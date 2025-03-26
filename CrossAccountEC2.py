import boto3
import time
import os

def assume_role(destination_account_role_arn):
    sts_client = boto3.client('sts')
    try:
        assumed_role = sts_client.assume_role(
            RoleArn=destination_account_role_arn,
            RoleSessionName="CrossAccountMigrationSession"
        )
        credentials = assumed_role['Credentials']
        return {
            'aws_access_key_id': credentials['AccessKeyId'],
            'aws_secret_access_key': credentials['SecretAccessKey'],
            'aws_session_token': credentials['SessionToken']
        }
    
    except Exception as e:
        print(f" Error assuming role: {str(e)}")
        return None

def share_ami_with_destination(source_ec2_client, ami_id, destination_account_id):
    try:
        source_ec2_client.modify_image_attribute(
            ImageId=ami_id,
            LaunchPermission={'Add': [{'UserId': destination_account_id}]}
        )
        print(f"Successfully shared AMI {ami_id} with account {destination_account_id}")
    except Exception as e:
        print(f" Error sharing AMI {ami_id}: {str(e)}")

def share_snapshot_with_destination(source_ec2_client, ami_id, destination_account_id):
    try:
        ami_details = source_ec2_client.describe_images(ImageIds=[ami_id])
        block_device_mappings = ami_details['Images'][0]['BlockDeviceMappings']
        for block in block_device_mappings:
            if 'Ebs' in block:
                snapshot_id = block['Ebs']['SnapshotId']
                source_ec2_client.modify_snapshot_attribute(
                    SnapshotId=snapshot_id,
                    Attribute="createVolumePermission",
                    OperationType="add",
                    UserIds=[destination_account_id]
                )
                print(f"Successfully shared snapshot {snapshot_id} with account {destination_account_id}")
    except Exception as e:
        print(f"Error sharing snapshot for AMI {ami_id}: {str(e)}")

def create_ami_and_copy(source_region, destination_region, source_access_key, source_secret_key, destination_role_arn):
    source_session = boto3.Session(
        aws_access_key_id=source_access_key,
        aws_secret_access_key=source_secret_key
    )
    source_ec2_client = source_session.client('ec2', region_name=source_region)
    source_ec2_resource = source_session.resource('ec2', region_name=source_region)
    destination_credentials = assume_role(destination_role_arn)
    if not destination_credentials:
        print(" Failed to assume role in the destination account.")
        return
    dest_ec2_client = boto3.client('ec2',
        aws_access_key_id=destination_credentials['aws_access_key_id'],
        aws_secret_access_key=destination_credentials['aws_secret_access_key'],
        aws_session_token=destination_credentials['aws_session_token'],
        region_name=destination_region
    )
    dest_sts_client = boto3.client(
    'sts',
    aws_access_key_id=destination_credentials['aws_access_key_id'],
    aws_secret_access_key=destination_credentials['aws_secret_access_key'],
    aws_session_token=destination_credentials['aws_session_token']
    )
    destination_account_id = dest_sts_client.get_caller_identity()['Account']

    instances = list(source_ec2_resource.instances.all())
    tagged_instances = [
        instance for instance in instances if any(tag['Key'] == 'Migration' and tag['Value'].lower() == 'true' for tag in (instance.tags or []))
    ]
    if not tagged_instances:
        user_input = input("No instances found with 'Migration=True'. Migrate all instances? (yes/no): ").strip().lower()
        if user_input != 'yes':
            print("Migration process aborted.")
            return
        tagged_instances = instances  
    for instance in tagged_instances:
        try:
            instance_tags = instance.tags or []
            instance_name = next((tag['Value'] for tag in instance_tags if tag['Key'] == 'Name'), 'Unnamed')
            ami_name = f"migration-{instance_name}-{instance.id}-{int(time.time())}"
            print(f"Creating AMI for instance {instance.id} ({instance_name})")
            ami_response = source_ec2_client.create_image(
                InstanceId=instance.id,
                Name=ami_name,
                NoReboot=True
            )
            ami_id = ami_response['ImageId']
            print(f"Waiting for AMI {ami_id} to become available")
            source_ec2_client.get_waiter('image_available').wait(ImageIds=[ami_id])

            share_ami_with_destination(source_ec2_client, ami_id, destination_account_id)
            share_snapshot_with_destination(source_ec2_client, ami_id, destination_account_id)

            print("Waiting 30 seconds for snapshot permissions to propagate...")
            time.sleep(30)
            
            print(f"Copying AMI {ami_id} to region {destination_region}")
            copy_response = dest_ec2_client.copy_image(
                SourceRegion=source_region,
                SourceImageId=ami_id,
                Name=f"copied-{ami_name}",
            )
            new_ami_id = copy_response['ImageId']
            print(f"Waiting for copied AMI {new_ami_id} to become available in {destination_region}")
            dest_ec2_client.get_waiter('image_available').wait(ImageIds=[new_ami_id])
            instance_type = instance.instance_type
            tag_specifications = [{
                'ResourceType': 'instance',
                'Tags': instance_tags
            }]
            print(f"Launching new instance in {destination_region}")
            new_instance = dest_ec2_client.run_instances(
                ImageId=new_ami_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                TagSpecifications=tag_specifications
            )
            new_instance_id = new_instance['Instances'][0]['InstanceId']
            print(f"Successfully launched instance {new_instance_id} ({instance_name}) in {destination_region}")
            print(f"Waiting for instance {new_instance_id} to reach 'running' state")
            dest_ec2_client.get_waiter('instance_running').wait(InstanceIds=[new_instance_id])
        except Exception as e:
            print(f"Error processing instance {instance.id}: {str(e)}")
            continue

def main():
    source_region = input("Enter the source AWS region (e.g., us-east-1): ").strip()
    destination_region = input("Enter the destination AWS region (e.g., ap-south-1): ").strip()
    source_access_key = os.getenv("AWS_ACCESS_KEY_ID") 
    source_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY") 
    destination_role_arn = input("Enter the IAM Role ARN for the destination account: ").strip()
    print(f"Starting EC2 instance migration from {source_region} to {destination_region}")
    create_ami_and_copy(source_region, destination_region, source_access_key, source_secret_key, destination_role_arn)

if __name__ == "__main__":
    main()

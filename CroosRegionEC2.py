import boto3
import time


def create_ami_and_copy(source_region, destination_region):
    source_ec2_client = boto3.client('ec2', region_name=source_region)
    source_ec2_resource = boto3.resource('ec2', region_name=source_region)
    dest_ec2_client = boto3.client('ec2', region_name=destination_region)
    
   
    instances = list(source_ec2_resource.instances.all())
    
    tagged_instances = [
        instance for instance in instances if any(tag['Key'] == 'Migration' and tag['Value'].lower() == 'true' for tag in (instance.tags or []))
    ]

    if not tagged_instances:
        user_input = input("No instances found with 'Migration=True'. Do you want to migrate all instances? (yes/no): ").strip().lower()
        if user_input != 'yes':
            print("Migration process aborted.")
            return
        tagged_instances = instances  
    
    for instance in tagged_instances:
        try:
            instance_tags = instance.tags or []
            instance_name = next((tag['Value'] for tag in instance_tags if tag['Key'] == 'Name'), 'Unnamed')

            ami_name = f"migration-{instance_name}-{instance.id}-{int(time.time())}"

            # Create AMI
            print(f"Creating AMI for instance {instance.id} ({instance_name})")
            ami_response = source_ec2_client.create_image(
                InstanceId=instance.id,
                Name=ami_name,
                NoReboot=True
            )

            ami_id = ami_response['ImageId']

           
            print(f"Waiting for AMI {ami_id} to be available")
            waiter = source_ec2_client.get_waiter('image_available')
            waiter.wait(ImageIds=[ami_id])

           
            print(f"Copying AMI {ami_id} to region {destination_region}")
            copy_response = dest_ec2_client.copy_image(
                SourceRegion=source_region,
                SourceImageId=ami_id,
                Name=f"copied-{ami_name}",
            )

            new_ami_id = copy_response['ImageId']

            print(f"Waiting for copied AMI {new_ami_id} to be available in {destination_region}")
            dest_waiter = dest_ec2_client.get_waiter('image_available')
            dest_waiter.wait(ImageIds=[new_ami_id])

            
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

            print(f"Waiting for instance {new_instance_id} to be running")
            instance_waiter = dest_ec2_client.get_waiter('instance_running')
            instance_waiter.wait(InstanceIds=[new_instance_id])

        except Exception as e:
            print(f"Error processing instance {instance.id}: {str(e)}")
            continue

def main():
    SOURCE_REGION = input("Enter Source region: ").strip() 
    DESTINATION_REGION = input("Enter Destination region: ").strip()

    print(f"Starting EC2 instance migration from {SOURCE_REGION} to {DESTINATION_REGION}")
    create_ami_and_copy(SOURCE_REGION, DESTINATION_REGION)

if __name__ == "__main__":
    main()

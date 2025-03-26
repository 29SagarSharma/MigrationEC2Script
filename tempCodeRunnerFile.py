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

share_snapshot_with_destination(source_ec2_client, ami_id, destination_account_id)


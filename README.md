Migrate EC2 instances from source account to destination account with tag specification on instances.
First, we uses AWS Security Token Service (STS) to assume an IAM role in the destination AWS account. Returns temporary security credentials (AccessKeyId, SecretAccessKey, SessionToken) for interacting with the destination account.
Second, we Finds instances to migrate.
Creates an AMI of each selected instance.
Shares the AMI & snapshot with the destination account.
Copies the AMI to the destination region.
Launches a new instance in the destination region.

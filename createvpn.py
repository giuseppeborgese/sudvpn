#!/usr/bin/python3
import boto3
import random
import string
import time

region = "eu-central-1"
ec2 = boto3.client('ec2', region_name = region)
iam = boto3.client('iam')


def generate_random_string(length):
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

def create_ec2_machine():
    # a machine with the permission to autodestory after some time
    return True

def get_default_vpc_id():
    response = ec2.describe_vpcs(
        Filters=[
            {
                'Name': 'isDefault',
                'Values': ['true']
            }
        ]
    )
    
    if 'Vpcs' in response and len(response['Vpcs']) > 0:
        return response['Vpcs'][0]['VpcId']
    
    return None

def create_security_group(vpc_id):
    random_string = generate_random_string(10)
    group_name = "SudVPN-"+random_string
    description = 'this is to be used by sudvpn'

    response = ec2.create_security_group(
        GroupName=group_name,
        Description=description,
        VpcId=vpc_id
    )
    
    security_group_id = response['GroupId']
    
    # Adding inbound rule for UDP traffic on port 1194
    ec2.authorize_security_group_ingress(
        GroupId=security_group_id,
        IpProtocol='udp',
        FromPort=1194,
        ToPort=1194,
        CidrIp='0.0.0.0/0'
    )
    
    return security_group_id

def create_ec2_role(role_name):
    
    # Create the IAM role
    response = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument='''{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ec2.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }'''
    )
    
    role_arn = response['Role']['Arn']
    
    # Attach the policy to the role
    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'
    )
    
    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn='arn:aws:iam::aws:policy/AmazonEC2FullAccess'
    )
    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn='arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore'
    )
    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess'
    )

    response = iam.create_instance_profile(InstanceProfileName=role_name)
    response = iam.add_role_to_instance_profile(InstanceProfileName=role_name,RoleName=role_name)
    return role_arn

def get_first_subnet_id(vpc_id):
    
    response = ec2.describe_subnets(
        Filters=[
            {
                'Name': 'vpc-id',
                'Values': [vpc_id]
            }
        ]
    )
    
    subnets = response['Subnets']
    if subnets:
        return subnets[0]['SubnetId']
    else:
        return None

def get_role_arn(role_name):    
    try:
        response = iam.get_role(RoleName=role_name)
        if response is not None and 'Role' in response:
            return response['Role']['Arn']
    except iam.exceptions.NoSuchEntityException:
        pass
    
    return None

def create_ec2_instance(subnet_id,sg_id,bucket_name,profile_name):
    
    # Get the latest Ubuntu AMI ID
    response = ec2.describe_images(
        Filters=[
            {'Name': 'name', 'Values': ['ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*']},
            {'Name': 'owner-id', 'Values': ['099720109477']}
        ],
        Owners=['099720109477']
    )
    
    images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
    ami_id = images[0]['ImageId']
    
    # Create the instance
    response = ec2.run_instances(
        ImageId=ami_id,
        InstanceType='t3.micro',
        UserData=get_user_data(bucket_name),
        SecurityGroupIds=[sg_id],
        SubnetId=subnet_id,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={'Name': profile_name},
    )
    
    instance_id = response['Instances'][0]['InstanceId']
    
    return instance_id

def get_user_data(bucket_name):
    # Create a script to terminate the instance after 10 minutes
    user_data = f"""#!/bin/bash
wget -O openvpn.sh https://get.vpnsetup.net/ovpn
sudo bash openvpn.sh <<ANSWERS
1
1194
1
client
y
ANSWERS
apt install awscli jq -y
aws s3 cp /root/client.ovpn s3://{bucket_name}/client-$(curl -s http://169.254.169.254/latest/meta-data/instance-id)-$(curl --silent http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region).ovpn
sleep 600
aws ec2 terminate-instances --instance-ids $(curl -s http://169.254.169.254/latest/meta-data/instance-id) --region $(curl --silent http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region)
"""
    return user_data

def check_and_create_bucket():
    s3_client = boto3.client('s3')
    bucket_prefix = 'sudvpn-openconfig-files'
    
    response = s3_client.list_buckets()
    buckets = [bucket['Name'] for bucket in response['Buckets']]
    
    for bucket_name in buckets:
        if bucket_name.startswith(bucket_prefix):
            print(f"A bucket starting with '{bucket_prefix}' already exists.")
            return bucket_name
    
    # Generate a random suffix
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    new_bucket_name = bucket_prefix + '-' + suffix
    
    # Create the bucket
    s3_client.create_bucket(
        Bucket=new_bucket_name,
        CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'}  
    )
    print(f"The bucket '{new_bucket_name}' has been created.")
    return new_bucket_name

def wait_for_file(bucket_name, file_key):
    s3_client = boto3.client('s3')
    
    waiter = s3_client.get_waiter('object_exists')
    waiter.wait(
        Bucket=bucket_name,
        Key=file_key,
        WaiterConfig={
            'Delay': 5,
            'MaxAttempts': 60
        }
    )
    
    print(f"The file '{file_key}' exists in the bucket '{bucket_name}'.")

def wait_for_iam_profile(profile_name):
    waiter = iam.get_waiter('instance_profile_exists')
    
    print(f"Waiting for the IAM profile '{profile_name}' to be available...")
    waiter.wait(InstanceProfileName=profile_name)
    
    print(f"The IAM profile '{profile_name}' exists.")

def download_file(bucket_name, file_key, destination_path):
    s3_client = boto3.client('s3')
    s3_client.download_file(bucket_name, file_key, destination_path)    
    print(f"The file '{file_key}' has been downloaded to '{destination_path}'.")


# Retrieve the default VPC ID
default_vpc_id = get_default_vpc_id()
print(default_vpc_id)
# Create the security group
security_group_id = create_security_group(default_vpc_id)

# Specify the desired role name
role_name = 'SudVPN-Ec2Role' #and profile name are the same
# Check if the role exists
role_arn = get_role_arn(role_name)
if role_arn:
    print(f"Role '{role_name}' exists with ARN: {role_arn}")
else:
    print(f"Role '{role_name}' does not exist.")
    # Create the EC2 role with the policy
    role_arn = create_ec2_role(role_name)

print(role_arn)

# Example usage
subnet_id = get_first_subnet_id(default_vpc_id)
print(subnet_id)

bucket_to_use = check_and_create_bucket()
print(bucket_to_use)

wait_for_iam_profile(role_name)

instance_id = create_ec2_instance(subnet_id,security_group_id,bucket_to_use,role_name)
print(instance_id)

config_file_key="client-"+instance_id+"-"+region+".ovpn"
wait_for_file(bucket_to_use, config_file_key)

# Example usage
destination_path = '~/Downloads/'
download_file(bucket_to_use, config_file_key, destination_path)

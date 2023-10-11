#!/usr/bin/python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import boto3
import random
import string
import time
import os
import json
from pkg_resources import resource_filename

    
def choose_the_region():
    ec2 = boto3.client('ec2')
    response = ec2.describe_regions(AllRegions=True)
    i=0
    for region in response['Regions']:
        #message=get_region_location(region['RegionName'])
        message = get_region_name(region['RegionName'])
        enabled=True
        if region['OptInStatus'] == "not-opted-in":
            enabled=False
        print(f"{i} - enabled {enabled} - {message}")
        i=i+1

    print("\nIf you select a region not enabled the script will enable but the process \nwill require some minutes or hours until the region will be shown as enabled")
    choosen_region = input("\nType the number of the choosen the region where you want your vpn: ")
    
    if response['Regions'][int(choosen_region)]['OptInStatus'] == "not-opted-in":
        enable_region(response['Regions'][int(choosen_region)]['RegionName'])  
    
    return response['Regions'][int(choosen_region)]['RegionName']    

def enable_region(region_code):
    account_client = boto3.client('account')
    response = account_client.enable_region(RegionName=region_code)
    print(f"\nThe region {region_code} will be enabled but this can requires some minutes or some hours until ready")
    print("try to check for the region later, the program will close for now")
    exit(1)

def get_region_name(region_code):
    default_region = 'US East (N. Virginia)'
    endpoint_file = resource_filename('botocore', 'data/endpoints.json')
    if region_code == "il-central-1": #for some reason the system is giving me error on this at the moment
        return "Israel (Tel Aviv)"
    try:
        with open(endpoint_file, 'r') as f:
            data = json.load(f)
        # Botocore is using Europe while Pricing API using EU...sigh...
        return data['partitions'][0]['regions'][region_code]['description'].replace('Europe', 'EU')
    except IOError:
        return default_region

def get_price_on_demand_per_hour(region, instance, os):
    # Search product filter. This will reduce the amount of data returned by the
    # get_products function of the Pricing API
    FLT = '[{{"Field": "tenancy", "Value": "shared", "Type": "TERM_MATCH"}},'\
        '{{"Field": "operatingSystem", "Value": "{o}", "Type": "TERM_MATCH"}},'\
        '{{"Field": "preInstalledSw", "Value": "NA", "Type": "TERM_MATCH"}},'\
        '{{"Field": "instanceType", "Value": "{t}", "Type": "TERM_MATCH"}},'\
        '{{"Field": "location", "Value": "{r}", "Type": "TERM_MATCH"}},'\
        '{{"Field": "capacitystatus", "Value": "Used", "Type": "TERM_MATCH"}}]'

    f = FLT.format(r=region, t=instance, o=os)
    pricing_client = boto3.client('pricing', region_name='us-east-1')
    data = pricing_client.get_products(ServiceCode='AmazonEC2', Filters=json.loads(f))
    od = json.loads(data['PriceList'][0])['terms']['OnDemand']
    id1 = list(od)[0]
    id2 = list(od[id1]['priceDimensions'])[0]
    return od[id1]['priceDimensions'][id2]['pricePerUnit']['USD']

# def get_region_location(region_code):
#     region_mappings = {
#         'af-south-1': ('Cape Town', 'South Africa'),
#         'ap-east-1': ('Hong Kong', 'China'),
#         'ap-northeast-1': ('Tokyo', 'Japan'),
#         'ap-northeast-2': ('Seoul', 'South Korea'),
#         'ap-northeast-3': ('Osaka-Local', 'Japan'),
#         'ap-south-1': ('Mumbai', 'India'),
#         'ap-southeast-1': ('Singapore', 'Singapore'),
#         'ap-southeast-2': ('Sydney', 'Australia'),
#         'ca-central-1': ('Central', 'Canada'),
#         'cn-north-1': ('Beijing', 'China'),
#         'cn-northwest-1': ('Ningxia', 'China'),
#         'eu-central-1': ('Frankfurt', 'Germany'),
#         'eu-north-1': ('Stockholm', 'Sweden'),
#         'eu-south-1': ('Milan', 'Italy'),
#         'eu-west-1': ('Ireland', 'Ireland'),
#         'eu-west-2': ('London', 'United Kingdom'),
#         'eu-west-3': ('Paris', 'France'),
#         'me-south-1': ('Bahrain', 'Bahrain'),
#         'sa-east-1': ('Sao Paulo', 'Brazil'),
#         'us-east-1': ('N. Virginia', 'USA'),
#         'us-east-2': ('Ohio', 'USA'),
#         'us-west-1': ('N. California', 'USA'),
#         'us-west-2': ('Oregon', 'USA'),
#     }

#     if region_code in region_mappings:
#         return region_mappings[region_code]
#     else:
#         return ('Unknown', 'Unknown')

def generate_random_string(length):
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for _ in range(length))


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

def create_security_group_if_it_does_not_exist(vpc_id):
    random_string = generate_random_string(10)
    group_name = "SudVPN-do-not-modify"
    description = 'this is to be used by sudvpn'

    response = ec2.describe_security_groups(
        Filters=[
            {'Name': 'group-name', 'Values': [group_name]},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    )    
    if response['SecurityGroups']:
        return response['SecurityGroups'][0]['GroupId']
    
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

def create_ec2_instance(subnet_id,sg_id,bucket_name,profile_name,time_seconds):
    
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
        UserData=get_user_data(bucket_name,time_seconds),
        SecurityGroupIds=[sg_id],
        SubnetId=subnet_id,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={'Name': profile_name},
        TagSpecifications=[
           {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': 'SudVPN-autodestroy-ec2'
                    },
                ]
            },
        ],
    )
    
    instance_id = response['Instances'][0]['InstanceId']
    
    return instance_id

def get_user_data(bucket_name, time_seconds):
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
sleep {time_seconds}
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
    
    time.sleep(6) 
    #without this sleep there is an error like this one
    #botocore.exceptions.ClientError: An error occurred (InvalidParameterValue) when calling the RunInstances operation: Value (SudVPN-Ec2Role) for parameter iamInstanceProfile.name is invalid. Invalid IAM Instance Profile name
    #the wait is not enough

def download_file(bucket_name, file_key, destination_path):
    s3_client.download_file(bucket_name, file_key, destination_path+file_key)    
    print(f"The file '{file_key}' has been downloaded to '{destination_path}'.")

def delete_file(bucket_name, file_key):
    response = s3_client.delete_object(
    Bucket=bucket_name,
    Key=file_key)
    print(f"The file '{file_key}' has been deleted" )

def get_region_location(region_code):
    region_mappings = {
        'af-south-1': ('Cape Town', 'South Africa'),
        'ap-east-1': ('Hong Kong', 'China'),
        'ap-northeast-1': ('Tokyo', 'Japan'),
        'ap-northeast-2': ('Seoul', 'South Korea'),
        'ap-northeast-3': ('Osaka-Local', 'Japan'),
        'ap-south-1': ('Mumbai', 'India'),
        'ap-southeast-1': ('Singapore', 'Singapore'),
        'ap-southeast-2': ('Sydney', 'Australia'),
        'ca-central-1': ('Central', 'Canada'),
        'cn-north-1': ('Beijing', 'China'),
        'cn-northwest-1': ('Ningxia', 'China'),
        'eu-central-1': ('Frankfurt', 'Germany'),
        'eu-north-1': ('Stockholm', 'Sweden'),
        'eu-south-1': ('Milan', 'Italy'),
        'eu-west-1': ('Ireland', 'Ireland'),
        'eu-west-2': ('London', 'United Kingdom'),
        'eu-west-3': ('Paris', 'France'),
        'me-south-1': ('Bahrain', 'Bahrain'),
        'sa-east-1': ('Sao Paulo', 'Brazil'),
        'us-east-1': ('N. Virginia', 'USA'),
        'us-east-2': ('Ohio', 'USA'),
        'us-west-1': ('N. California', 'USA'),
        'us-west-2': ('Oregon', 'USA'),
    }

    if region_code in region_mappings:
        return region_mappings[region_code]
    else:
        return ('Unknown', 'Unknown')

def select_the_time(selected_region):
    cost_1_hour = float(get_price_on_demand_per_hour(get_region_name(selected_region), 't3.micro', 'Linux'))
    possible_time = [
        ['10 minutes            ', 600, str(round(cost_1_hour/6, 6))],
        ['20 minutes            ', 1200, str(round(cost_1_hour/3, 6))],
        ['30 minutes            ', 1800, str(round(cost_1_hour/2, 6))],
        ['1 hour                ', 3600, str(round(cost_1_hour, 6))],
        ['1 hour and 30 minutes ', 5400, str(round(cost_1_hour+cost_1_hour/2, 6))],
        ['2 hours               ', 7200, str(round(cost_1_hour*2, 6))]
    ]
    i=0
    print("Type the number of choosen VPN Server Duration")
    for ele in possible_time:
        print(f"{i} - {ele[0]} cost for the instance in USD {ele[2]}")
        i=i+1
    decision=input("\nInsert a number: ")
    return possible_time[int(decision)][1]

def create_iam_policy(iam,role_name):

    # Define the policy document in JSON format
    policy_document = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "ec2:TerminateInstances",
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "s3:PutObject",
            "Resource": "arn:aws:s3:::sudvpn-openconfig-files*/*"
        }
        ]
    }

    # Create the custom policy
    response = iam.create_policy(
        PolicyName="SudVPN-restrict-policy",
        PolicyDocument=json.dumps(policy_document, indent=4)
    )
    policy_arn = response['Policy']['Arn']

    # Attach the policy to the role
    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn=policy_arn
    )
    


# Get the available regions
region = choose_the_region()
print(f"You are working on the {region}")

ec2 = boto3.client('ec2', region_name = region)
iam = boto3.client('iam')
s3_client = boto3.client('s3')

print("For many regions the outgoing traffic from EC2 to internet is 0,09 USD per GB")
print("The EC2 storage cost is irrelevant")
time_seconds = select_the_time(region)

# Retrieve the default VPC ID
default_vpc_id = get_default_vpc_id()
print(default_vpc_id)
# Create the security group
security_group_id = create_security_group_if_it_does_not_exist(default_vpc_id)

# Specify the desired role name
role_name = 'SudVPN-Ec2Role' #and profile name are the same
# Check if the role exists
role_arn = get_role_arn(role_name)
if role_arn:
    print(f"Role '{role_name}' exists with ARN: {role_arn}")
else:
    print(f"Role '{role_name}' does not exist.")
    # Create the EC2 role
    role_arn = create_ec2_role(role_name)
    #create the policy and attach to the role
    print("creating a policy and attach to the role")
    create_iam_policy(iam, role_name)

print(role_arn)


# Example usage
subnet_id = get_first_subnet_id(default_vpc_id)
print(subnet_id)

bucket_to_use = check_and_create_bucket()
print(bucket_to_use)

wait_for_iam_profile(role_name)

print("Creating the OpenVPNServer, you need to wait few minutes")
instance_id = create_ec2_instance(subnet_id,security_group_id,bucket_to_use,role_name,time_seconds)
print(instance_id)

config_file_key="client-"+instance_id+"-"+region+".ovpn"
wait_for_file(bucket_to_use, config_file_key)

# download the file in your laptop
destination_path = '/tmp/'
download_file(bucket_to_use, config_file_key, destination_path)

# remove the file from the s3 bucket we don't need it anymore
delete_file(bucket_to_use, config_file_key)

print()
print("Below messages are from open OpenVPN Binary")
print("--------------------------------------------")
binary_file = "/Applications/OpenVPN\ Connect/OpenVPN\ Connect.app/Contents/MacOS/OpenVPN\ Connect "
option_config = "--import-profile="
#insert profile
os.system(binary_file+option_config+destination_path+config_file_key)
#open the client
os.system(binary_file)
print("--------------------------------------------")
print("Above messages are from open OpenVPN Binary")
print()
print("after you finished remove from your openvpn client the profile for the new vpn")

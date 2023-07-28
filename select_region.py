import boto3
import os 

def choose_the_region():
    ec2 = boto3.client('ec2')
    response = ec2.describe_regions()
    i=0
    for region in response['Regions']:
        message=get_region_location(region['RegionName'])
        print(f"{i} - {message}")
        i=i+1
    choosen_region = input("\nChoose the region where you want your vpn: ")
    return response['Regions'][int(choosen_region)]['RegionName']    

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

def select_the_time():
    time = [
        ['10 minutes', 600],
        ['20 minutes', 1200],
        ['30 minutes', 1800],
        ['1 hour', 3600],
        ['1 hour and 30 minutes', 5400],
        ['2 hours', 7200]
    ]
    i=0
    print("Choose you VPN Server Duration")
    for ele in time:
        print(f"{i} - {ele[0]}")
        i=i+1
    decision=input("\nInsert a number: ")
    return time[int(decision)][1]
# Get the available regions
#region_code = choose_the_region()
#print(region_code)
# Print the list of regions
s3_client = boto3.client('s3')

#print(select_the_time())
def download_file(bucket_name, file_key, destination_path):
    s3_client.download_file(bucket_name, file_key, destination_path+file_key)    
    print(f"The file '{file_key}' has been downloaded to '{destination_path}'")


config_file_key = "client-i-08636f2762d376330-ap-south-1.ovpn"
#bucket_to_use = "sudvpn-openconfig-files-idz036v4"

destination_path = '/tmp/'
#download_file(bucket_to_use, config_file_key, destination_path)


def create_vpc_with_public_subnets_if_does_not_exist():
    my_tag_name = "SudVPN-do-not-modify"
    vpc_cidr = '10.0.0.0/16'
    subnet_cidrs = ['10.0.1.0/24', '10.0.2.0/24', '10.0.3.0/24']

    ec2 = boto3.client('ec2')

       # Create VPC
    response = ec2.create_vpc(
        CidrBlock=vpc_cidr,
        AmazonProvidedIpv6CidrBlock=False
    )
    vpc_id = response['Vpc']['VpcId']

    # Add name tag to the VPC
    ec2.create_tags(
        Resources=[vpc_id],
        Tags=[
            {
                'Key': 'Name',
                'Value': my_tag_name
            }
        ]
    )

    # Enable DNS hostnames in the VPC
    ec2.modify_vpc_attribute(
        VpcId=vpc_id,
        EnableDnsHostnames={'Value': True}
    )

    # Create internet gateway
    response = ec2.create_internet_gateway()
    internet_gateway_id = response['InternetGateway']['InternetGatewayId']

    # Attach internet gateway to the VPC
    ec2.attach_internet_gateway(
        VpcId=vpc_id,
        InternetGatewayId=internet_gateway_id
    )

    # Create route table
    response = ec2.create_route_table(VpcId=vpc_id)
    route_table_id = response['RouteTable']['RouteTableId']

    # Create route to internet gateway
    ec2.create_route(
        RouteTableId=route_table_id,
        DestinationCidrBlock='0.0.0.0/0',
        GatewayId=internet_gateway_id
    )

    # Create subnets
    subnet_ids = []
    for i, cidr in enumerate(subnet_cidrs):
        response = ec2.create_subnet(
            VpcId=vpc_id,
            CidrBlock=cidr
        )
        subnet_id = response['Subnet']['SubnetId']
        subnet_ids.append(subnet_id)

        # Add name tag to the subnet
        ec2.create_tags(
            Resources=[subnet_id],
            Tags=[
                {
                    'Key': 'Name',
                    'Value': f'{my_tag_name} {i+1}'
                }
            ]
        )

        # Associate subnet with route table
        ec2.associate_route_table(
            RouteTableId=route_table_id,
            SubnetId=subnet_id
        )

        # Enable auto-assign public IP on subnet
        ec2.modify_subnet_attribute(
            SubnetId=subnet_id,
            MapPublicIpOnLaunch={'Value': True}
        )

    return vpc_id, subnet_ids


# Example usage

vpc_id, subnet_ids = create_vpc_with_public_subnets()

print(f"VPC created with ID: {vpc_id}")
print("Public Subnet IDs:")
for subnet_id in subnet_ids:
    print(subnet_id)

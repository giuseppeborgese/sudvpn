import boto3

def list_disabled_regions():
    ec2 = boto3.client('ec2')
    response = ec2.describe_regions(AllRegions=True)
    for region in response['Regions']:
        print(f"{region['RegionName']} {region['OptInStatus']}")

# Get the disabled regions
disabled_regions = list_disabled_regions()


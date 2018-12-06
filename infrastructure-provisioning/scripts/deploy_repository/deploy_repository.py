#!/usr/bin/python
# *****************************************************************************
#
# Copyright (c) 2016, EPAM SYSTEMS INC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# ******************************************************************************

from fabric.api import *
import argparse
import boto3
import traceback
import sys
import json
import time

parser = argparse.ArgumentParser()
parser.add_argument('--service_base_name', required=True, type=str, default='',
                    help='unique name for repository environment')
parser.add_argument('--vpc_id', type=str, default='', help='AWS VPC ID')
parser.add_argument('--vpc_cidr', type=str, default='172.31.0.0/16', help='Cidr of VPC')
parser.add_argument('--subnet_id', type=str, default='', help='AWS Subnet ID')
parser.add_argument('--subnet_cidr', type=str, default='172.31.0.0/24', help='Cidr of subnet')
parser.add_argument('--sg_id', type=str, default='', help='AWS VPC ID')
parser.add_argument('--billing_tag', type=str, default='product:dlab', help='Tag in format: "Key1:Value1"')
parser.add_argument('--additional_tags', type=str, default='', help='Tags in format: "Key1:Value1;Key2:Value2"')
parser.add_argument('--tag_resource_id', type=str, default='dlab', help='The name of user tag')
parser.add_argument('--allowed_ip_cidr', type=str, default='', help='Comma-separated CIDR of IPs which will have '
                                                                    'access to the instance')
parser.add_argument('--key_name', type=str, default='', help='Key name (WITHOUT ".pem")')
parser.add_argument('--instance_type', type=str, default='t2.medium', help='Instance shape')
parser.add_argument('--region', required=True, type=str, default='', help='AWS region name')
parser.add_argument('--elastic_ip', type=str, default='', help='Elastic IP address')
parser.add_argument('--network_type', type=str, default='public', help='Network type: public or private')
parser.add_argument('--hosted_zone_name', type=str, default='', help='Name of hosted zone')
parser.add_argument('--hosted_zone_id', type=str, default='', help='ID of hosted zone')
parser.add_argument('--subdomain', type=str, default='', help='Subdomain name')
parser.add_argument('--action', required=True, type=str, default='', help='Action: create or terminate')
args = parser.parse_args()


def vpc_exist(return_id=False):
    try:
        vpc_created = False
        for vpc in ec2_resource.vpcs.filter(Filters=[{'Name': 'tag-key', 'Values': [tag_name]},
                                                     {'Name': 'tag-value', 'Values': [args.service_base_name]}]):
            if return_id:
                return vpc.id
            vpc_created = True
        return vpc_created
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS VPC: {}'.format(str(err)))


def create_vpc(vpc_cidr):
    try:
        tag = {"Key": tag_name, "Value": args.service_base_name}
        name_tag = {"Key": "Name", "Value": args.service_base_name + '-vpc'}
        vpc = ec2_resource.create_vpc(CidrBlock=vpc_cidr)
        create_tag(vpc.id, tag)
        create_tag(vpc.id, name_tag)
        return vpc.id
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with creating AWS VPC: {}'.format(str(err)))


def enable_vpc_dns(vpc_id):
    try:
        ec2_client.modify_vpc_attribute(VpcId=vpc_id,
                                        EnableDnsHostnames={'Value': True})
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with modifying AWS VPC attributes: {}'.format(str(err)))


def create_rt(vpc_id):
    try:
        tag = {"Key": tag_name, "Value": args.service_base_name}
        name_tag = {"Key": "Name", "Value": args.service_base_name + '-rt'}
        route_table = []
        rt = ec2_client.create_route_table(VpcId=vpc_id)
        rt_id = rt.get('RouteTable').get('RouteTableId')
        route_table.append(rt_id)
        print('Created AWS Route-Table with ID: {}'.format(rt_id))
        create_tag(route_table, json.dumps(tag))
        create_tag(route_table, json.dumps(name_tag))
        ig = ec2_client.create_internet_gateway()
        ig_id = ig.get('InternetGateway').get('InternetGatewayId')
        route_table = list()
        route_table.append(ig_id)
        create_tag(route_table, json.dumps(tag))
        create_tag(route_table, json.dumps(name_tag))
        ec2_client.attach_internet_gateway(InternetGatewayId=ig_id, VpcId=vpc_id)
        ec2_client.create_route(DestinationCidrBlock='0.0.0.0/0', RouteTableId=rt_id, GatewayId=ig_id)
        return rt_id
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with creating AWS Route Table: {}'.format(str(err)))


def remove_vpc(vpc_id):
    try:
        ec2_client.delete_vpc(VpcId=vpc_id)
        print("AWS VPC {} has been removed".format(vpc_id))
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with removing AWS VPC: {}'.format(str(err)))


def create_tag(resource, tag, with_tag_res_id=True):
    try:
        tags_list = list()
        if type(tag) == dict:
            resource_name = tag.get('Value')
            resource_tag = tag
        else:
            resource_name = json.loads(tag).get('Value')
            resource_tag = json.loads(tag)
        if type(resource) != list:
            resource = [resource]
        tags_list.append(resource_tag)
        if with_tag_res_id:
            tags_list.append(
                {
                    'Key': args.tag_resource_id,
                    'Value': args.service_base_name + ':' + resource_name
                }
            )
            tags_list.append(
                {
                    'Key': args.billing_tag.split(':')[0],
                    'Value': args.billing_tag.split(':')[1]
                }
            )
        if args.additional_tags:
            for tag in args.additional_tags.split(';'):
                tags_list.append(
                    {
                        'Key': tag.split(':')[0],
                        'Value': tag.split(':')[1]
                    }
                )
        ec2_client.create_tags(
            Resources=resource,
            Tags=tags_list
        )
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with setting tag: {}'.format(str(err)))


def create_subnet(vpc_id, subnet_cidr):
    try:
        tag = {"Key": tag_name, "Value": "{}".format(args.service_base_name)}
        name_tag = {"Key": "Name", "Value": "{}-subnet".format(args.service_base_name)}
        subnet = ec2_resource.create_subnet(VpcId=vpc_id, CidrBlock=subnet_cidr)
        create_tag(subnet.id, tag)
        create_tag(subnet.id, name_tag)
        subnet.reload()
        print('AWS Subnet has been created')
        return subnet.id
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with creating AWS Subnet: {}'.format(str(err)))


def remove_subnet():
    try:
        subnets = ec2_resource.subnets.filter(
            Filters=[{'Name': 'tag:{}'.format(tag_name), 'Values': [args.service_base_name]}])
        if subnets:
            for subnet in subnets:
                ec2_client.delete_subnet(SubnetId=subnet.id)
                print("The AWS subnet {} has been deleted successfully".format(subnet.id))
        else:
            print("There are no private AWS subnets to delete")
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with removing AWS Subnet: {}'.format(str(err)))


def get_route_table_by_tag(tag_value):
    try:
        route_tables = ec2_client.describe_route_tables(
            Filters=[{'Name': 'tag:{}'.format(tag_name), 'Values': ['{}'.format(tag_value)]}])
        rt_id = route_tables.get('RouteTables')[0].get('RouteTableId')
        return rt_id
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS Route tables: {}'.format(str(err)))


def create_security_group(security_group_name, vpc_id):
    try:
        allowed_ip_cidr = list()
        for cidr in args.allowed_ip_cidr.split(','):
            allowed_ip_cidr.append({"CidrIp": cidr.replace(' ', '')})
        allowed_vpc_cidr_ip_ranges = list()
        for cidr in get_vpc_cidr_by_id(vpc_id):
            allowed_vpc_cidr_ip_ranges.append({"CidrIp": cidr})
        ingress = format_sg([
            {
                "PrefixListIds": [],
                "FromPort": 80,
                "IpRanges": allowed_ip_cidr,
                "ToPort": 80, "IpProtocol": "tcp", "UserIdGroupPairs": []
            },
            {
                "PrefixListIds": [],
                "FromPort": 22,
                "IpRanges": allowed_ip_cidr,
                "ToPort": 22, "IpProtocol": "tcp", "UserIdGroupPairs": []
            },
            {
                "PrefixListIds": [],
                "FromPort": 443,
                "IpRanges": allowed_ip_cidr,
                "ToPort": 443, "IpProtocol": "tcp", "UserIdGroupPairs": []
            },
            {
                "PrefixListIds": [],
                "FromPort": 80,
                "IpRanges": allowed_vpc_cidr_ip_ranges,
                "ToPort": 80, "IpProtocol": "tcp", "UserIdGroupPairs": []
            },
            {
                "PrefixListIds": [],
                "FromPort": 443,
                "IpRanges": allowed_vpc_cidr_ip_ranges,
                "ToPort": 443, "IpProtocol": "tcp", "UserIdGroupPairs": []
            }
        ])
        egress = format_sg([
            {"IpProtocol": "-1", "IpRanges": [{"CidrIp": '0.0.0.0/0'}], "UserIdGroupPairs": [], "PrefixListIds": []}
        ])
        tag = {"Key": tag_name, "Value": args.service_base_name}
        name_tag = {"Key": "Name", "Value": args.service_base_name + "-sg"}
        group = ec2_resource.create_security_group(GroupName=security_group_name, Description='security_group_name',
                                                   VpcId=vpc_id)
        time.sleep(10)
        create_tag(group.id, tag)
        create_tag(group.id, name_tag)
        try:
            group.revoke_egress(IpPermissions=[{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                                                "UserIdGroupPairs": [], "PrefixListIds": []}])
        except:
            print("Mentioned rule does not exist")
        for rule in ingress:
            group.authorize_ingress(IpPermissions=[rule])
        for rule in egress:
            group.authorize_egress(IpPermissions=[rule])
        return group.id
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with creating AWS security group: {}'.format(str(err)))


def get_vpc_cidr_by_id(vpc_id):
    try:
        cidr_list = list()
        for vpc in ec2_client.describe_vpcs(VpcIds=[vpc_id]).get('Vpcs'):
            for cidr_set in vpc.get('CidrBlockAssociationSet'):
                cidr_list.append(cidr_set.get('CidrBlock'))
            return cidr_list
        return ''
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS VPC CIDR: {}'.format(str(err)))


def format_sg(sg_rules):
    try:
        formatted_sg_rules = list()
        for rule in sg_rules:
            if rule['IpRanges']:
                for ip_range in rule['IpRanges']:
                    formatted_rule = dict()
                    for key in rule.keys():
                        if key == 'IpRanges':
                            formatted_rule['IpRanges'] = [ip_range]
                        else:
                            formatted_rule[key] = rule[key]
                    if formatted_rule not in formatted_sg_rules:
                        formatted_sg_rules.append(formatted_rule)
            else:
                formatted_sg_rules.append(rule)
        return formatted_sg_rules
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with formating AWS SG rules: {}'.format(str(err)))


def remove_sgroups():
    try:
        sgs = ec2_resource.security_groups.filter(
            Filters=[{'Name': 'tag:{}'.format(tag_name), 'Values': [args.service_base_name]}])
        if sgs:
            for sg in sgs:
                ec2_client.delete_security_group(GroupId=sg.id)
                print("The AWS security group {} has been deleted successfully".format(sg.id))
        else:
            print("There are no AWS security groups to delete")
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with removing AWS SG: {}'.format(str(err)))


def create_instance():
    try:
        user_data = ''
        ami_id = get_ami_id('ubuntu/images/hvm-ssd/ubuntu-xenial-16.04-amd64-server-20160907.1')
        instances = ec2_resource.create_instances(ImageId=ami_id, MinCount=1, MaxCount=1,
                                                  KeyName=args.key_name,
                                                  SecurityGroupIds=[args.sg_id],
                                                  InstanceType=args.instance_type,
                                                  SubnetId=args.subnet_id,
                                                  UserData=user_data)
        for instance in instances:
            print("Waiting for instance {} become running.".format(instance.id))
            instance.wait_until_running()
            tag = {'Key': 'Name', 'Value': args.service_base_name + '-repository'}
            instance_tag = {"Key": tag_name, "Value": args.service_base_name}
            create_tag(instance.id, tag)
            create_tag(instance.id, instance_tag)
            tag_intance_volume(instance.id, args.service_base_name + '-repository', instance_tag)
            return instance.id
        return ''
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with creating AWS EC2 instance: {}'.format(str(err)))


def tag_intance_volume(instance_id, node_name, instance_tag):
    try:
        volume_list = get_instance_attr(instance_id, 'block_device_mappings')
        counter = 0
        instance_tag_value = instance_tag.get('Value')
        for volume in volume_list:
            if counter == 1:
                volume_postfix = '-volume-secondary'
            else:
                volume_postfix = '-volume-primary'
            tag = {'Key': 'Name',
                   'Value': node_name + volume_postfix}
            volume_tag = instance_tag
            volume_tag['Value'] = instance_tag_value + volume_postfix
            volume_id = volume.get('Ebs').get('VolumeId')
            create_tag(volume_id, tag)
            create_tag(volume_id, volume_tag)
            counter += 1
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with tagging AWS EC2 instance volumes: {}'.format(str(err)))


def get_instance_attr(instance_id, attribute_name):
    try:
        instances = ec2_resource.instances.filter(
            Filters=[{'Name': 'instance-id', 'Values': [instance_id]},
                     {'Name': 'instance-state-name', 'Values': ['running']}])
        for instance in instances:
            return getattr(instance, attribute_name)
        return ''
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS EC2 instance attributes: {}'.format(str(err)))


def get_ami_id(ami_name):
    try:
        image_id = ''
        response = ec2_client.describe_images(
            Filters=[
                {
                    'Name': 'name',
                    'Values': [ami_name]
                },
                {
                    'Name': 'virtualization-type', 'Values': ['hvm']
                },
                {
                    'Name': 'state', 'Values': ['available']
                },
                {
                    'Name': 'root-device-name', 'Values': ['/dev/sda1']
                },
                {
                    'Name': 'root-device-type', 'Values': ['ebs']
                },
                {
                    'Name': 'architecture', 'Values': ['x86_64']
                }
            ])
        response = response.get('Images')
        for i in response:
            image_id = i.get('ImageId')
        if image_id == '':
            raise Exception("Unable to find AWS AMI id with name: " + ami_name)
        return image_id
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS AMI ID: {}'.format(str(err)))


def remove_route_tables():
    try:
        rtables = ec2_client.describe_route_tables(Filters=[{'Name': 'tag-key', 'Values': [tag_name]}]).get('RouteTables')
        for rtable in rtables:
            if rtable:
                rtable_associations = rtable.get('Associations')
                rtable = rtable.get('RouteTableId')
                for association in rtable_associations:
                    ec2_client.disassociate_route_table(AssociationId=association.get('RouteTableAssociationId'))
                    print("Association {} has been removed".format(association.get('RouteTableAssociationId')))
                ec2_client.delete_route_table(RouteTableId=rtable)
                print("AWS Route table {} has been removed".format(rtable))
            else:
                print("There are no AWS route tables to remove")
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with removing AWS Route Tables: {}'.format(str(err)))


def remove_ec2():
    try:
        inst = ec2_resource.instances.filter(
            Filters=[{'Name': 'instance-state-name', 'Values': ['running', 'stopped', 'pending', 'stopping']},
                     {'Name': 'tag:{}'.format(tag_name), 'Values': ['{}'.format(args.service_base_name)]}])
        instances = list(inst)
        if instances:
            for instance in instances:
                ec2_client.terminate_instances(InstanceIds=[instance.id])
                waiter = ec2_client.get_waiter('instance_terminated')
                waiter.wait(InstanceIds=[instance.id])
                print("The instance {} has been terminated successfully".format(instance.id))
        else:
            print("There are no instances with '{}' tag to terminate".format(tag_name))
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with removing EC2 instances: {}'.format(str(err)))


def remove_internet_gateways(vpc_id, tag_value):
    try:
        ig_id = ''
        response = ec2_client.describe_internet_gateways(
            Filters=[
                {'Name': 'tag-key', 'Values': [tag_name]},
                {'Name': 'tag-value', 'Values': [tag_value]}]).get('InternetGateways')
        for i in response:
            ig_id = i.get('InternetGatewayId')
        ec2_client.detach_internet_gateway(InternetGatewayId=ig_id, VpcId=vpc_id)
        print("AWS Internet gateway {0} has been detached from VPC {1}".format(ig_id, vpc_id))
        ec2_client.delete_internet_gateway(InternetGatewayId=ig_id)
        print("AWS Internet gateway {} has been deleted successfully".format(ig_id))
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with removing AWS Internet gateways: {}'.format(str(err)))


def enable_auto_assign_ip(subnet_id):
    try:
        ec2_client.modify_subnet_attribute(MapPublicIpOnLaunch={'Value': True}, SubnetId=subnet_id)
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with enabling auto-assign of public IP addresses: {}'.format(str(err)))


def subnet_exist(return_id=False):
    try:
        subnet_created = False
        if args.vpc_id:
            filters = [{'Name': 'tag-key', 'Values': [tag_name]},
                       {'Name': 'tag-value', 'Values': [args.service_base_name]},
                       {'Name': 'vpc-id', 'Values': [args.vpc_id]}]
        else:
            filters = [{'Name': 'tag-key', 'Values': [tag_name]},
                       {'Name': 'tag-value', 'Values': [args.service_base_name]}]
        for subnet in ec2_resource.subnets.filter(Filters=filters):
            if return_id:
                return subnet.id
            subnet_created = True
        return subnet_created
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS Subnet: {}'.format(str(err)))


def sg_exist(return_id=False):
    try:
        sg_created = False
        for security_group in ec2_resource.security_groups.filter(
                Filters=[{'Name': 'group-name', 'Values': [args.service_base_name + "-sg"]}]):
            if return_id:
                return security_group.id
            sg_created = True
        return sg_created
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS Security group: {}'.format(str(err)))


def ec2_exist(return_id=False):
    try:
        ec2_created = False
        instances = ec2_resource.instances.filter(
            Filters=[{'Name': 'tag:Name', 'Values': [args.service_base_name + '-repository']},
                     {'Name': 'instance-state-name', 'Values': ['running', 'pending', 'stopping', 'stopped']}])
        for instance in instances:
            if return_id:
                return instance.id
            ec2_created = True
        return ec2_created
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS EC2 instance: {}'.format(str(err)))


def allocate_elastic_ip():
    try:
        tag = {"Key": tag_name, "Value": "{}".format(args.service_base_name)}
        name_tag = {"Key": "Name", "Value": "{}-eip".format(args.service_base_name)}
        allocation_id = ec2_client.allocate_address(Domain='vpc').get('AllocationId')
        create_tag(allocation_id, tag)
        create_tag(allocation_id, name_tag)
        print('AWS Elastic IP address has been allocated')
        return allocation_id
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with creating AWS Elastic IP: {}'.format(str(err)))


def release_elastic_ip():
    try:
        allocation_id = elastic_ip_exist(True)
        ec2_client.release_address(AllocationId=allocation_id)
        print("AWS Elastic IP address has been released.")
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with removing AWS Elastic IP: {}'.format(str(err)))


def associate_elastic_ip(instance_id, allocation_id):
    try:
        allocation_id = ec2_client.associate_address(InstanceId=instance_id, AllocationId=allocation_id).get('AssociationId')
        print("AWS Elastic IP address has been associated.")
        return allocation_id
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with associating AWS Elastic IP: {}'.format(str(err)))


def disassociate_elastic_ip(association_id):
    try:
        ec2_client.disassociate_address(AssociationId=association_id)
        print("AWS Elastic IP address has been disassociated.")
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with disassociating AWS Elastic IP: {}'.format(str(err)))


def elastic_ip_exist(return_id=False, return_parameter='AllocationId'):
    try:
        elastic_ip_created = False
        elastic_ips = ec2_client.describe_addresses(
            Filters=[
                {'Name': 'tag-key', 'Values': [tag_name]},
                {'Name': 'tag-value', 'Values': [args.service_base_name]}
            ]
        ).get('Addresses')
        for elastic_ip in elastic_ips:
            if return_id:
                return elastic_ip.get(return_parameter)
            elastic_ip_created = True
        return elastic_ip_created
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS Elastic IP: {}'.format(str(err)))


def create_route_53_record(hosted_zone_id, hosted_zone_name, subdomain, ip_address):
    try:
        route53_client.change_resource_record_sets(
            HostedZoneId=hosted_zone_id,
            ChangeBatch={
                'Changes': [
                    {
                        'Action': 'CREATE',
                        'ResourceRecordSet': {
                            'Name': "{}.{}".format(subdomain, hosted_zone_name),
                            'Type': 'A',
                            'TTL': 300,
                            'ResourceRecords': [
                                {
                                    'Value': ip_address
                                }
                            ]
                        }
                    }
                ]
            }
        )
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with creating AWS Route53 record: {}'.format(str(err)))


def remove_route_53_record(hosted_zone_id, hosted_zone_name, subdomain):
    try:
        for record_set in route53_client.list_resource_record_sets(
                HostedZoneId=hosted_zone_id).get('ResourceRecordSets'):
            if record_set['Name'] == "{}.{}.".format(subdomain, hosted_zone_name):
                for record in record_set['ResourceRecords']:
                    route53_client.change_resource_record_sets(
                        HostedZoneId=hosted_zone_id,
                        ChangeBatch={
                            'Changes': [
                                {
                                    'Action': 'DELETE',
                                    'ResourceRecordSet': {
                                        'Name': record_set['Name'],
                                        'Type': 'A',
                                        'TTL': 300,
                                        'ResourceRecords': [
                                            {
                                                'Value': record['Value']
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    )
        print("AWS Route53 record has been removed.")
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with removing AWS Route53 record: {}'.format(str(err)))


def get_instance_ip_address_by_id(instance_id, ip_address_type):
    try:
        instances = ec2_resource.instances.filter(
            Filters=[{'Name': 'instance-id', 'Values': [instance_id]},
                     {'Name': 'instance-state-name', 'Values': ['running']}])
        for instance in instances:
            return getattr(instance, ip_address_type)
    except Exception as err:
        traceback.print_exc(file=sys.stdout)
        print('Error with getting AWS EC2 instance IP address: {}'.format(str(err)))


if __name__ == "__main__":
    ec2_resource = boto3.resource('ec2', region_name=args.region)
    ec2_client = boto3.client('ec2', region_name=args.region)
    route53_client = boto3.client('route53')
    tag_name = args.service_base_name + '-Tag'
    pre_defined_vpc = False
    pre_defined_subnet = False
    pre_defined_sg = False
    if args.action == 'terminate':
        if args.hosted_zone_id and args.hosted_zone_name and args.subdomain:
            remove_route_53_record(args.hosted_zone_id, args.hosted_zone_name, args.subdomain)
        if elastic_ip_exist():
            try:
                association_id = elastic_ip_exist(True, 'AssociationId')
                disassociate_elastic_ip(association_id)
            except:
                print("AWS Elastic IP address isn't associated with instance or there is an error "
                      "with disassociating it")
            release_elastic_ip()
        if ec2_exist():
            remove_ec2()
        if sg_exist():
            remove_sgroups()
        if subnet_exist():
            remove_subnet()
        if vpc_exist():
            args.vpc_id = vpc_exist(True)
            remove_internet_gateways(args.vpc_id, args.service_base_name)
            remove_route_tables()
            remove_vpc(args.vpc_id)
    elif args.action == 'create':
        if not args.vpc_id and not vpc_exist():
            try:
                print('[CREATING AWS VPC]')
                args.vpc_id = create_vpc(args.vpc_cidr)
                enable_vpc_dns(args.vpc_id)
                rt_id = create_rt(args.vpc_id)
                pre_defined_vpc = True
            except:
                remove_internet_gateways(args.vpc_id, args.service_base_name)
                remove_route_tables()
                remove_vpc(args.vpc_id)
                sys.exit(1)
        elif not args.vpc_id and vpc_exist():
            args.vpc_id = vpc_exist(True)
        print('AWS VPC ID: {}'.format(args.vpc_id))
        if not args.subnet_id and not subnet_exist():
            try:
                print('[CREATING AWS SUBNET]')
                args.subnet_id = create_subnet(args.vpc_id, args.subnet_cidr)
                if args.network_type == 'public':
                    enable_auto_assign_ip(args.subnet_id)
                print("[ASSOCIATING ROUTE TABLE WITH THE SUBNET]")
                rt = get_route_table_by_tag(args.service_base_name)
                route_table = ec2_resource.RouteTable(rt)
                route_table.associate_with_subnet(SubnetId=args.subnet_id)
                pre_defined_subnet = True
            except:
                try:
                    remove_subnet()
                except:
                    print("AWS Subnet hasn't been created or there is an error with removing it")
                if pre_defined_vpc:
                    remove_internet_gateways(args.vpc_id, args.service_base_name)
                    remove_route_tables()
                    remove_vpc(args.vpc_id)
                sys.exit(1)
        if not args.subnet_id and subnet_exist():
            args.subnet_id = subnet_exist(True)
        print('AWS Subnet ID: {}'.format(args.subnet_id))
        if not args.sg_id and not sg_exist():
            try:
                print('[CREATING AWS SECURITY GROUP]')
                args.sg_id = create_security_group(args.service_base_name + '-sg', args.vpc_id)
                pre_defined_sg = True
            except:
                try:
                    remove_sgroups()
                except:
                    print("AWS Security Group hasn't been created or there is an error with removing it")
                    pass
                if pre_defined_subnet:
                    remove_subnet()
                if pre_defined_vpc:
                    remove_internet_gateways(args.vpc_id, args.service_base_name)
                    remove_route_tables()
                    remove_vpc(args.vpc_id)
                sys.exit(1)
        if not args.sg_id and sg_exist():
            args.sg_id = sg_exist(True)
        print('AWS Security Group ID: {}'.format(args.sg_id))

        if not ec2_exist():
            try:
                print('[CREATING AWS EC2 INSTANCE]')
                ec2_id = create_instance()
            except:
                try:
                    remove_ec2()
                except:
                    print("AWS EC2 instance hasn't been created or there is an error with removing it")
                if pre_defined_sg:
                    remove_sgroups()
                if pre_defined_subnet:
                    remove_subnet()
                if pre_defined_vpc:
                    remove_internet_gateways(args.vpc_id, args.service_base_name)
                    remove_route_tables()
                    remove_vpc(args.vpc_id)
                sys.exit(1)
        else:
            ec2_id = ec2_exist(True)

        if args.network_type == 'public':
            if not elastic_ip_exist():
                try:
                    print('[ALLOCATING AWS ELASTIC IP ADDRESS]')
                    allocate_elastic_ip()
                except:
                    try:
                        release_elastic_ip()
                    except:
                        print("AWS Elastic IP address hasn't been created or there is an error with removing it")
                    remove_ec2()
                    if pre_defined_sg:
                        remove_sgroups()
                    if pre_defined_subnet:
                        remove_subnet()
                    if pre_defined_vpc:
                        remove_internet_gateways(args.vpc_id, args.service_base_name)
                        remove_route_tables()
                        remove_vpc(args.vpc_id)
                    sys.exit(1)
            try:
                print('[ASSOCIATING AWS ELASTIC IP ADDRESS TO EC2 INSTANCE]')
                allocation_id = elastic_ip_exist(True)
                associate_elastic_ip(ec2_id, allocation_id)
            except:
                try:
                    association_id = elastic_ip_exist(True, 'AssociationId')
                    disassociate_elastic_ip(association_id)
                except:
                    print("AWS Elastic IP address hasn't been associated or there is an error with disassociating it")
                release_elastic_ip()
                remove_ec2()
                if pre_defined_sg:
                    remove_sgroups()
                if pre_defined_subnet:
                    remove_subnet()
                if pre_defined_vpc:
                    remove_internet_gateways(args.vpc_id, args.service_base_name)
                    remove_route_tables()
                    remove_vpc(args.vpc_id)
                sys.exit(1)

        if args.network_type == 'public':
            ec2_ip_address = get_instance_ip_address_by_id(ec2_id, 'public_ip_address')
        else:
            ec2_ip_address = get_instance_ip_address_by_id(ec2_id, 'private_ip_address')

        if args.hosted_zone_id and args.hosted_zone_name and args.subdomain:
            try:
                print('[CREATING AWS ROUTE53 RECORD]')
                create_route_53_record(args.hosted_zone_id, args.hosted_zone_name, args.subdomain, ec2_ip_address)
            except:
                try:
                    remove_route_53_record(args.hosted_zone_id, args.hosted_zone_name, args.subdomain)
                except:
                    print("AWS Route53 record hasn't been created or there is an error with removing it")
                if args.network_type == 'public':
                    association_id = elastic_ip_exist(True, 'AssociationId')
                    disassociate_elastic_ip(association_id)
                    release_elastic_ip()
                remove_ec2()
                if pre_defined_sg:
                    remove_sgroups()
                if pre_defined_subnet:
                    remove_subnet()
                if pre_defined_vpc:
                    remove_internet_gateways(args.vpc_id, args.service_base_name)
                    remove_route_tables()
                    remove_vpc(args.vpc_id)
                sys.exit(1)

        print('[SUMMARY]')
        print("AWS VPC ID: {0}".format(args.vpc_id))
        print("AWS Subnet ID: {0}".format(args.subnet_id))
        print("AWS Security Group ID: {0}".format(args.sg_id))
        print("AWS EC2 ID: {0}".format(ec2_id))
        print("AWS EC2 IP address: {0}".format(ec2_ip_address))
        if args.hosted_zone_id and args.hosted_zone_name and args.subdomain:
            print("DNS name: {0}".format(args.subdomain + '.' + args.hosted_zone_name))

    else:
        print('Invalid action: {}'.format(args.action))

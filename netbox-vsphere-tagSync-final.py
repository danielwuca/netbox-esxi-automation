import urllib3
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import ssl
from pyVim.task import WaitForTask
import os
import requests
import pandas as pd
import numpy as np
import pynetbox

import com.vmware
# vsphere python automation library
from com.vmware.vcenter_client import VM
from com.vmware.vcenter_client import Datacenter
from com.vmware.vcenter_client import Network
from com.vmware.vcenter_client import Datastore
from com.vmware.vcenter_client import Cluster
from com.vmware.vcenter.vm.hardware_client import (Cpu, Memory, Ethernet, Cdrom, Disk)
from com.vmware.cis.tagging_client import (Category, CategoryModel, Tag, TagAssociation, TagModel)
from vmware.vapi.vsphere.client import create_vsphere_client
from vmware.vapi.bindings.stub import StubFactory, StubConfiguration
from vmware.vapi.lib.connect import get_requests_connector
from vmware.vapi.security.session import create_session_security_context
from vmware.vapi.stdlib.client.factories import StubConfigurationFactory
from vmware.vapi.security.session import create_session_security_context
from vmware.vapi.security.user_password import create_user_password_security_context
from vmware.vapi.stdlib.client.factories import StubConfigurationFactory
from vmware.vapi.lib.connect import get_requests_connector

# static
NETBOX_VM_API = os.getenv('NETBOX_VM_API')
NETBOX_CLUSTER_API = os.getenv('NETBOX_CLUSTER_API')
NETBOX_INTERFACES_API = os.getenv('NETBOX_INTERFACES_API')
Netbox_Token = os.getenv('Netbox_Token')
ESXI_IP = os.getenv('ESXI_IP')
USERNAME_ESXI = os.getenv('USERNAME_ESXI')
PASSWORD = os.getenv('PASSWORD')
NETBOX_URL = os.getenv('NETBOX_URL')
netbox = pynetbox.api(NETBOX_URL, token=Netbox_Token)

session = requests.session()
session.verify = False
session.trust_env = False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

client = create_vsphere_client(server=ESXI_IP, username=USERNAME_ESXI, password=PASSWORD, session=session)


# step one sync tag step two assign tag
# step one
# print tag info test
def printing_infra():
    tags_ids = client.tagging.Tag.list()
    existing_tag_names = [client.tagging.Tag.get(tag_id).name for tag_id in tags_ids]
    print(existing_tag_names)

    category_ids = client.tagging.Category.list()
    category_names = [client.tagging.Category.get(category_id).name for category_id in category_ids]
    print(category_names)

    all_tags = [client.tagging.Tag.get(tag_id) for tag_id in tags_ids]
    category_to_tags = {}
    for category_id in category_ids:
        category = client.tagging.Category.get(category_id)
        category_name = category.name
        category_to_tags[category_name] = []

        for tag in all_tags:
            if tag.category_id == category_id:
                category_to_tags[category_name].append(tag.name)

    print(category_to_tags)


# create syncing from netbox to vsphere
def sync_tags_to_vsphere(category_mapping):
    netbox_tags = list(netbox.extras.tags.all())
    netbox_vm_roles = list(netbox.dcim.device_roles.all()) 
    category_ids = client.tagging.Category.list()
    tags_ids = client.tagging.Tag.list()
    vsphere_categories = {client.tagging.Category.get(category_id).name: category_id for category_id in category_ids}
    vsphere_tags = {client.tagging.Tag.get(tag_id).name: tag_id for tag_id in tags_ids}
    keyword_matched_tags = set()

    combine_items = [{'item': item, 'type': 'tag'} for item in netbox_tags] + \
                    [{'item': role, 'type': 'role'} for role in netbox_vm_roles]

    for entry in combine_items:
        netbox_item = entry['item']
        tag_name = netbox_item.name
        tag_description = getattr(netbox_item, 'description',
                                  netbox_item.name)
        item_type = entry['type']
        category_matched = False

        for keyword, category_name in category_mapping.items():
            if keyword in tag_description.lower():
                vsphere_category_name = category_name
                category_matched = True
                break

        if not category_matched and item_type == 'role':
            vsphere_category_name = 'Server Type'  # Default category for roles

        if not category_matched and item_type == 'tag':
            continue  # Skip tags without keyword matches

        category_id = vsphere_categories[vsphere_category_name]

        if tag_name not in vsphere_tags:
            tag_spec = client.tagging.Tag.CreateSpec()
            tag_spec.name = tag_name
            tag_spec.description = tag_description
            tag_spec.category_id = category_id
            client.tagging.Tag.create(tag_spec)
            keyword_matched_tags.add(tag_name)
        else:
            tag_id = vsphere_tags[tag_name]
            update_spec = client.tagging.Tag.UpdateSpec()
            update_spec.description = tag_description
            update_spec.category_id = category_id
            client.tagging.Tag.update(tag_id, update_spec)
            keyword_matched_tags.add(tag_name)

    return keyword_matched_tags


def assign_tags_to_vms(keyword_matched_tags):
    netbox_vms = netbox.virtualization.virtual_machines.all()
    vsphere_vm_ids = client.vcenter.VM.list()
    tags_ids = client.tagging.Tag.list()
    vsphere_tags = {client.tagging.Tag.get(tag_id).name: tag_id for tag_id in tags_ids}

    vsphere_vm_summaries = client.vcenter.VM.list()
    vsphere_vms = {client.vcenter.VM.get(vm_summary.vm).name: vm_summary.vm for vm_summary in vsphere_vm_summaries}

    for netbox_vm in netbox_vms:
        vsphere_vm_id = vsphere_vms.get(netbox_vm.name)
        if vsphere_vm_id:
            netbox_vm_tags = [tag.name for tag in netbox_vm.tags if tag.name in keyword_matched_tags]
            if hasattr(netbox_vm, 'role') and netbox_vm.role and netbox_vm.role.name in keyword_matched_tags:
                netbox_vm_tags.append(netbox_vm.role.name)

            for tag_name in netbox_vm_tags:
                if tag_name in vsphere_tags:
                    tag_id = vsphere_tags[tag_name]
                    client.tagging.TagAssociation.attach(tag_id=tag_id,
                                                         object_id={'id': vsphere_vm_id, 'type': 'VirtualMachine'})
                    print(f"assign tag {tag_name} to VM {netbox_vm.name}")
        #else:
            #print(f"VM {netbox_vm.name} not found in vSphere")


def main():
    category_mapping = {
        'environment': 'Environment',
        'application': 'Application Group'
    }
    keyword_matched_tags = sync_tags_to_vsphere(category_mapping)
    assign_tags_to_vms(keyword_matched_tags)


if __name__ == "__main__":
    main()

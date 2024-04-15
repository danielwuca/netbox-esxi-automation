import ssl
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import requests
import urllib3
import pynetbox

# Disable SSL warnings (not recommended for production)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# User inputs for NetBox and vSphere
NETBOX_URL = input("Enter NetBox URL: ")
Netbox_Token = input("Enter NetBox API Token: ")
ESXI_IP = input("Enter ESXi IP: ")
USERNAME_ESXI = input("Enter ESXi Username: ")
PASSWORD = input("Enter ESXi Password: ")
CLUSTER_NAME = input("Enter Cluster Name: ")

# Initialize NetBox API client
netbox = pynetbox.api(NETBOX_URL, token=Netbox_Token)
session = requests.Session()
session.verify = False
netbox.http_session = session

def check_vm_vcenter(si, vm_name):
    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    for vm in container.view:
        if vm.name == vm_name:
            return True
    return False

def create_vm_esxi(si, vm_name, memoryGB, numCPUs, datastore_name, disk_size_gb):
    content = si.RetrieveContent()
    datacenter = content.rootFolder.childEntity[0]
    vm_folder = datacenter.vmFolder
    resource_pool = datacenter.hostFolder.childEntity[0].resourcePool

    # Assume a single datastore here; modify as needed
    datastore = [ds for ds in datacenter.datastore if ds.name == datastore_name][0]

    vm_config = vim.vm.ConfigSpec(
        name=vm_name,
        memoryMB=int(memoryGB * 1024),
        numCPUs=int(numCPUs),
        guestId='otherGuest',
        files=vim.vm.FileInfo(vmPathName=f'[{datastore_name}]'),
    )

    disk_spec = vim.vm.device.VirtualDeviceSpec()
    disk_spec.fileOperation = "create"
    disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    disk_spec.device = vim.vm.device.VirtualDisk()
    disk_spec.device.backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
    disk_spec.device.backing.diskMode = 'persistent'
    disk_spec.device.backing.fileName = f'[{datastore_name}] {vm_name}/{vm_name}.vmdk'
    disk_spec.device.unitNumber = 0
    disk_spec.device.capacityInKB = disk_size_gb * 1024 * 1024
    disk_spec.device.controllerKey = 1000

    vm_config.deviceChange = [disk_spec]

    # Create VM
    task = vm_folder.CreateVM_Task(config=vm_config, pool=resource_pool)
    WaitForTask(task)

def sync_vms_in_cluster(netbox, cluster_name, client, si):
    cluster = netbox.virtualization.clusters.get(name=cluster_name)
    if cluster is None:
        print(f"No cluster found with the name '{cluster_name}'")
        return

    vms_in_cluster = netbox.virtualization.virtual_machines.filter(cluster_id=cluster.id)
    for vm in vms_in_cluster:
        vm_name = vm.name
        memory_val = vm.memory
        cpu_val = vm.vcpus
        disk_val = vm.disk

        if not check_vm_vcenter(si, vm_name):
            print(f"Creating VM {vm_name} in vSphere...")
            create_vm_esxi(si, vm_name, memory_val, cpu_val, "DatastoreName", disk_val)
        else:
            print(f"VM {vm_name} already exists in vSphere.")

def main():
    context = ssl._create_unverified_context()
    si = SmartConnect(host=ESXI_IP, user=USERNAME_ESXI, pwd=PASSWORD, sslContext=context)
    try:
        sync_vms_in_cluster(netbox, CLUSTER_NAME, None, si)
    finally:
        Disconnect(si)

if __name__ == "__main__":
    main()


# version 2
def sync_tags_to_vsphere(category_mapping):
    netbox_tags = list(netbox.extras.tags.all())  # Tags from NetBox
    netbox_vm_roles = list(netbox.dcim.device_roles.all())  # Roles from NetBox, definitely roles
    category_ids = client.tagging.Category.list()
    tags_ids = client.tagging.Tag.list()
    vsphere_categories = {client.tagging.Category.get(category_id).name: category_id for category_id in category_ids}
    vsphere_tags = {client.tagging.Tag.get(tag_id).name: tag_id for tag_id in tags_ids}

    # Combine tags and roles but maintain awareness of their origin
    combine_items = [{'item': item, 'type': 'tag'} for item in netbox_tags] + \
                    [{'item': role, 'type': 'role'} for role in netbox_vm_roles]

    for entry in combine_items:
        netbox_item = entry['item']
        tag_name = netbox_item['name']
        tag_description = netbox_item.get('description', netbox_item['name'])
        item_type = entry['type']
        category_matched = False

        for keyword, category_name in category_mapping.items():
            if keyword in tag_description.lower():
                vsphere_category_name = category_name
                category_matched = True
                break

        if not category_matched and item_type == 'role':
            vsphere_category_name = 'Server Type'  # Default category for roles without specific keywords

        if not category_matched and item_type == 'tag':
            continue  # Skip tags without keyword matches

        category_id = vsphere_categories[vsphere_category_name]
        
        if tag_name not in vsphere_tags:
            tag_spec = client.tagging.Tag.CreateSpec()
            tag_spec.name = tag_name
            tag_spec.description = tag_description
            tag_spec.category_id = category_id
            client.tagging.Tag.create(tag_spec)
        else:
            tag_id = vsphere_tags[tag_name]
            update_spec = client.tagging.Tag.UpdateSpec()
            update_spec.description = tag_description
            update_spec.category_id = category_id
            client.tagging.Tag.update(tag_id, update_spec)

def main():
    category_mapping = {
        'environment': 'Environment',
        'application': 'Application Group'
    }

    sync_tags_to_vsphere(category_mapping)
    assign_tags_to_vms()

if __name__ == "__main__":
    main()


# version 3
def sync_tags_to_vsphere(category_mapping):
    ...
    keyword_matched_tags = set()  # To track tags created based on keywords
    
    for entry in combine_items:
        ...
        if category_matched:
            if tag_name not in vsphere_tags:
                ...
                client.tagging.Tag.create(tag_spec)
            else:
                ...
                client.tagging.Tag.update(tag_id, update_spec)
            keyword_matched_tags.add(tag_name)  # Track this tag as keyword matched
    
    return keyword_matched_tags  # Return the set of keyword-matched tags

def assign_tags_to_vms(keyword_matched_tags):
    ...
    for netbox_vm in netbox_vms:
        vsphere_vm_id = vsphere_vms.get(netbox_vm.name)
        if vsphere_vm_id:
            netbox_vm_tags = [tag.name for tag in netbox_vm.tags if tag.name in keyword_matched_tags]
            if hasattr(netbox_vm, 'role') and netbox_vm.role and netbox_vm.role.name in keyword_matched_tags:
                netbox_vm_tags.append(netbox_vm.role.name)
            
            for tag_name in netbox_vm_tags:
                if tag_name in vsphere_tags:
                    tag_id = vsphere_tags[tag_name]
                    client.tagging.TagAssociation.attach(tag_id=tag_id, object_id={'id': vsphere_vm_id, 'type': 'VirtualMachine'})
                    print(f"assign tag {tag_name} to VM {netbox_vm.name}")
        else:
            print(f"vm {netbox_vm.name} not found in vsphere")

def main():
    category_mapping = {
        'environment': 'Environment',
        'application': 'Application Group'
    }
    keyword_matched_tags = sync_tags_to_vsphere(category_mapping)
    assign_tags_to_vms(keyword_matched_tags)

if __name__ == "__main__":
    main()

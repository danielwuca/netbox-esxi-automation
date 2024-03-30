import ssl
import pynetbox
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from vmware.vapi.vsphere.client import create_vsphere_client
from com.vmware.vcenter_client import VM
from com.vmware.vcenter.vm.hardware_client import (Cpu, Memory, Ethernet, Disk, Cdrom)
from com.vmware.cis.tagging_client import (Category, CategoryModel, Tag, TagAssociation, TagModel)
from vmware.vapi.bindings.stub import StubFactory, StubConfiguration
from vmware.vapi.lib.connect import get_requests_connector
from vmware.vapi.stdlib.client.factories import StubConfigurationFactory

# Static variables (fill in with your details)
NETBOX_VM_API = 'your_netbox_vm_api'
NETBOX_CLUSTER_API = 'your_netbox_cluster_api'
NETBOX_INTERFACES_API = 'your_netbox_interfaces_api'
myToken = 'your_netbox_token'
ESXI_IP = 'your_esxi_ip'
USERNAME = 'your_esxi_username'
PASSWORD = 'your_esxi_password'
NETBOX_URL = 'your_netbox_url'
netbox = pynetbox.api(url=NETBOX_URL, token=myToken)

# Get cluster information from vSphere
def get_cluster_id_vsphere():
    context = ssl._create_unverified_context()
    si = SmartConnect(host=ESXI_IP, user=USERNAME, pwd=PASSWORD, sslContext=context)
    content = si.RetrieveContent()
    for datacenter in content.rootFolder.childEntity:
        for cluster in datacenter.hostFolder.childEntity:
            cluster_name = cluster.name
    cluster = netbox.virtualization.clusters.get(name=cluster_name)
    if cluster:
        return cluster.id
    return None

# Get VM information from NetBox
def get_vm_obj_netbox():
    vms_list = []
    vms = netbox.virtualization.virtual_machines.filter(cluster_id=get_cluster_id_vsphere())
    for vm in vms:
        vm_obj = {
            "name": vm.name,
            "cluster": vm.cluster.name,
            "role": vm.role.name if vm.role else None,
            "tags": [tag.name for tag in vm.tags],
            "memoryGB": vm.memory,  # Assuming memory is in MB in NetBox
            "numCPUs": vm.vcpus,
            "disk_size_gb": vm.disk,  # Assuming disk size is in MB in NetBox
            "os_name": vm.custom_fields['os_name'] if 'os_name' in vm.custom_fields else 'DEBIAN_9_64',
            "datastore_name": vm.custom_fields['datastore_name'] if 'datastore_name' in vm.custom_fields else None,
            "network_name": vm.custom_fields['network_name'] if 'network_name' in vm.custom_fields else None
        }
        vms_list.append(vm_obj)
    return vms_list

# Get or create a cluster in vSphere
def get_or_create_cluster(client, datacenter, cluster_name):
    clusters = client.vcenter.Cluster.list(VM.Cluster.FilterSpec(names=set([cluster_name]), datacenters=set([datacenter])))
    if clusters:
        return clusters[0].cluster
    else:
        cluster_spec = VM.Cluster.CreateSpec(name=cluster_name, folder=client.vcenter.Folder.get(client.vcenter.VM.get(datacenter=datacenter).home))
        cluster = client.vcenter.Cluster.create(cluster_spec)
        print(f"Cluster '{cluster_name}' created with ID: {cluster}")
        return cluster

# Determine the tag category based on the tag description
def get_tag_category(tag_name, tag_description):
    keyword_to_category = {
        'Application': 'Application Group',
        'Environment': 'Environment',
    }
    for keyword, category in keyword_to_category.items():
        if keyword.lower() in tag_description.lower():
            return category
    return 'Server Type'

# Create a VM in vSphere
def create_vm_vsphere(vm_name, memoryGB, numCPUs, cluster_name, disk_size_gb, tags, os_name, datastore_name=None, network_name=None):
    client = create_vsphere_client(server=ESXI_IP, username=USERNAME, password=PASSWORD)
    datacenter = client.vcenter.Datacenter.list(VM.Datacenter.FilterSpec(names=set(['DatacenterName'])))[0].datacenter
    if datastore_name is None:
        datastore_name = 'DatastoreName'  # Fallback to default datastore name
    if network_name is None:
        network_name = 'NetworkName'  # Fallback to default network name

    datastore = client.vcenter.Datastore.list(VM.Datastore.FilterSpec(names=set([datastore_name]), datacenters=set([datacenter])))[0].datastore
    network = client.vcenter.Network.list(VM.Network.FilterSpec(names=set([network_name]), datacenters=set([datacenter])))[0].network
    cluster = client.vcenter.Cluster.list(VM.Cluster.FilterSpec(names=set([cluster_name]), datacenters=set([datacenter])))[0].cluster

    datastore_info = client.vcenter.Datastore.get(datastore)
    free_space_gb = datastore_info.free_space / (1024 ** 3)
    if disk_size_gb > free_space_gb:
        print(f"Insufficient disk space in datastore '{datastore_name}' for VM '{vm_name}'.")
        return False

    vm_create_spec = VM.CreateSpec(
        name=vm_name,
        guest_os=os_name,
        placement=VM.PlacementSpec(folder=client.vcenter.Folder.get(client.vcenter.VM.get(datacenter=datacenter).home), cluster=cluster, datastore=datastore),
        hardware=VM.HardwareSpec(
            cpu=VM.CpuSpec(count=numCPUs),
            memory=VM.MemorySpec(size_mb=memoryGB * 1024),
            nics=[Ethernet.CreateSpec(type=Ethernet.BackingType.STANDARD_PORTGROUP, network=network)],
            disks=[Disk.CreateSpec(type=Disk.HostBusAdapterType.SCSI, backing=Disk.BackingSpec(type=Disk.BackingType.VMDK_FILE, vmdk_file=vm_name + '.vmdk', datastore=datastore), new_vmdk=Disk.VmdkCreateSpec(capacity=disk_size_gb * 1024))],
            cdroms=[Cdrom.CreateSpec(type=Cdrom.BackingType.ISO_FILE, iso_file='')]
        )
    )
    vm = client.vcenter.VM.create(vm_create_spec)
    print(f"VM '{vm_name}' created with ID: {vm}")

    session = client._session_id
    connector = get_requests_connector(session_id=session, url=f'https://{ESXI_IP}/api')
    stub_config = StubConfigurationFactory.new_std_configuration(connector)
    stub_factory = StubFactory(stub_config)
    category_svc = stub_factory.create_stub(Category)
    tag_svc = stub_factory.create_stub(Tag)
    tag_assoc_svc = stub_factory.create_stub(TagAssociation)

    for tag in tags:
        category_name = get_tag_category(tag['name'], tag['description'])
        category_id = None
        for category in category_svc.list():
            if category_svc.get(category).name == category_name:
                category_id = category
                break
        if not category_id:
            category_spec = CategoryModel(name=category_name, description=f'Category for {vm_name}', cardinality=CategoryModel.Cardinality.SINGLE)
            category_id = category_svc.create(category_spec)

        tag_id = None
        for existing_tag in tag_svc.list():
            if tag_svc.get(existing_tag).name == tag['name']:
                tag_id = existing_tag
                break
        if not tag_id:
            tag_spec = TagModel(name=tag['name'], description=f'Tag for {vm_name}', category_id=category_id)
            tag_id = tag_svc.create(tag_spec)

        tag_assoc_svc.attach(tag_id=tag_id, object_id={'id': vm, 'type': 'VirtualMachine'})
    print(f"Tags synchronized for VM '{vm_name}'")

def main():
    client = create_vsphere_client(server=ESXI_IP, username=USERNAME, password=PASSWORD)
    datacenter = client.vcenter.Datacenter.list(VM.Datacenter.FilterSpec(names=set(['DatacenterName'])))[0].datacenter

    vms = get_vm_obj_netbox()
    for vm in vms:
        cluster = get_or_create_cluster(client, datacenter, vm['cluster'])
        create_vm_vsphere(
            vm_name=vm['name'],
            memoryGB=vm['memoryGB'],
            numCPUs=vm['numCPUs'],
            cluster_name=vm['cluster'],
            disk_size_gb=vm['disk_size_gb'],
            tags=vm['tags'],
            os_name=vm['os_name'],
            datastore_name=vm.get('datastore_name'),
            network_name=vm.get('network_name')
        )

if __name__ == "__main__":
    main()

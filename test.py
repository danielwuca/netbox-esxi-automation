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

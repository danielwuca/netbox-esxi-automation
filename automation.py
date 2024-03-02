# import importlib.metadata
# from importlib.metadata import version
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import ssl
from pyVim.task import WaitForTask
import os
import requests
import pandas as pd
import numpy as np
import pynetbox
import urllib3
# import win32com.client as win32
from email.message import EmailMessage
import smtplib
#from dotenv import load_dotenv

#load_dotenv()

# static url
NETBOX_VM_API = os.getenv('NETBOX_VM_API')
NETBOX_CLUSTER_API = os.getenv('NETBOX_CLUSTER_API')
NETBOX_INTERFACES_API = os.getenv('NETBOX_INTERFACES_API')
Netbox_Token = os.getenv('Netbox_Token')
ESXI_IP = os.getenv('ESXI_IP')
USERNAME_ESXI = os.getenv('USERNAME_ESXI')
PASSWORD = os.getenv('PASSWORD')
NETBOX_URL = os.getenv('NETBOX_URL')

my_session = requests.Session()
my_session.verify = False
urllib3.disable_warnings()
# pynetbox
netbox = pynetbox.api(NETBOX_URL, token=Netbox_Token)
my_session.get(NETBOX_URL)
netbox.http_session = my_session

# site map
site_map1 = ['YF', 'LI', 'TH', 'AD', 'CA', 'GE', 'HA', 'KE', 'LO', 'MI', 'FL', 'MU', 'NI', 'NB', 'OT', 'PS', 'RE', 'SU',
             'TO', 'WI', 'OS', 'WA']


# get jenkins user input parameter
vm_name = os.getenv('vm_name')
cluster_name = os.getenv('cluster_name')
role_name = os.getenv('role_name')
platform_name = os.getenv('platform_name')
vcpus_val = os.getenv('vcpus_val')
memory_val = os.getenv('memory_val')
disk_val = os.getenv('disk_val')
tenant_name = os.getenv('tenant_name')
sender = "moh.vmcreationnotify@outlook.com"
recipient = os.getenv('user_email')

# data: vm information in netbox / data type: list
# Warning! has maximum page size limited using rest api, please use pynetbox instead
def get_netbox_vms():
    head = {
        'Authorization': 'token {}'.format(Netbox_Token),
        'Content-Type': 'application/json',
    }

    try:
        res = requests.get(NETBOX_VM_API, headers=head)
        res.raise_for_status()
        result_json = res.json()['results']
        return result_json
    except requests.HTTPError as e:
        print(f"HTTP Error: {e}")
        return []
    except requests.RequestException as e:
        print(f'Error fetching data from NetBox: {e}')
        return []


# pynetbox all vm names list
vms = netbox.virtualization.virtual_machines.all()
# vm_name_list = [vm.name for vm in vms]


# store tag
vm_tag = {vm.name: [tag.name for tag in vm.tags] for vm in vms}


# VM exists in Netbox?
def check_vm_netbox(vm_name):
    if netbox.virtualization.virtual_machines.get(name=vm_name):
        return True
    return False


# VM exists in Vcenter?
def check_vm_vcenter(si, vm_name):
    content = si.RetrieveContent()
    container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    for vm in container.view:
        if vm.name == vm_name:
            return True
    return False


# create vm in netbox
def create_vm_netbox(vm_name, cluster_name, role_name, platform_name, vcpus_val, memory_val, disk_val, tenant_name):
    try:
        role = netbox.dcim.device_roles.get(name=role_name)
        platform = netbox.dcim.platforms.get(name=platform_name)
        cluster = netbox.virtualization.clusters.get(name=cluster_name)
        tenant = netbox.tenancy.tenants.get(name=tenant_name)

        new_vm = netbox.virtualization.virtual_machines.create(
            name=vm_name,
            cluster=cluster.id,
            role=role.id,
            platform=platform.id,
            status='active',
            vcpus=vcpus_val,
            memory=memory_val,
            disk=disk_val,
            tenant=tenant.id,
        )
        print(f"VM name: {new_vm.name} (id: {new_vm.id}) created successfully in netbox")
    except Exception as e:
        print(f"Error creating VM {vm_name} in netbox: {e}")


# create interfaces and assign ip to interface
def create_interface_assign_ip(new_vm, interface_name):
    try:
        vm_interface = netbox.virtualization.interfaces.create(
            virtual_machine=new_vm.id,
            name=interface_name,
        )
    except Exception as e:
        print(f"Error creating interface {interface_name} in netbox: {e}")


# create ip and assign to interface
def create_ip_assign(ip_address, vm_interface):
    try:
        new_ip = netbox.ipam.ip_addresses.create(
            address=ip_address,
            assigned_object_type='virtualization.vminterface',
            assigned_object_id=vm_interface.id,
        )
    except Exception as e:
        print(f"Error create and assign ip to the interface : {e}")


# ESX has enough disk space/mem/cpu?
def check_esxi_resource(si, memoryGB, cpu, diskGB):
    content = si.RetrieveContent()
    for datacenter in content.rootFolder.childEntity:
        for cluster in datacenter.hostFolder.childEntity:
            for host in cluster.host:
                summary = host.summary
                # memory remain (GB)
                memory_total = summary.hardware.memorySize / (1024 ** 3)
                memory_used = summary.quickStats.overallMemoryUsage / 1024
                memory_free = memory_total - memory_used
                # cpu remain (Mhz)
                cpu_total = summary.hardware.cpuMhz * summary.hardware.numCpuCores
                cpu_used = summary.quickStats.overallMemoryUsage
                cpu_free = cpu_total - cpu_used
                # disk size remain (GB)
                if memory_free > memoryGB and cpu_free > cpu:
                    for datastore in cluster.datastore:
                        ds_summary = datastore.summary
                        disk_total = ds_summary.capacity / (1024 ** 3)
                        disk_free = ds_summary.freeSpace / (1024 ** 3)
                        if disk_free > diskGB:
                            return True
    return False


# Create VM in ESXI/Vcenter
def create_vm_esxi(si, vm_name, memoryGB, numCPUs, datastore_name, disk_size_gb):
    content = si.RetrieveContent()
    datacenter = content.rootFolder.childEntity[0]
    vm_folder = datacenter.vmFolder
    resource_pool = datacenter.hostFolder.childEntity[0].resourcePool
    datastore = datacenter.datastoreFolder.childEntity[0]

    vm_config = vim.vm.ConfigSpec(
        name=vm_name,
        memoryMB=int(memoryGB * 1024),
        numCPUs=int(numCPUs),
        files=vim.vm.FileInfo(vmPathName=f'[{datastore_name}]'),
    )

    scsi_ctrl_spec = vim.vm.device.VirtualDeviceSpec()
    scsi_ctrl_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    scsi_ctrl = vim.vm.device.VirtualLsiLogicController()
    scsi_ctrl.key = 1000
    scsi_ctrl.busNumber = 0
    scsi_ctrl.sharedBus = vim.vm.device.VirtualSCSIController.Sharing.noSharing
    scsi_ctrl_spec.device = scsi_ctrl

    disk_spec = vim.vm.device.VirtualDeviceSpec()
    disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
    disk_spec.fileOperation = vim.vm.device.VirtualDeviceSpec.FileOperation.create
    disk_spec.device = vim.vm.device.VirtualDisk()
    disk_spec.device.backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
    disk_spec.device.backing.fileName = f'[{datastore_name}] {vm_name}/{vm_name}.vmdk'
    disk_spec.device.backing.diskMode = 'persistent'
    disk_spec.device.unitNumber = 0
    disk_spec.device.controllerKey = scsi_ctrl.key
    disk_spec.device.capacityInKB = disk_size_gb * 1024 * 1024

    vm_config.deviceChange = [scsi_ctrl_spec, disk_spec]

    task = vm_folder.CreateVM_Task(config=vm_config, pool=resource_pool)
    #     WaitForTask(task)
    task_info = task.info
    while task_info.state == vim.TaskInfo.State.running:
        task_info = task.info
    if task_info.state == vim.TaskInfo.State.success:
        print(f"VM {vm_name} created successfully in esxi")
    else:
        print(f'Error creating VM {vm_name}: {task_info.error}')


# naming convention
def name_validation(name):
    if name[:3].upper() != 'EHS' or name[3:4].upper() not in ['D', 'B', 'P', 'E', 'X', 'Y', 'G', 'T', 'V', 'Z'] or \
            name[4:5].upper() not in ['I', 'O'] or name[5:7].upper() not in site_map1:
        return False
    else:
        return True


# email send
def email_notification(subject, message):
    email = EmailMessage()
    email["From"] = sender
    email["To"] = recipient
    email["Subject"] = subject
    email.set_content(message)

    smtp = smtplib.SMTP("smtp-mail.outlook.com", port=587)
    smtp.starttls()
    smtp.login(sender, "Password01!")
    smtp.sendmail(sender, recipient, email.as_string())
    smtp.quit()

# main function
def main():
    si = None

    try:
        context = ssl._create_unverified_context()
        si = SmartConnect(host=ESXI_IP, user=USERNAME_ESXI, pwd=PASSWORD, sslContext=context)
    except Exception as e:
        print(f"Cannot connect to esxi: {e}")
        return

    try:
        while not name_validation(vm_name):
            print('Does not meet the naming convention, try again...')
            # email_notification('Naming convention error', 'Please follow the naming convention rule!')
            return

        if check_vm_netbox(vm_name):
            print('Already existed in netbox let me check if it is existed in vcenter...')
            if check_vm_vcenter(si, vm_name):
                print('Already existed in vcenter!')
                # email_notification('Already existed', 'VM already exists in vcenter and netbox!')
                return
            else:
                print('Not exist in vcenter let me create it...')
                grab_vm = netbox.virtualization.virtual_machines.get(name=vm_name)
                grab_memory = grab_vm.memory
                grab_cpus = grab_vm.vcpus
                grab_disk = grab_vm.disk
                if check_esxi_resource(si, grab_memory, grab_cpus, grab_disk):
                    create_vm_esxi(si, vm_name, grab_memory, grab_cpus, "strg-01", grab_disk)
                else:
                    print('Warning!! Not enough space, cpu and disk in esxi, please reconfigure and try again...')
                    # email_notification('Vcenter space not enough warning', 'Please reconfigure and try again!')
                    return
        else:
            print('VM does not exist in netbox! lets create:')
            create_vm_netbox(vm_name, cluster_name, role_name, platform_name, vcpus_val, memory_val, disk_val,
                             tenant_name)
            grab_vm = netbox.virtualization.virtual_machines.get(name=vm_name)
            grab_memory = grab_vm.memory
            grab_cpus = grab_vm.vcpus
            grab_disk = grab_vm.disk
            if check_esxi_resource(si, grab_memory, grab_cpus, grab_disk):
                create_vm_esxi(si, vm_name, grab_memory, grab_cpus, "strg-01", grab_disk)
            else:
                print('Warning!! Not enough space and cpu in esxi, please reconfigure and try again...')
                email_notification('Vcenter space not enough warning', 'Please reconfigure and try again!')
                return
    finally:
        if si:
            Disconnect(si)


if __name__ == "__main__":
    main()
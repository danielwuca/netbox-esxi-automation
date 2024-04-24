from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import ssl
ESXI_IP = ''
USERNAME = ''
PASSWORD = ''
 
si = None
try:
    context = ssl._create_unverified_context()
    si = SmartConnect(host=ESXI_IP, user=USERNAME, pwd=PASSWORD, sslContext=context)
except Exception as e:
    print(f"Cannot connect to esxi: {e}")
 
content = si.RetrieveContent()
container = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
vm_info_list = []
 
for vm in container.view:
    vm_summary = vm.summary
    vm_info = {
        'vm_name': vm_summary.config.name,
        'host_name': vm_summary.guest.hostName,
        'ip_address': vm_summary.guest.ipAddress,
    }
    vm_info_list.append(vm_info)
Disconnect(si)

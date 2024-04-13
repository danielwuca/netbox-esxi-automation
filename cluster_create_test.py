import ssl
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
from pyVim.task import WaitForTask
import urllib3
import pynetbox

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Function to check if a cluster exists in a datacenter
def get_cluster(content, cluster_name, datacenter):
    for cluster in datacenter.hostFolder.childEntity:
        if cluster.name == cluster_name:
            return cluster
    return None

# Function to create a cluster in a specified datacenter
def create_cluster(content, cluster_name, datacenter):
    cluster_config = vim.cluster.ConfigSpecEx()
    try:
        cluster_folder = datacenter.hostFolder
        cluster_task = cluster_folder.CreateClusterEx(name=cluster_name, spec=cluster_config)
        WaitForTask(cluster_task)
        print(f"Cluster '{cluster_name}' created successfully.")
        return cluster_task.info.result
    except vmodl.MethodFault as error:
        print(f"Failed to create cluster {cluster_name}: {error.msg}")
        return None

# Function to ensure cluster existence
def ensure_cluster_exists(si, cluster_name, datacenter_name):
    content = si.RetrieveContent()
    datacenter = next((dc for dc in content.rootFolder.childEntity if dc.name == datacenter_name), None)
    if not datacenter:
        raise Exception(f"Datacenter '{datacenter_name}' not found")

    cluster = get_cluster(content, cluster_name, datacenter)
    if not cluster:
        cluster = create_cluster(content, cluster_name, datacenter)
    return cluster

# Main function handling the VM synchronization
def main():
    print("Welcome to the VM and Cluster Management Tool")
    datacenter_name = input("Enter the datacenter name: ")
    cluster_names = input("Enter comma-separated cluster names: ").split(',')
    esxi_ip = input("Enter ESXi IP: ")
    username_esxi = input("Enter ESXi Username: ")
    password = input("Enter ESXi Password: ")

    context = ssl._create_unverified_context()
    si = SmartConnect(host=esxi_ip, user=username_esxi, pwd=password, sslContext=context)
    try:
        for cluster_name in cluster_names:
            cluster_name = cluster_name.strip()
            print(f"Checking and creating cluster '{cluster_name}' if necessary...")
            cluster = ensure_cluster_exists(si, cluster_name, datacenter_name)
            # Placeholder for VM sync logic here, you can integrate VM creation or sync here
            print(f"Processing in cluster: {cluster_name}")

    finally:
        Disconnect(si)
        print("Disconnected from vSphere.")

if __name__ == "__main__":
    main()

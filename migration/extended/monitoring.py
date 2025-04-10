"""
Monitoring data migration functions
"""
import requests

from racktables_netbox_migration.utils import error_log
from racktables_netbox_migration.config import NB_HOST, NB_PORT, NB_TOKEN, TARGET_SITE

def migrate_monitoring(cursor, netbox):
    """
    Migrate monitoring data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating monitoring data...")
    
    # Get device names in target site if site filtering is enabled
    site_device_names = set()
    if TARGET_SITE:
        print(f"Filtering monitoring data for site: {TARGET_SITE}")
        site_devices = netbox.dcim.get_devices(site=TARGET_SITE)
        site_device_names = set(device['name'] for device in site_devices)
        
        # Also include VMs in clusters at the target site
        site_clusters = netbox.virtualization.get_clusters(site=TARGET_SITE)
        for cluster in site_clusters:
            cluster_vms = netbox.virtualization.get_virtual_machines(cluster_id=cluster['id'])
            site_device_names.update(vm['name'] for vm in cluster_vms)
    
    # Get Cacti servers
    cursor.execute("SELECT id, base_url FROM CactiServer")
    cacti_servers = {}
    
    for server_id, base_url in cursor.fetchall():
        cacti_servers[server_id] = base_url
    
    # Get Cacti graphs associated with objects
    cursor.execute("""
        SELECT CG.object_id, CG.server_id, CG.graph_id, CG.caption, OBJ.name, OBJ.objtype_id
        FROM CactiGraph CG
        JOIN Object OBJ ON CG.object_id = OBJ.id
    """)
    
    monitor_count = 0
    for object_id, server_id, graph_id, caption, obj_name, objtype_id in cursor.fetchall():
        if not obj_name:
            continue
            
        obj_name = obj_name.strip()
        
        # Skip if site filtering is enabled and device is not in target site
        if TARGET_SITE and obj_name not in site_device_names:
            continue
        
        # Determine if this is a VM or a device
        is_vm = (objtype_id == 1504)  # VM objtype_id
        
        # Find the object in NetBox
        if is_vm:
            objects = netbox.virtualization.get_virtual_machines(name=obj_name)
        else:
            objects = netbox.dcim.get_devices(name=obj_name)
        
        if not objects:
            error_log(f"Could not find object {obj_name} to update monitoring data")
            continue
            
        obj = objects[0]
        
        # Get the Cacti server base URL
        base_url = cacti_servers.get(server_id, "")
        
        # Construct the monitoring URL if we have the base URL
        monitoring_url = ""
        if base_url and graph_id:
            monitoring_url = f"{base_url.rstrip('/')}/graph_view.php?action=tree&select_first=true&graph_id={graph_id}"
        
        # Update the object with monitoring information
        if is_vm:
            url = f"http://{NB_HOST}:{NB_PORT}/api/virtualization/virtual-machines/{obj['id']}/"
        else:
            url = f"http://{NB_HOST}:{NB_PORT}/api/dcim/devices/{obj['id']}/"
            
        headers = {
            "Authorization": f"Token {NB_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # Get current data
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            error_log(f"Error getting object {obj_name}: {response.text}")
            continue
            
        current_data = response.json()
        
        # Prepare data for update
        data = {
            "custom_fields": {
                "Cacti_Server": base_url,
                "Cacti_Graph_ID": str(graph_id),
                "Monitoring_URL": monitoring_url
            }
        }
        
        # Update the custom fields of existing data
        if 'custom_fields' in current_data and current_data['custom_fields']:
            for key, value in current_data['custom_fields'].items():
                if key not in data['custom_fields'] and value:
                    data['custom_fields'][key] = value
        
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code in (200, 201):
            monitor_count += 1
            print(f"Updated monitoring information for {obj_name}")
        else:
            error_log(f"Error updating monitoring for {obj_name}: {response.text}")
    
    print(f"Monitoring data migration completed. Updated {monitor_count} devices/VMs.")

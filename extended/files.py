"""
File attachment migration functions
"""
import os
import requests

from racktables_netbox_migration.utils import error_log
from racktables_netbox_migration.config import NB_HOST, NB_PORT, NB_TOKEN, TARGET_SITE

def migrate_files(cursor, netbox):
    """
    Migrate file attachments from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating file attachments...")
    
    # Get device IDs in target site if site filtering is enabled
    site_device_names = set()
    if TARGET_SITE:
        print(f"Filtering file attachments for site: {TARGET_SITE}")
        site_devices = netbox.dcim.get_devices(site=TARGET_SITE)
        site_device_names = set(device['name'] for device in site_devices)
        
        # Also include VMs in clusters at the target site
        site_clusters = netbox.virtualization.get_clusters(site=TARGET_SITE)
        for cluster in site_clusters:
            cluster_vms = netbox.virtualization.get_virtual_machines(cluster_id=cluster['id'])
            site_device_names.update(vm['name'] for vm in cluster_vms)
    
    # Get files from Racktables
    cursor.execute("SELECT id, name, type, size, contents FROM File")
    file_data = cursor.fetchall()
    
    # Track migrated files for reference
    migrated_files = {}
    
    # Set up directory for file storage
    file_dir = "racktables_files"
    os.makedirs(file_dir, exist_ok=True)
    
    for file_id, file_name, file_type, file_size, file_contents in file_data:
        # Save file locally
        file_path = os.path.join(file_dir, f"{file_id}_{file_name}")
        with open(file_path, "wb") as f:
            f.write(file_contents)
        
        migrated_files[file_id] = {
            "name": file_name,
            "path": file_path,
            "type": file_type,
            "size": file_size
        }
        
        print(f"Saved file: {file_name} (ID: {file_id})")
    
    # Now get file links to associate files with objects
    cursor.execute("""
        SELECT FL.file_id, FL.entity_type, FL.entity_id, F.name
        FROM FileLink FL
        JOIN File F ON FL.file_id = F.id
    """)
    
    for file_id, entity_type, entity_id, file_name in cursor.fetchall():
        if entity_type == 'object':
            # Get the object name
            cursor.execute("SELECT name, objtype_id FROM Object WHERE id = %s", (entity_id,))
            obj_data = cursor.fetchone()
            
            if not obj_data:
                continue
                
            obj_name, objtype_id = obj_data
            
            # Skip if the name is empty
            if not obj_name:
                continue
                
            obj_name = obj_name.strip()
            
            # Skip if site filtering is enabled and this device is not in the target site
            if TARGET_SITE and obj_name not in site_device_names:
                continue
            
            # Determine if this is a device or VM
            is_vm = (objtype_id == 1504)  # VM objtype_id
            
            # Find the object in NetBox
            if is_vm:
                obj = netbox.virtualization.get_virtual_machines(name=obj_name)
            else:
                obj = netbox.dcim.get_devices(name=obj_name)
            
            if not obj:
                error_log(f"Could not find object {obj_name} to attach file {file_name}")
                continue
                
            obj = obj[0]
            
            # Update the object with file reference in custom fields
            if is_vm:
                url = f"http://{NB_HOST}:{NB_PORT}/api/virtualization/virtual-machines/{obj['id']}/"
            else:
                url = f"http://{NB_HOST}:{NB_PORT}/api/dcim/devices/{obj['id']}/"
                
            headers = {
                "Authorization": f"Token {NB_TOKEN}",
                "Content-Type": "application/json"
            }
            
            # Get current value if it exists
            response = requests.get(url, headers=headers)
            current_data = response.json()
            
            file_refs = current_data.get('custom_fields', {}).get('File_References', "")
            if file_refs:
                file_refs += f", {file_name} (from Racktables)"
            else:
                file_refs = f"{file_name} (from Racktables)"
            
            data = {
                "custom_fields": {
                    "File_References": file_refs
                }
            }
            
            response = requests.patch(url, headers=headers, json=data)
            if response.status_code in (200, 201):
                print(f"Updated file reference for {obj_name}: {file_name}")
            else:
                error_log(f"Error updating file reference: {response.text}")
    
    # Create a summary document about migrated files
    with open(os.path.join(file_dir, "migrated_files.txt"), "w") as f:
        f.write("# Migrated Files from Racktables\n\n")
        f.write("This document lists files migrated from Racktables to local storage.\n")
        f.write("File references have been added to device custom fields.\n\n")
        
        f.write("## File List\n\n")
        for file_id, file_info in migrated_files.items():
            f.write(f"- {file_info['name']} (ID: {file_id})\n")
            f.write(f"  Type: {file_info['type']}, Size: {file_info['size']} bytes\n")
            f.write(f"  Saved to: {file_info['path']}\n\n")
    
    print(f"File migration completed. Files saved to {file_dir} directory.")
    print(f"See {os.path.join(file_dir, 'migrated_files.txt')} for a summary.")

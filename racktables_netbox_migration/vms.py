"""
Virtual machine creation and management functions
"""
from slugify import slugify

from racktables_netbox_migration.utils import get_db_connection, get_cursor
from racktables_netbox_migration.db import getTags
from racktables_netbox_migration.config import TARGET_SITE

def create_vms(netbox, create_mounted=True, create_unmounted=True):
    """
    Create VMs and their clusters in NetBox
    
    Args:
        netbox: NetBox client instance
        create_mounted: Whether to create VMs in clusters
        create_unmounted: Whether to create VMs not in clusters
    """
    # Skip if not creating any VMs
    if not create_mounted and not create_unmounted:
        return
    
    print("Creating VM clusters and virtual machines")
    
    # Get existing VM data to avoid duplicates
    existing_cluster_types = set(cluster_type['name'] for cluster_type in netbox.virtualization.get_cluster_types())
    existing_cluster_names = set(cluster['name'] for cluster in netbox.virtualization.get_clusters())
    existing_virtual_machines = set(virtual_machine['name'] for virtual_machine in netbox.virtualization.get_virtual_machines())
    
    # Site filtering for clusters
    site_filter = {}
    if TARGET_SITE:
        # Updated to handle both RecordSet and list return types
        try:
            sites = netbox.dcim.get_sites(name=TARGET_SITE)
            
            # Convert RecordSet to list if needed
            if hasattr(sites, 'results'):
                sites = sites.results
            
            # Ensure we have a list to work with
            if not isinstance(sites, list):
                sites = list(sites)
            
            if sites:
                # Extract site ID safely
                site = sites[0]
                site_id = site['id'] if isinstance(site, dict) else site
                site_filter = {"site": site_id}
                print(f"Filtering VMs by site: {TARGET_SITE}")
            else:
                print(f"Warning: No site found with name {TARGET_SITE}")
        except Exception as e:
            print(f"Error processing site filter: {e}")
    
    # Create VMs in clusters if enabled
    if create_mounted:
        create_mounted_vms(
            netbox, 
            existing_cluster_types, 
            existing_cluster_names, 
            existing_virtual_machines,
            site_filter
        )
    
    # Create VMs not in clusters if enabled
    if create_unmounted:
        create_unmounted_vms(
            netbox, 
            existing_cluster_types, 
            existing_cluster_names, 
            existing_virtual_machines,
            site_filter
        )

def create_mounted_vms(netbox, existing_cluster_types, existing_cluster_names, existing_virtual_machines, site_filter={}):
    """
    Create VMs that exist in clusters
    
    Args:
        netbox: NetBox client instance
        existing_cluster_types: Set of existing cluster type names
        existing_cluster_names: Set of existing cluster names
        existing_virtual_machines: Set of existing VM names
        site_filter: Optional site filter dict
    """
    print("Creating VMs in clusters")
    
    vm_counter = 0
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            # Get clusters from Racktables
            cursor.execute("SELECT id,name,asset_no,label FROM Object WHERE objtype_id=1505")
            clusters = cursor.fetchall()
            
            for row in clusters:
                cluster_id, cluster_name, asset_no, label = row["id"], row["name"], row["asset_no"], row["label"]
                
                # Create cluster type if needed
                if cluster_name not in existing_cluster_types:
                    try:
                        netbox.virtualization.create_cluster_type(
                            cluster_name, 
                            slugify(cluster_name)
                        )
                        existing_cluster_types.add(cluster_name)
                        print(f"Created cluster type: {cluster_name}")
                    except Exception as e:
                        print(f"Error creating cluster type {cluster_name}: {e}")
                
                # Create cluster if needed
                if cluster_name not in existing_cluster_names:
                    try:
                        netbox.virtualization.create_cluster(
                            cluster_name, 
                            cluster_name,
                            **site_filter
                        )
                        existing_cluster_names.add(cluster_name)
                        print(f"Created cluster: {cluster_name}")
                    except Exception as e:
                        print(f"Error creating cluster {cluster_name}: {e}")
                
                # Get VMs in this cluster
                cursor.execute(
                    "SELECT child_entity_type,child_entity_id FROM EntityLink WHERE parent_entity_id=%s", 
                    (cluster_id,)
                )
                child_virtual_machines = cursor.fetchall()
                
                for child_row in child_virtual_machines:
                    child_entity_type, child_entity_id = child_row["child_entity_type"], child_row["child_entity_id"]
                    
                    # Get VM details
                    cursor.execute(
                        "SELECT name,label,comment,objtype_id,asset_no FROM Object WHERE id=%s", 
                        (child_entity_id,)
                    )
                    vm_row = cursor.fetchone()
                    
                    if not vm_row:
                        continue
                    
                    vm_name = vm_row["name"]
                    vm_label = vm_row["label"]
                    vm_comment = vm_row["comment"]
                    vm_objtype_id = vm_row["objtype_id"]
                    vm_asset_no = vm_row["asset_no"]
                    
                    # Skip if not a VM or no name
                    if vm_objtype_id != 1504 or not vm_name:
                        continue
                    
                    vm_name = vm_name.strip()
                    
                    # Skip if VM already exists
                    if vm_name in existing_virtual_machines:
                        print(f"VM {vm_name} already exists")
                        continue
                    
                    # Get VM tags
                    vm_tags = getTags("object", child_entity_id)
                    
                    # Create the VM
                    try:
                        netbox.virtualization.create_virtual_machine(
                            vm_name, 
                            cluster_name, 
                            tags=vm_tags, 
                            comments=vm_comment[:200] if vm_comment else "",
                            custom_fields={
                                "VM_Label": vm_label[:200] if vm_label else "", 
                                "VM_Asset_No": vm_asset_no if vm_asset_no else ""
                            }
                        )
                        
                        existing_virtual_machines.add(vm_name)
                        vm_counter += 1
                        print(f"Created VM {vm_name} in cluster {cluster_name}")
                    except Exception as e:
                        print(f"Error creating VM {vm_name}: {e}")
    
    print(f"Created {vm_counter} VMs in clusters")

def create_unmounted_vms(netbox, existing_cluster_types, existing_cluster_names, existing_virtual_machines, site_filter={}):
    """
    Create VMs that are not in clusters
    
    Args:
        netbox: NetBox client instance
        existing_cluster_types: Set of existing cluster type names
        existing_cluster_names: Set of existing cluster names
        existing_virtual_machines: Set of existing VM names
        site_filter: Optional site filter dict
    """
    print("Creating unmounted VMs")
    
    # Create a special cluster for unmounted VMs
    unmounted_cluster_name = "Unmounted Cluster"
    
    # Create cluster type if needed
    if unmounted_cluster_name not in existing_cluster_types:
        try:
            netbox.virtualization.create_cluster_type(
                unmounted_cluster_name, 
                slugify(unmounted_cluster_name)
            )
            existing_cluster_types.add(unmounted_cluster_name)
            print(f"Created cluster type: {unmounted_cluster_name}")
        except Exception as e:
            print(f"Error creating cluster type {unmounted_cluster_name}: {e}")
    
    # Create cluster if needed
    if unmounted_cluster_name not in existing_cluster_names:
        try:
            netbox.virtualization.create_cluster(
                unmounted_cluster_name, 
                unmounted_cluster_name,
                **site_filter
            )
            existing_cluster_names.add(unmounted_cluster_name)
            print(f"Created cluster: {unmounted_cluster_name}")
        except Exception as e:
            print(f"Error creating cluster {unmounted_cluster_name}: {e}")
    
    # Get all VMs from Racktables that aren't in a cluster
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            # Get all VMs
            cursor.execute("SELECT id,name,label,comment,objtype_id,asset_no FROM Object WHERE objtype_id=1504")
            vms = cursor.fetchall()
            
            # Get VMs that are in clusters
            cursor.execute("""
                SELECT child_entity_id 
                FROM EntityLink 
                WHERE parent_entity_type='object' 
                AND child_entity_type='object' 
                AND child_entity_id IN (SELECT id FROM Object WHERE objtype_id=1504)
            """)
            mounted_vm_ids = set(row["child_entity_id"] for row in cursor.fetchall())
    
    # Process VMs not in clusters
    vm_counter = 0
    for vm in vms:
        vm_id = vm["id"]
        vm_name = vm["name"]
        vm_label = vm["label"]
        vm_comment = vm["comment"]
        vm_asset_no = vm["asset_no"]
        
        # Skip if already in a cluster or no name
        if vm_id in mounted_vm_ids or not vm_name:
            continue
        
        vm_name = vm_name.strip()
        
        # Skip if VM already exists
        if vm_name in existing_virtual_machines:
            print(f"VM {vm_name} already exists")
            continue
        
        # Get VM tags
        vm_tags = getTags("object", vm_id)
        
        # Create the VM
        try:
            netbox.virtualization.create_virtual_machine(
                vm_name, 
                unmounted_cluster_name, 
                tags=vm_tags, 
                comments=vm_comment[:200] if vm_comment else "",
                custom_fields={
                    "VM_Label": vm_label[:200] if vm_label else "", 
                    "VM_Asset_No": vm_asset_no if vm_asset_no else ""
                }
            )
            
            existing_virtual_machines.add(vm_name)
            vm_counter += 1
            print(f"Created unmounted VM: {vm_name}")
        except Exception as e:
            print(f"Error creating VM {vm_name}: {e}")
    
    print(f"Created {vm_counter} unmounted VMs")

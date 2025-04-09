"""
VLAN-related migration functions
"""
from slugify import slugify

from racktables_netbox_migration.utils import get_db_connection, get_cursor, pickleDump

def create_vlan_groups(netbox):
    """
    Create VLAN groups from Racktables in NetBox
    
    Args:
        netbox: NetBox client instance
    """
    print("Creating VLAN Groups")
    
    # Map VLAN domain IDs to names
    vlan_domain_id_names = {}
    
    # Get existing VLAN groups to avoid duplicates
    existing_vlan_groups = set(vlan_group['name'] for vlan_group in netbox.ipam.get_vlan_groups())
    
    # Get VLAN domains from Racktables
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT id,description FROM VLANDomain")
            vlan_domains = cursor.fetchall()
            
            for row in vlan_domains:
                domain_id, description = row["id"], row["description"]
                
                vlan_domain_id_names[domain_id] = description
                
                # Skip if VLAN group already exists
                if description in existing_vlan_groups:
                    print(f"VLAN group {description} already exists")
                    continue
                
                # Create the VLAN group
                try:
                    netbox.ipam.create_vlan_group(
                        name=description, 
                        slug=slugify(description), 
                        custom_fields={"VLAN_Domain_ID": str(domain_id)}
                    )
                    
                    print(f"Created VLAN group: {description}")
                    existing_vlan_groups.add(description)
                except Exception as e:
                    print(f"Error creating VLAN group {description}: {e}")
    
    return vlan_domain_id_names

def create_vlans(netbox):
    """
    Create VLANs from Racktables in NetBox
    
    Args:
        netbox: NetBox client instance
    """
    print("Creating VLANs")
    
    # Get VLAN domain mappings
    vlan_domain_id_names = {}
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT id,description FROM VLANDomain")
            for row in cursor.fetchall():
                vlan_domain_id_names[row["id"]] = row["description"]
    
    # Track VLAN mappings for network associations
    network_id_group_name_id = {}
    
    # Track VLANs by group to ensure unique names
    vlans_for_group = {}
    
    # Process IPv4 and IPv6 VLANs
    for IP in ("4", "6"):
        with get_db_connection() as connection:
            with get_cursor(connection) as cursor:
                cursor.execute(f"SELECT domain_id,vlan_id,ipv{IP}net_id FROM VLANIPv{IP}")
                vlans = cursor.fetchall()
                
                for row in vlans:
                    domain_id, vlan_id, net_id = row["domain_id"], row["vlan_id"], row[f"ipv{IP}net_id"]
                    
                    # Get VLAN description
                    cursor.execute(
                        "SELECT vlan_descr FROM VLANDescription WHERE domain_id=%s AND vlan_id=%s", 
                        (domain_id, vlan_id)
                    )
                    result = cursor.fetchone()
                    vlan_name = result["vlan_descr"] if result else None
                    
                    # Skip if no name available
                    if not vlan_name:
                        continue
                    
                    # Get VLAN group name
                    vlan_group_name = vlan_domain_id_names[domain_id]
                    
                    # Initialize tracking for this group
                    if vlan_group_name not in vlans_for_group:
                        vlans_for_group[vlan_group_name] = set()
                    
                    # Ensure unique name within group
                    name = vlan_name
                    if name in vlans_for_group[vlan_group_name]:
                        counter = 1
                        while True:
                            name = f"{vlan_name}-{counter}"
                            if name not in vlans_for_group[vlan_group_name]:
                                break
                            counter += 1
                    
                    # Create the VLAN
                    try:
                        created_vlan = netbox.ipam.create_vlan(
                            group={"name": vlan_group_name},
                            vid=vlan_id,
                            vlan_name=name
                        )
                        
                        # Store mapping for network association
                        network_id_group_name_id[net_id] = (vlan_group_name, name, created_vlan['id'])
                        
                        # Track created VLAN name
                        vlans_for_group[vlan_group_name].add(name)
                        
                        print(f"Created VLAN {name} (ID: {vlan_id}) in group {vlan_group_name}")
                    except Exception as e:
                        print(f"Error creating VLAN {name} (ID: {vlan_id}): {e}")
    
    # Save network to VLAN mappings for IP networks creation
    pickleDump('network_id_group_name_id', network_id_group_name_id)
    
    return network_id_group_name_id

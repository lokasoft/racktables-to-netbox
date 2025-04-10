"""
Patch cable migration functions with comprehensive database and duplicate handling
"""
import requests
from slugify import slugify

from racktables_netbox_migration.utils import pickleLoad, error_log
from racktables_netbox_migration.config import NB_HOST, NB_PORT, NB_TOKEN, TARGET_SITE

def migrate_patch_cables(cursor, netbox):
    """
    Migrate patch cable data from Racktables to NetBox with robust handling
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating patch cable data...")
    
    # Flexible column detection function
    def get_column_name(table, preferred_columns):
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        columns = [column['Field'] for column in cursor.fetchall()]
        
        for pref_col in preferred_columns:
            if pref_col in columns:
                return pref_col
        
        print(f"Could not find suitable column for {table}")
        return None

    # Detect column names
    connector_name_col = get_column_name('PatchCableConnector', 
        ['connector_name', 'name', 'type', 'label'])
    type_name_col = get_column_name('PatchCableType', 
        ['pctype_name', 'name', 'type', 'label'])
    
    if not (connector_name_col and type_name_col):
        print("Cannot proceed with patch cable migration due to schema issues")
        return
    
    # Dictionary to map patch cable connector types and types
    connector_types = {}
    cable_types = {}
    
    # Load connector types with error handling
    try:
        cursor.execute(f"SELECT id, {connector_name_col} FROM PatchCableConnector")
        connector_types = {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        error_log(f"Error loading PatchCableConnector: {str(e)}")
        return
    
    # Load cable types with error handling
    try:
        cursor.execute(f"SELECT id, {type_name_col} FROM PatchCableType")
        cable_types = {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        error_log(f"Error loading PatchCableType: {str(e)}")
        return
    
    # Site filtering
    site_device_ids = []
    if TARGET_SITE:
        site_devices = netbox.dcim.get_devices(site=TARGET_SITE)
        site_device_ids = [device['id'] for device in site_devices]
        
        if not site_device_ids:
            print("No devices found in the specified site, skipping patch cable migration")
            return
    
    # Get existing cables to prevent duplicates
    existing_cables = set()
    for cable in netbox.dcim.get_cables():
        if cable['termination_a_type'] == 'dcim.interface' and cable['termination_b_type'] == 'dcim.interface':
            # Create a unique identifier for the cable
            cable_key = (
                min(cable['termination_a_id'], cable['termination_b_id']),
                max(cable['termination_a_id'], cable['termination_b_id'])
            )
            existing_cables.add(cable_key)
    
    # Get connections from the Link table
    cursor.execute("""
        SELECT L.porta, L.portb, L.cable, C.pctype_id, C.end1_conn_id, C.end2_conn_id, 
               C.length, C.color, C.description 
        FROM Link L
        JOIN PatchCableHeap C ON L.cable = C.id
        WHERE L.cable IS NOT NULL
    """)
    link_connections = cursor.fetchall()
    
    connection_ids = pickleLoad('connection_ids', dict())
    cable_count = 0
    
    for connection in link_connections:
        porta_id, portb_id, cable_id = connection[0], connection[1], connection[2]
        
        # Skip if interface IDs are not mapped
        if porta_id not in connection_ids or portb_id not in connection_ids:
            continue
        
        netbox_id_a = connection_ids[porta_id]
        netbox_id_b = connection_ids[portb_id]
        
        # Site filtering check
        if TARGET_SITE and (netbox_id_a not in site_device_ids and netbox_id_b not in site_device_ids):
            continue
        
        # Create unique cable key
        cable_key = (min(netbox_id_a, netbox_id_b), max(netbox_id_a, netbox_id_b))
        
        # Skip if cable already exists
        if cable_key in existing_cables:
            continue
        
        # Extract cable details
        pctype_id, end1_conn_id, end2_conn_id = connection[3:6]
        length, color, description = connection[6:9]
        
        # Get cable type and connector details
        cable_type = cable_types.get(pctype_id, "Unknown")
        connector_a = connector_types.get(end1_conn_id, "Unknown")
        connector_b = connector_types.get(end2_conn_id, "Unknown")
        
        try:
            # Create cable connection
            cable = netbox.dcim.create_interface_connection(
                netbox_id_a, 
                netbox_id_b, 
                'dcim.interface', 
                'dcim.interface',
                label=f"{cable_type}-{color}",
                color=color,
                length=length,
                length_unit="m",
                description=description
            )
            
            # Update cable with custom fields
            url = f"http://{NB_HOST}:{NB_PORT}/api/dcim/cables/{cable['id']}/"
            headers = {
                "Authorization": f"Token {NB_TOKEN}",
                "Content-Type": "application/json"
            }
            
            data = {
                "custom_fields": {
                    "Patch_Cable_Type": cable_type,
                    "Patch_Cable_Connector_A": connector_a,
                    "Patch_Cable_Connector_B": connector_b,
                    "Cable_Color": color,
                    "Cable_Length": str(length) if length else ""
                }
            }
            
            response = requests.patch(url, headers=headers, json=data)
            
            if response.status_code in (200, 201):
                cable_count += 1
                print(f"Created cable between interfaces {netbox_id_a} and {netbox_id_b}")
                
                # Mark as processed
                existing_cables.add(cable_key)
            else:
                error_log(f"Error updating cable: {response.text}")
        
        except Exception as e:
            error_log(f"Error creating cable connection: {str(e)}")
    
    print(f"Completed patch cable migration. Created {cable_count} cables.")

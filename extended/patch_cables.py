"""
Patch cable migration functions
"""
import requests
from slugify import slugify

from racktables_netbox_migration.utils import pickleLoad, error_log
from racktables_netbox_migration.config import NB_HOST, NB_PORT, NB_TOKEN, TARGET_SITE

def migrate_patch_cables(cursor, netbox):
    """
    Migrate patch cable data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating patch cable data...")
    
    # Dictionary to map patch cable connector types
    connector_types = {}
    
    # Dictionary to map patch cable types
    cable_types = {}
    
    # If site filtering is enabled, only process cables connected to devices in that site
    site_filter_clause = ""
    site_device_ids = []
    
    if TARGET_SITE:
        print(f"Filtering patch cables for site: {TARGET_SITE}")
        # Get devices in the target site
        site_devices = netbox.dcim.get_devices(site=TARGET_SITE)
        site_device_ids = [device['id'] for device in site_devices]
        
        if not site_device_ids:
            print("No devices found in the specified site, skipping patch cable migration")
            return
    
    # Load connector types
    cursor.execute("SELECT id, connector_name FROM PatchCableConnector")
    for conn_id, conn_name in cursor.fetchall():
        connector_types[conn_id] = conn_name
        
    # Load cable types
    cursor.execute("SELECT id, pctype_name FROM PatchCableType")
    for type_id, type_name in cursor.fetchall():
        cable_types[type_id] = type_name
    
    # Get existing cables in NetBox to avoid duplicates
    existing_cables = set()
    for cable in netbox.dcim.get_cables():
        if cable['termination_a_type'] == 'dcim.interface' and cable['termination_b_type'] == 'dcim.interface':
            cable_key = f"{cable['termination_a_id']}-{cable['termination_b_id']}"
            existing_cables.add(cable_key)
    
    # Get patch cable heap (inventory)
    cursor.execute("""
        SELECT id, pctype_id, end1_conn_id, end2_conn_id, length, color, description 
        FROM PatchCableHeap
    """)
    
    # Process patch cables in inventory (not yet connected)
    for cable_id, pctype_id, end1_conn_id, end2_conn_id, length, color, description in cursor.fetchall():
        # For inventory items, we'll create custom tags since they're not connected yet
        cable_type = cable_types.get(pctype_id, "Unknown")
        connector_a = connector_types.get(end1_conn_id, "Unknown")
        connector_b = connector_types.get(end2_conn_id, "Unknown")
        
        # Create a tag that represents this cable in inventory
        tag_name = f"Cable-{cable_id}-{cable_type}-{color}"
        tag_slug = slugify(tag_name)
        
        try:
            netbox.extras.create_tag(
                name=tag_name, 
                slug=tag_slug,
                color="2196f3",
                description=f"Cable type: {cable_type}, Length: {length}, Connectors: {connector_a}/{connector_b}, Description: {description}"
            )
            print(f"Created inventory tag for cable ID {cable_id}")
        except Exception as e:
            error_log(f"Error creating tag for cable {cable_id}: {str(e)}")
    
    # Process connections from the Link table that represent cables
    # These are already created in the CREATE_INTERFACE_CONNECTIONS section,
    # so we'll update them with additional information
    cursor.execute("""
        SELECT L.porta, L.portb, L.cable 
        FROM Link L
        WHERE L.cable IS NOT NULL
    """)
    
    connection_ids = pickleLoad('connection_ids', dict())
    
    for porta_id, portb_id, cable_id in cursor.fetchall():
        if porta_id not in connection_ids or portb_id not in connection_ids:
            continue
            
        netbox_id_a = connection_ids[porta_id]
        netbox_id_b = connection_ids[portb_id]
        
        # If site filtering is enabled, skip cables not connected to devices in the site
        if TARGET_SITE and (netbox_id_a not in site_device_ids and netbox_id_b not in site_device_ids):
            continue
        
        # Skip if the cable already exists
        cable_key = f"{netbox_id_a}-{netbox_id_b}"
        if cable_key in existing_cables:
            # Get the cable
            for cable in netbox.dcim.get_cables():
                if ((cable['termination_a_id'] == netbox_id_a and cable['termination_b_id'] == netbox_id_b) or
                    (cable['termination_a_id'] == netbox_id_b and cable['termination_b_id'] == netbox_id_a)):
                    
                    # Get cable details from PatchCableHeap
                    cursor.execute("""
                        SELECT pctype_id, end1_conn_id, end2_conn_id, length, color, description
                        FROM PatchCableHeap
                        WHERE id = %s
                    """, (cable_id,))
                    
                    cable_data = cursor.fetchone()
                    if cable_data:
                        pctype_id, end1_conn_id, end2_conn_id, length, color, description = cable_data
                        
                        # Update the cable with custom fields
                        cable_type = cable_types.get(pctype_id, "Unknown")
                        connector_a = connector_types.get(end1_conn_id, "Unknown")
                        connector_b = connector_types.get(end2_conn_id, "Unknown")
                        
                        # Use the requests library to update the cable directly with custom fields
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
                            },
                            "label": f"{cable_type}-{color}",
                            "color": color,
                            "length": length,
                            "length_unit": "m",
                            "description": description
                        }
                        
                        response = requests.patch(url, headers=headers, json=data)
                        if response.status_code in (200, 201):
                            print(f"Updated cable information for cable between {netbox_id_a} and {netbox_id_b}")
                        else:
                            error_log(f"Error updating cable {cable['id']}: {response.text}")
                            
                    break
    
    print("Patch cable migration completed.")

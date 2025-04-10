"""
Patch cable migration functions with comprehensive database and duplicate handling
"""
import requests
from slugify import slugify

from migration.utils import pickleLoad, error_log
from migration.config import NB_HOST, NB_PORT, NB_TOKEN, TARGET_SITE

def migrate_patch_cables(cursor, netbox):
    """
    Migrate patch cable data from Racktables to NetBox with robust handling
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating patch cable data...")
    
    # First check if required tables exist
    required_tables = ["PatchCableConnector", "PatchCableType", "Link", "PatchCableHeap"]
    missing_tables = []
    
    for table in required_tables:
        try:
            cursor.execute(f"SHOW TABLES LIKE '{table}'")
            if not cursor.fetchone():
                missing_tables.append(table)
        except Exception as e:
            print(f"Error checking table {table}: {e}")
            missing_tables.append(table)
    
    if missing_tables:
        print(f"The following required tables are missing: {', '.join(missing_tables)}")
        print("Cannot proceed with patch cable migration")
        return
    
    # Flexible column detection function with additional logging
    def get_column_name(table, preferred_columns):
        try:
            cursor.execute(f"SHOW COLUMNS FROM {table}")
            columns = [column['Field'] for column in cursor.fetchall()]
            
            print(f"Available columns in {table}: {', '.join(columns)}")
            
            for pref_col in preferred_columns:
                if pref_col in columns:
                    print(f"Selected column '{pref_col}' for {table}")
                    return pref_col
            
            # Use first column that has 'name' in it
            for col in columns:
                if 'name' in col.lower():
                    print(f"Selected column '{col}' (contains 'name') for {table}")
                    return col
            
            # Fall back to first column
            if columns:
                print(f"Falling back to first column '{columns[0]}' for {table}")
                return columns[0]
            
            print(f"No suitable column found for {table}")
            return None
        except Exception as e:
            print(f"Error getting columns for {table}: {e}")
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
        for row in cursor.fetchall():
            connector_types[row['id']] = row[connector_name_col]
        print(f"Loaded {len(connector_types)} connector types")
    except Exception as e:
        error_log(f"Error loading PatchCableConnector: {str(e)}")
        print(f"Error loading connector types: {e}")
        print("Continuing with empty connector types dictionary")
    
    # Load cable types with error handling
    try:
        cursor.execute(f"SELECT id, {type_name_col} FROM PatchCableType")
        for row in cursor.fetchall():
            cable_types[row['id']] = row[type_name_col]
        print(f"Loaded {len(cable_types)} cable types")
    except Exception as e:
        error_log(f"Error loading PatchCableType: {str(e)}")
        print(f"Error loading cable types: {e}")
        print("Continuing with empty cable types dictionary")
    
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
    
    # Check PatchCableHeap schema to determine field names
    try:
        cursor.execute("SHOW COLUMNS FROM PatchCableHeap")
        pch_columns = {column['Field'].lower(): column['Field'] for column in cursor.fetchall()}
        print(f"PatchCableHeap columns: {', '.join(pch_columns.keys())}")
    except Exception as e:
        error_log(f"Error getting PatchCableHeap schema: {str(e)}")
        print(f"Error getting PatchCableHeap schema: {e}")
        pch_columns = {}
    
    # Determine the correct field names
    pctype_id_field = pch_columns.get('pctype_id', 'pctype_id')
    end1_conn_id_field = pch_columns.get('end1_conn_id', 'end1_conn_id')
    end2_conn_id_field = pch_columns.get('end2_conn_id', 'end2_conn_id')
    length_field = pch_columns.get('length', 'length')
    color_field = pch_columns.get('color', 'color') if 'color' in pch_columns else None
    description_field = pch_columns.get('description', 'description')
    
    # Get connections from the Link table
    try:
        # Build query based on available columns
        query = f"""
            SELECT L.porta, L.portb, L.cable, C.{pctype_id_field}, 
                   C.{end1_conn_id_field}, C.{end2_conn_id_field}, 
                   C.{length_field}"""
        
        # Add color if it exists
        if color_field:
            query += f", C.{color_field}"
            
        # Add description if it exists
        query += f", C.{description_field} FROM Link L JOIN PatchCableHeap C ON L.cable = C.id WHERE L.cable IS NOT NULL"
        
        cursor.execute(query)
        link_connections = cursor.fetchall()
        print(f"Found {len(link_connections)} cable connections")
    except Exception as e:
        error_log(f"Error querying Link table: {str(e)}")
        print(f"Error querying Link table: {e}")
        link_connections = []
    
    connection_ids = pickleLoad('connection_ids', dict())
    cable_count = 0
    
    for connection in link_connections:
        try:
            porta_id, portb_id, cable_id = connection['porta'], connection['portb'], connection['cable']
            
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
            
            # Extract cable details - handle schema differences
            try:
                pctype_id = connection[pctype_id_field]
                end1_conn_id = connection[end1_conn_id_field]
                end2_conn_id = connection[end2_conn_id_field]
                length = connection[length_field]
                color = connection[color_field] if color_field and color_field in connection else None
                description = connection[description_field]
            except (KeyError, IndexError):
                # Fallback to numerical indices if column names don't match
                pctype_id = connection.get(3, None)
                end1_conn_id = connection.get(4, None)
                end2_conn_id = connection.get(5, None)
                length = connection.get(6, None)
                color = connection.get(7, None) if color_field else None
                description = connection.get(8 if color_field else 7, None)
            
            # Get cable type and connector details
            cable_type = cable_types.get(pctype_id, "Unknown") if pctype_id else "Unknown"
            connector_a = connector_types.get(end1_conn_id, "Unknown") if end1_conn_id else "Unknown"
            connector_b = connector_types.get(end2_conn_id, "Unknown") if end2_conn_id else "Unknown"
            
            try:
                # Create cable connection
                cable = netbox.dcim.create_interface_connection(
                    netbox_id_a, 
                    netbox_id_b, 
                    'dcim.interface', 
                    'dcim.interface',
                    label=f"{cable_type}-{color}" if color else cable_type,
                    color=color if color else None,
                    length=length if length else None,
                    length_unit="m",
                    description=description if description else None
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
                        "Cable_Color": color if color else "",
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
        
        except Exception as e:
            error_log(f"Error processing connection: {str(e)}")
            continue
    
    print(f"Completed patch cable migration. Created {cable_count} cables.")

"""
Interface creation and management functions
"""
import time

from racktables_netbox_migration.utils import (
    get_db_connection, get_cursor, pickleLoad, pickleDump, error_log
)
from racktables_netbox_migration.db import change_interface_name
from racktables_netbox_migration.config import TARGET_SITE

def get_interfaces(netbox):
    """
    Retrieve all interfaces from NetBox with pagination
    
    This function retrieves interfaces from NetBox using pagination to handle
    large numbers of interfaces. It caches the results to avoid repeated queries.
    
    Args:
        netbox: NetBox client instance
        
    Returns:
        list: A list of interface objects
    """
    interfaces = []
    interfaces_file = "interfaces"
    
    # First try to load cached interfaces
    cached_interfaces = pickleLoad(interfaces_file, [])
    if cached_interfaces:
        print(f"Loaded {len(cached_interfaces)} interfaces from cache")
        return cached_interfaces
    
    print("Fetching interfaces from NetBox...")
    limit = 500
    offset = 0
    
    try:
        while True:
            ret = netbox.dcim.get_interfaces_custom(limit=limit, offset=offset)
            if not ret:
                # No more interfaces to fetch
                break
                
            interfaces.extend(ret)
            offset += limit
            print(f"Added {len(ret)} interfaces, total {len(interfaces)}")
    except Exception as e:
        error_log(f"Error retrieving interfaces: {str(e)}")
        print(f"Error retrieving interfaces: {str(e)}")
    
    print(f"Total interfaces fetched: {len(interfaces)}")
    
    # Cache the result for later use
    pickleDump(interfaces_file, interfaces)
    return interfaces

def create_interfaces(netbox):
    """
    Create interfaces for devices in NetBox
    
    Args:
        netbox: NetBox client instance
    """
    print("Creating interfaces for devices")
    
    # Load device data
    global_physical_object_ids = pickleLoad("global_physical_object_ids", set())
    global_non_physical_object_ids = pickleLoad("global_non_physical_object_ids", set())
    
    # Filter devices by site if site filtering is enabled
    if TARGET_SITE:
        site_devices = set(device['id'] for device in netbox.dcim.get_devices(site=TARGET_SITE))
        filtered_physical = []
        for device_name, racktables_id, netbox_id, objtype_id in global_physical_object_ids:
            if netbox_id in site_devices:
                filtered_physical.append((device_name, racktables_id, netbox_id, objtype_id))
        global_physical_object_ids = filtered_physical
    
    # Get existing interfaces to avoid duplicates
    print("Getting existing interfaces")
    start_time = time.time()
    
    interface_local_names_for_device = {}
    interface_netbox_ids_for_device = {}
    
    for value in get_interfaces(netbox):
        device_id = value['device']['id']
        
        if device_id not in interface_local_names_for_device:
            interface_local_names_for_device[device_id] = set()
        
        interface_local_names_for_device[device_id].add(value['name'])
        
        if device_id not in interface_netbox_ids_for_device:
            interface_netbox_ids_for_device[device_id] = {}
        
        interface_netbox_ids_for_device[device_id][value['name']] = value['id']
    
    print(f"Got existing interfaces in {time.time() - start_time:.2f} seconds")
    
    # Get port types from Racktables
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT id,oif_name FROM PortOuterInterface")
            port_outer_interfaces = {row["id"]: row["oif_name"] for row in cursor.fetchall()}
    
    # Store the SQL id and the netbox interface id for later connections
    connection_ids = {}
    
    # Create interfaces for physical and non-physical devices
    interface_counter = 0
    for device_list in (global_physical_object_ids, global_non_physical_object_ids):
        for device_name, racktables_object_id, netbox_id, objtype_id in device_list:
            # Get ports from Racktables
            with get_db_connection() as connection:
                with get_cursor(connection) as cursor:
                    cursor.execute(
                        "SELECT id,name,iif_id,type,label FROM Port WHERE object_id=%s", 
                        (racktables_object_id,)
                    )
                    ports = cursor.fetchall()
            
            # Initialize tracking for this device
            if netbox_id not in interface_local_names_for_device:
                interface_local_names_for_device[netbox_id] = set()
            
            if netbox_id not in interface_netbox_ids_for_device:
                interface_netbox_ids_for_device[netbox_id] = {}
            
            # Process each port
            for port in ports:
                Id, interface_name, iif_id, Type, label = port["id"], port["name"], port["iif_id"], port["type"], port["label"]
                
                # Skip if no interface name
                if not interface_name:
                    continue
                
                # Get port type
                port_outer_interface = port_outer_interfaces.get(Type, "Other")
                
                # Standardize interface name
                interface_name = change_interface_name(interface_name, objtype_id)
                
                # Skip if interface already exists
                if interface_name in interface_local_names_for_device[netbox_id]:
                    print(f"Interface {interface_name} already exists on {device_name}")
                    
                    # Link racktables interface id to netbox interface id
                    connection_ids[Id] = interface_netbox_ids_for_device[netbox_id][interface_name]
                    continue
                
                # Create the interface
                try:
                    added_interface = netbox.dcim.create_interface(
                        name=interface_name,
                        interface_type="other",
                        device_id=netbox_id,
                        custom_fields={"Device_Interface_Type": port_outer_interface},
                        label=label[:200] if label else ""
                    )
                    
                    # Track created interface
                    interface_local_names_for_device[netbox_id].add(interface_name)
                    interface_netbox_ids_for_device[netbox_id][interface_name] = added_interface['id']
                    
                    # Link racktables interface id to netbox interface id
                    connection_ids[Id] = added_interface['id']
                    
                    interface_counter += 1
                    if interface_counter % 500 == 0:
                        print(f"Created {interface_counter} interfaces")
                
                except Exception as e:
                    error_log(f"Error creating interface {interface_name} on {device_name}: {str(e)}")
    
    # Save connection IDs for creating connections
    pickleDump('connection_ids', connection_ids)
    print(f"Created {interface_counter} interfaces")

def create_interface_connections(netbox):
    """
    Create connections between interfaces in NetBox
    
    Args:
        netbox: NetBox client instance
    """
    print("Creating interface connections")
    
    # Load connection IDs mapping
    connection_ids = pickleLoad('connection_ids', dict())
    
    # Get connections from Racktables
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT porta,portb,cable FROM Link")
            connections = cursor.fetchall()
    
    # Track completed connections
    connection_count = 0
    
    # Create the connections
    for connection in connections:
        interface_a, interface_b, cable = connection["porta"], connection["portb"], connection["cable"]
        
        # Skip if either interface is missing
        if interface_a not in connection_ids:
            print(f"Interface A (ID: {interface_a}) not found in connection mapping")
            continue
        
        if interface_b not in connection_ids:
            print(f"Interface B (ID: {interface_b}) not found in connection mapping")
            continue
        
        # Get NetBox interface IDs
        netbox_id_a = connection_ids[interface_a]
        netbox_id_b = connection_ids[interface_b]
        
        # Skip if site filtering is enabled and interfaces are not in target site
        if TARGET_SITE:
            # This would require additional checks to get the devices for these interfaces
            # Implement if needed
            pass
        
        # Create the connection
        try:
            netbox.dcim.create_interface_connection(
                netbox_id_a, 
                netbox_id_b, 
                'dcim.interface', 
                'dcim.interface'
            )
            connection_count += 1
            if connection_count % 100 == 0:
                print(f"Created {connection_count} connections")
        except Exception as e:
            error_log(f"Error creating connection between {netbox_id_a} and {netbox_id_b}: {str(e)}")
    
    print(f"Created {connection_count} interface connections")

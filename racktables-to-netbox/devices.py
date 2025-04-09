"""
Device creation and management functions
"""
from slugify import slugify

from racktables_netbox_migration.utils import (
    get_db_connection, get_cursor, pickleDump, error_log
)
from racktables_netbox_migration.db import (
    getAtomsAtRack, getTags, get_hw_type, getDeviceType, get_custom_fields, device_is_in_cluster
)
from racktables_netbox_migration.config import (
    PARENT_OBJTYPE_IDS, OBJTYPE_ID_NAMES, RACKTABLES_MANUFACTURERS,
    PARENT_CHILD_OBJTYPE_ID_PAIRS, FIRST_ASCII_CHARACTER
)

# Global tracking of created objects
global_names = set()
global_devices = []
global_device_roles = set()
global_manufacturers = set()
global_device_types = set()
global_physical_object_ids = set()
global_non_physical_object_ids = set()
asset_tags = set()
serials = dict()

def get_manufacturer_role_type(racktables_object_id, objtype_id, height, is_full_depth):
    """
    Determine manufacturer, role, and type for a device
    
    Args:
        racktables_object_id: Object ID in Racktables
        objtype_id: Object type ID
        height: Device height in U
        is_full_depth: Whether device is full depth
        
    Returns:
        tuple: (manufacturer, device_role, device_type_model)
    """
    original_device_type = getDeviceType(objtype_id)
    manufacturer = original_device_type

    # Add the height to the type model, as well as the binary full_depth or not
    hw_type = get_hw_type(racktables_object_id, serials)
    if hw_type:
        device_type = hw_type

        for racktables_manufacturer in RACKTABLES_MANUFACTURERS:
            if device_type.startswith(racktables_manufacturer) or device_type.startswith(racktables_manufacturer+" "):
                device_type = device_type.replace(racktables_manufacturer," ", 1).lstrip(" ")
                manufacturer = racktables_manufacturer
    else:
        device_type = original_device_type

    device_type_model = "{}-{}U{}".format(device_type, height, "-full" if is_full_depth else "")

    return manufacturer, original_device_type, device_type_model

def create_device_at_location(netbox, device_name, face, start_height, device_role, manufacturer, 
                             device_type_model, site_name, rack_name, asset_no, racktables_device_id):
    """
    Create a device at a specific location in a rack
    
    Args:
        netbox: NetBox client instance
        device_name: Name of the device
        face: Rack face ('front', 'rear')
        start_height: Starting rack unit
        device_role: Device role name
        manufacturer: Manufacturer name
        device_type_model: Device type model
        site_name: Site name
        rack_name: Rack name
        asset_no: Asset number
        racktables_device_id: Original ID in Racktables
        
    Returns:
        tuple: (device_name, device_id)
    """
    global global_devices, global_names, global_device_roles, global_manufacturers, global_device_types, asset_tags
    
    # Check if device already exists at this location
    name_at_location = None
    id_at_location = None

    for device in global_devices:
        if (face == device['face']['value'] and start_height == device['position'] and 
            device_role == device['device_role']['name'] and 
            manufacturer == device['device_type']['manufacturer']['name'] and 
            device_type_model == device['device_type']['model'] and 
            site_name == device['site']['name'] and rack_name == device['rack']['name']):
            name_at_location = device['name']
            id_at_location = device['id']
            break

    if name_at_location is None:
        # Use original name if unique, otherwise append counter
        name_at_location = device_name

        if device_name in global_names:
            name_counter = 1
            while True:
                counter_name = device_name + ".{}".format(name_counter)
                if counter_name not in global_names:
                    name_at_location = counter_name
                    break
                else:
                    name_counter += 1

        # Check if device is in a VM cluster
        device_in_vm_cluster, device_vm_cluster_name, parent_entity_ids = device_is_in_cluster(racktables_device_id)
        
        # Get custom fields for this device
        custom_fields = get_custom_fields(racktables_device_id)
        
        # Get serial number if available
        serial = serials[racktables_device_id] if racktables_device_id in serials else ""

        # Handle asset tag duplicates
        asset_no = asset_no.strip() if asset_no else None
        if asset_no and asset_no in asset_tags:
            asset_no = asset_no + "-1"

        # Create the device
        try:
            device = netbox.dcim.create_device(
                custom_fields=custom_fields,
                face=face,
                cluster={"name": device_vm_cluster_name} if device_in_vm_cluster else None,
                asset_tag=asset_no,
                serial=serial,
                position=start_height,
                name=name_at_location,
                device_role=device_role,
                manufacturer={"name": manufacturer},
                device_type=device_type_model,
                site_name=site_name,
                rack={"name": rack_name}
            )
            
            if asset_no:
                asset_tags.add(asset_no)

            id_at_location = device['id']
            global_names.add(name_at_location)
            global_devices.append(device)
            
            print(f"Created device {name_at_location} at {rack_name} U{start_height} {face}")
        except Exception as e:
            error_log(f"Error creating device {name_at_location}: {str(e)}")
            return None, None
    else:
        print(f"Device {name_at_location} already exists at location")

    return name_at_location, id_at_location

def create_racked_devices(netbox):
    """
    Create devices in racks based on Racktables data
    
    Args:
        netbox: NetBox client instance
    """
    global global_physical_object_ids, global_device_roles, global_manufacturers, global_device_types
    
    print("Creating racked devices")
    
    # Load existing devices, names, roles, manufacturers, and types
    global_devices = netbox.dcim.get_devices()
    print(f"Got {len(global_devices)} existing devices")
    
    global_names = set(device['name'] for device in global_devices)
    global_device_roles = set(role['name'] for role in netbox.dcim.get_device_roles())
    global_manufacturers = set(manufacturer['name'] for manufacturer in netbox.dcim.get_manufacturers())
    global_device_types = set(device_type['model'] for device_type in netbox.dcim.get_device_types())
    
    # Load serial numbers for devices
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT object_id, string_value FROM AttributeValue WHERE attr_id=10014")
            for row in cursor.fetchall():
                serials[row["object_id"]] = row["string_value"] if row["string_value"] else ""
    
    # Get racks from NetBox
    racks = netbox.dcim.get_racks()
    
    # Process each rack and create devices
    for rack in racks:
        rack_name = rack['name']
        site_name = rack['site']['name']
        
        # Skip if site filtering is enabled and this is not the target site
        if TARGET_SITE and site_name != TARGET_SITE:
            continue
        
        # Extract Racktables rack ID from name (temporary solution)
        # In a production environment, you would store this mapping
        rack_id = rack['id']
        
        # Get atoms (device placements) for this rack from Racktables
        atoms = getAtomsAtRack(rack_id)
        
        if atoms:
            # Create devices based on atoms
            create_devices_in_rack(netbox, atoms, rack_name, site_name, rack['id'])
    
    # Save tracking of physical devices for interface creation
    pickleDump("global_physical_object_ids", global_physical_object_ids)

def create_devices_in_rack(netbox, atoms, rack_name, site_name, rack_id):
    """
    Create devices in a rack based on atoms data
    
    Args:
        netbox: NetBox client instance
        atoms: List of atom dictionaries
        rack_name: Rack name
        site_name: Site name
        rack_id: Rack ID in NetBox
    """
    # Put positions into dict based on Id
    atoms_dict = {}
    for atom in atoms:
        key = str(atom["object_id"])
        if key not in atoms_dict:
            atoms_dict[key] = [atom]
        else:
            atoms_dict[key].append(atom)
    
    # Find devices that may need to be split due to non-contiguous placement
    added_atom_objects = {}
    separated_Ids = False
    
    # Process devices in the rack
    for Id in atoms_dict:
        # Skip null ID (reservations)
        if Id == "None":
            continue
        
        real_id = int(Id)
        
        # Get device info from Racktables
        with get_db_connection() as connection:
            with get_cursor(connection) as cursor:
                cursor.execute("SELECT id,name,label,objtype_id,has_problems,comment,asset_no FROM Object WHERE id=%s", (real_id,))
                info = cursor.fetchone()
        
        if not info:
            continue
        
        objtype_id = info["objtype_id"]
        device_name = info["name"]
        asset_no = info["asset_no"]
        
        # Get device tags
        device_tags = getTags("object", real_id)
        
        # Determine face and depth
        if 'rear' not in [atom["atom"] for atom in atoms_dict[Id]]:
            face = 'front'
            is_full_depth = False
        elif 'front' not in [atom["atom"] for atom in atoms_dict[Id]]:
            face = 'rear'
            is_full_depth = False
        else:
            face = 'front'  # NetBox doesn't have 'both'
            is_full_depth = True
        
        # Calculate height
        start_height = min([atom["unit_no"] for atom in atoms_dict[Id]])
        height = max([atom["unit_no"] for atom in atoms_dict[Id]]) - start_height + 1
        
        # Get device details
        manufacturer, device_role, device_type_model = get_manufacturer_role_type(
            real_id, objtype_id, height, is_full_depth
        )
        
        # Create device role if needed
        if device_role not in global_device_roles:
            netbox.dcim.create_device_role(device_role, "ffffff", slugify(device_role))
            global_device_roles.add(device_role)
        
        # Create manufacturer if needed
        if manufacturer not in global_manufacturers:
            netbox.dcim.create_manufacturer(manufacturer, slugify(manufacturer))
            global_manufacturers.add(manufacturer)
        
        # Adjust device type for parent devices
        if objtype_id in PARENT_OBJTYPE_IDS:
            device_type_model += "-parent"
        
        # Create device type if needed
        if device_type_model not in global_device_types:
            netbox.dcim.create_device_type(
                model=device_type_model,
                manufacturer={"name": manufacturer},
                slug=slugify(device_type_model),
                u_height=height,
                is_full_depth=is_full_depth,
                tags=device_tags,
                subdevice_role="parent" if objtype_id in PARENT_OBJTYPE_IDS else ""
            )
            global_device_types.add(device_type_model)
        
        # Create the device
        device_name, device_id = create_device_at_location(
            netbox, device_name, face, start_height, device_role, manufacturer,
            device_type_model, site_name, rack_name, asset_no, real_id
        )
        
        if device_name and device_id:
            # Store device information for interface creation
            global_physical_object_ids.add((device_name, info["id"], device_id, objtype_id))

def create_non_racked_devices(netbox):
    """
    Create non-racked devices from Racktables in NetBox
    
    Args:
        netbox: NetBox client instance
    """
    global global_non_physical_object_ids
    
    print("Creating non-racked devices")
    
    # Load existing tracking of non-physical devices
    global_non_physical_object_ids = pickleLoad("global_non_physical_object_ids", set())
    
    # Process each object type
    for objtype_id in OBJTYPE_ID_NAMES:
        print(f"Processing {OBJTYPE_ID_NAMES[objtype_id]} devices")
        
        # Get all objects of this type from Racktables
        with get_db_connection() as connection:
            with get_cursor(connection) as cursor:
                cursor.execute("SELECT id,name,label,asset_no,comment FROM Object WHERE objtype_id=%s", (objtype_id,))
                objs = cursor.fetchall()
        
        # Convert to the format expected by create_parent_child_devices
        objs_list = [(obj["id"], obj["name"], obj["label"], obj["asset_no"], obj["comment"]) for obj in objs]
        
        # Create devices
        children_without_parents = create_parent_child_devices(netbox, objs_list, objtype_id)
        
        # Try again for children whose parents weren't created yet
        if children_without_parents:
            create_parent_child_devices(netbox, children_without_parents, objtype_id)
    
    # Save tracking of non-physical devices for interface creation
    pickleDump("global_non_physical_object_ids", global_non_physical_object_ids)

def create_parent_child_devices(netbox, data, objtype_id):
    """
    Create devices and establish parent-child relationships
    
    Args:
        netbox: NetBox client instance
        data: List of device data tuples
        objtype_id: Object type ID
        
    Returns:
        list: Devices that couldn't be created due to missing parents
    """
    global global_non_physical_object_ids, asset_tags
    
    # Track devices that couldn't be created due to missing parents
    not_created_parents = []
    
    # Get existing data from NetBox
    existing_device_names = set(device['name'].strip() for device in netbox.dcim.get_devices() if device['name'])
    
    # Map device bay names by parent device
    existing_device_bays = {}
    for device_bay in netbox.dcim.get_device_bays():
        parent_name = device_bay['device']['name']
        if parent_name not in existing_device_bays:
            existing_device_bays[parent_name] = set()
        existing_device_bays[parent_name].add(device_bay['name'])
    
    # Process each device
    for racktables_device_id, object_name, label, asset_no, comment in data:
        # Skip if no name
        if not object_name:
            continue
        
        object_name = object_name.strip()
        
        # Skip if already exists
        if object_name in existing_device_names:
            continue
        
        # Create device in the "None" site
        site_name = "None"
        
        # Get device details
        manufacturer, device_role, device_type_model = get_manufacturer_role_type(
            racktables_device_id, objtype_id, 0, False
        )
        
        # Check if device is in a VM cluster
        device_in_vm_cluster, device_vm_cluster_name, parent_entity_ids = device_is_in_cluster(racktables_device_id)
        
        # Determine if device is a child or parent
        is_child = False
        is_parent = False
        subdevice_role = ""
        is_child_parent_name = None
        
        # Check for parent-child relationships
        for parent_from_pairs_objtype_id, child_from_pairs_objtype_id in PARENT_CHILD_OBJTYPE_ID_PAIRS:
            if objtype_id == child_from_pairs_objtype_id:
                # Check for parent
                for parent_entity_id in parent_entity_ids:
                    with get_db_connection() as connection:
                        with get_cursor(connection) as cursor:
                            cursor.execute("SELECT objtype_id,name FROM Object WHERE id=%s", (parent_entity_id,))
                            result = cursor.fetchone()
                            if result and result["objtype_id"] == parent_from_pairs_objtype_id:
                                is_child = True
                                is_child_parent_name = result["name"].strip()
                                break
                
                if is_child:
                    device_type_model += "-child"
                    subdevice_role = "child"
                    break
            
            elif objtype_id == parent_from_pairs_objtype_id:
                is_parent = True
                device_type_model += "-parent"
                subdevice_role = "parent"
                break
        
        # Create device type if needed
        if device_type_model not in global_device_types:
            try:
                netbox.dcim.create_device_type(
                    model=device_type_model,
                    slug=slugify(device_type_model),
                    manufacturer={"name": manufacturer},
                    u_height=0,
                    subdevice_role=subdevice_role
                )
                global_device_types.add(device_type_model)
            except Exception as e:
                error_log(f"Error creating device type {device_type_model}: {str(e)}")
        
        # Get device tags and custom fields
        device_tags = getTags("object", racktables_device_id)
        custom_fields = get_custom_fields(racktables_device_id, {"Device_Label": label})
        serial = serials.get(racktables_device_id, "")
        
        # Handle asset tag duplicates
        asset_no = asset_no.strip() if asset_no else None
        if asset_no and asset_no in asset_tags:
            asset_no = f"{asset_no}-1"
        
        # Create the device
        try:
            device = netbox.dcim.create_device(
                name=object_name,
                cluster={"name": device_vm_cluster_name} if device_in_vm_cluster else None,
                asset_tag=asset_no,
                serial=serial,
                custom_fields=custom_fields,
                device_type=device_type_model,
                device_role=device_role,
                site_name=site_name,
                comment=comment[:200] if comment else "",
                tags=device_tags
            )
            
            if asset_no:
                asset_tags.add(asset_no)
            
            # Track created device
            global_non_physical_object_ids.add((object_name, racktables_device_id, device['id'], objtype_id))
            print(f"Created non-racked device: {object_name}")
            
            # Handle child device in parent's device bay
            if is_child and is_child_parent_name:
                # Find the parent device
                parent_devices = netbox.dcim.get_devices(name=is_child_parent_name)
                if parent_devices:
                    parent_device = parent_devices[0]
                    
                    # Determine new bay name
                    if is_child_parent_name in existing_device_bays:
                        try:
                            new_bay_number = max(int(bay.split('-')[1]) for bay in existing_device_bays[is_child_parent_name]) + 1
                        except ValueError:
                            new_bay_number = 1
                    else:
                        new_bay_number = 1
                    
                    new_bay_name = f"bay-{new_bay_number}"
                    
                    # Create device bay
                    try:
                        bay = netbox.dcim.create_device_bay(
                            name=new_bay_name,
                            device_id=parent_device['id'],
                            installed_device_id=device['id']
                        )
                        existing_device_bays.setdefault(is_child_parent_name, set()).add(new_bay_name)
                        print(f"Added {object_name} to {is_child_parent_name} in bay {new_bay_name}")
                    except Exception as e:
                        error_log(f"Error creating device bay for {object_name}: {str(e)}")
        
        except Exception as e:
            error_log(f"Error creating device {object_name}: {str(e)}")
            not_created_parents.append((racktables_device_id, object_name, label, asset_no, comment))
    
    return not_created_parents

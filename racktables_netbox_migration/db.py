"""
Database helper functions for accessing Racktables data
"""
from racktables_netbox_migration.utils import get_db_connection, get_cursor
from racktables_netbox_migration.config import INTERFACE_NAME_MAPPINGS

def getRackHeight(rackId):
    """
    Get the height of a rack from Racktables

    Args:
        rackId: ID of the rack

    Returns:
        int: Height of the rack in units, or 0 if not found
    """
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT uint_value FROM AttributeValue WHERE object_id=%s AND attr_id=27", (rackId,))
            result = cursor.fetchone()
            return result["uint_value"] if result else 0

def get_hw_type(racktables_object_id, hw_types):
    """
    Get the hardware type for a given Racktables object

    Args:
        racktables_object_id: ID of the object in Racktables
        hw_types: Dictionary mapping hw type IDs to names

    Returns:
        str: Hardware type name, or None if not found
    """
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT uint_value FROM AttributeValue WHERE object_id=%s AND attr_id=2", (racktables_object_id,))
            uint = cursor.fetchone()

            # If uint_value is not in hw_types, return a default or the uint_value as a string
            if uint:
                hw_type = hw_types.get(uint["uint_value"], f"Unknown Type ({uint['uint_value']})")
                return hw_type

            return None

def getRowsAtSite(siteId):
    """
    Get all rows at a given site

    Args:
        siteId: ID of the site

    Returns:
        list: List of row dictionaries
    """
    rows = []
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT child_entity_id FROM EntityLink WHERE parent_entity_type='location' AND parent_entity_id=%s AND child_entity_type='row'", (siteId,))
            rowIds = cursor.fetchall()
            for rowId in rowIds:
                cursor.execute("SELECT id,name,label,asset_no,comment FROM Object WHERE id=%s", (rowId["child_entity_id"],))
                rows += cursor.fetchall()
    return rows

def getRacksAtRow(rowId):
    """
    Get all racks in a given row

    Args:
        rowId: ID of the row

    Returns:
        list: List of rack dictionaries
    """
    racks = []
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT child_entity_id FROM EntityLink WHERE parent_entity_type='row' AND parent_entity_id=%s AND child_entity_type='rack'", (rowId,))
            rackIds = cursor.fetchall()
            for rackId in rackIds:
                cursor.execute("SELECT id,name,label,asset_no,comment FROM Object WHERE id=%s", (rackId["child_entity_id"],))
                racks += cursor.fetchall()
    return racks

def getAtomsAtRack(rackId):
    """
    Get all atoms (placement units) in a rack

    Args:
        rackId: ID of the rack

    Returns:
        list: List of atom dictionaries
    """
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT rack_id,unit_no,atom,state,object_id FROM RackSpace WHERE rack_id=%s", (rackId,))
            return cursor.fetchall()

def getTags(entity_realm, entity_id):
    """
    Get all tags for a given entity

    Args:
        entity_realm: Type of entity (e.g., 'object', 'rack')
        entity_id: ID of the entity

    Returns:
        list: List of tag dictionaries
    """
    tags = []
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT tag_id FROM TagStorage WHERE entity_id=%s AND entity_realm=%s", (entity_id, entity_realm))
            tag_ids = [x["tag_id"] for x in cursor.fetchall()]
            for tag_id in tag_ids:
                cursor.execute("SELECT tag FROM TagTree WHERE id=%s", (tag_id,))
                tags += cursor.fetchall()
    return [{'name': tag["tag"]} for tag in tags]

def getDeviceType(objtype_id):
    """
    Get the device type name for a given object type ID

    Args:
        objtype_id: Object type ID

    Returns:
        str: Device type name, or None if not found
    """
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT dict_key,dict_value FROM Dictionary WHERE dict_key=%s", (objtype_id,))
            result = cursor.fetchone()
            return result["dict_value"] if result else None

def get_custom_fields(racktables_object_id, slugified_attributes, initial_dict=None):
    """
    Get all custom field values for a given object

    Args:
        racktables_object_id: ID of the object in Racktables
        slugified_attributes: Dictionary mapping attribute IDs to slugified names
        initial_dict: Initial dictionary to populate (optional)

    Returns:
        dict: Dictionary of custom field values
    """
    custom_fields = initial_dict if initial_dict else dict()

    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT attr_id,string_value,uint_value FROM AttributeValue WHERE object_id=%s", (racktables_object_id,))
            attributes = cursor.fetchall()

            for attr in attributes:
                attr_id = attr["attr_id"]
                string_value = attr["string_value"]
                uint_value = attr["uint_value"]

                # Skip specific known attributes or add more as needed
                if attr_id in (2, 27, 10014):
                    continue

                # Only process if the attribute ID is in the slugified_attributes
                if attr_id in slugified_attributes:
                    custom_fields[slugified_attributes[attr_id]] = string_value if string_value else uint_value

    return custom_fields

def device_is_in_cluster(device_id):
    """
    Check if a device is in a VM cluster

    Args:
        device_id: ID of the device

    Returns:
        tuple: (is_in_cluster, cluster_name, parent_entity_ids)
    """
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT parent_entity_id FROM EntityLink WHERE parent_entity_type=\"object\" AND child_entity_id=%s", (device_id,))
            parent_entity_ids = [parent_entity_id["parent_entity_id"] for parent_entity_id in cursor.fetchall()]

            for parent_entity_id in parent_entity_ids:
                cursor.execute("SELECT objtype_id,name FROM Object WHERE id=%s", (parent_entity_id,))
                result = cursor.fetchone()
                if result:
                    parent_objtype_id, parent_name = result["objtype_id"], result["name"]

                    if parent_objtype_id == 1505:  # VM Cluster
                        return True, parent_name, parent_entity_ids

    return False, None, parent_entity_ids

def change_interface_name(interface_name, objtype_id):
    """
    Clean up interface names based on device type and standardization rules

    Args:
        interface_name: Original interface name
        objtype_id: Object type ID of the device

    Returns:
        str: Standardized interface name
    """
    interface_name = interface_name.strip()

    if objtype_id in (7, 8):  # Router or Network Switch
        for prefix in INTERFACE_NAME_MAPPINGS:
            # Make sure the prefix is followed by a number
            if interface_name.startswith(prefix) and len(interface_name) > len(prefix) and interface_name[len(prefix)] in "0123456789- ":
                interface_name = interface_name.replace(prefix, INTERFACE_NAME_MAPPINGS[prefix], 1)

    return interface_name

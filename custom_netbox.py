"""
This module extends the python-netbox library with custom methods needed for the migration.
It monkey-patches the Dcim class to add the required methods.
"""

from netbox import NetBox
from netbox.dcim import Dcim
import netbox.exceptions as exceptions


# Add the missing get_interfaces_custom method to Dcim class
def get_interfaces_custom(self, limit, offset, **kwargs):
    """Return interfaces with custom limit and offset parameters

    :param limit: Maximum number of results to return
    :param offset: Number of results to skip before beginning
    :param kwargs: Optional filter arguments
    :return: List of interfaces
    """
    return self.netbox_con.get('/dcim/interfaces/', limit=limit, offset=offset, **kwargs)


# Add or update the create_interface_connection method to use the cables API
def create_interface_connection(self, termination_a_id, termination_b_id, termination_a_type, termination_b_type, **kwargs):
    """Create a new interface-connection

    :param termination_a_id: id of the source interface
    :param termination_a_type: type of source interface ("dcim.consoleport", "dcim.consoleserverport", "dcim.interface")
    :param termination_b_id: id of the destination interface
    :param termination_b_type: type of destination interface ("dcim.consoleport", "dcim.consoleserverport", "dcim.interface")
    :param kwargs: Optional arguments
    :return: netbox object if successful otherwise raise CreateException
    """
    required_fields = {
        "termination_a_id": termination_a_id, 
        "termination_a_type": termination_a_type, 
        "termination_b_id": termination_b_id, 
        "termination_b_type": termination_b_type
    }
    return self.netbox_con.post('/dcim/cables/', required_fields, **kwargs)


# Add the get_device_bays method if it's missing
def get_device_bays(self, **kwargs):
    """Return the device bays"""
    return self.netbox_con.get('/dcim/device-bays/', **kwargs)


# Apply the monkey patches
def extend_netbox():
    """Extend the NetBox library with the necessary methods for migration"""
    # Add the custom methods to the Dcim class
    Dcim.get_interfaces_custom = get_interfaces_custom
    Dcim.create_interface_connection = create_interface_connection
    
    # Only add get_device_bays if it doesn't exist
    if not hasattr(Dcim, 'get_device_bays'):
        Dcim.get_device_bays = get_device_bays
    
    return True


# Create a custom NetBox class that extends the original
class ExtendedNetBox(NetBox):
    """Extended NetBox class with additional methods for migration"""
    
    def __init__(self, host, **kwargs):
        super().__init__(host, **kwargs)
        # Apply the extensions
        extend_netbox()

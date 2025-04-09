"""
Bridge module that imports NetBox from custom_netbox
This allows code that imports from 'netbox' to work with our custom wrapper
"""
from custom_netbox import ExtendedNetBox as NetBox

#!/usr/bin/env python3
"""
Extended migration script for additional Racktables data
"""
import os
import sys

# Add the current directory to the Python path if it's not already there
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from racktables_netbox_migration.config import *
from racktables_netbox_migration.utils import *
from racktables_netbox_migration.db import *

# Import the custom NetBox class
from custom_netbox import NetBox

def verify_site_exists(netbox, site_name):
    """
    Verify that the specified site exists in NetBox
    
    Args:
        netbox: NetBox client instance
        site_name: Name of site to verify
        
    Returns:
        bool: True if site exists or if site_name is None, False otherwise
    """
    if not site_name:
        return True  # No site filter, proceed with all
    
    sites = netbox.dcim.get_sites(name=site_name)
    if sites:
        print(f"Target site '{site_name}' found - restricting migration to this site")
        return True
    else:
        print(f"ERROR: Target site '{site_name}' not found in NetBox")
        return False

def migrate_additional():
    """Run the additional migration components"""
    # Initialize NetBox connection
    netbox = NetBox(host=NB_HOST, port=NB_PORT, use_ssl=NB_USE_SSL, auth_token=NB_TOKEN)
    
    # Check if target site exists when site filtering is enabled
    if not verify_site_exists(netbox, TARGET_SITE):
        print("Migration aborted: Target site not found")
        return
    
    # Run additional migration components
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            if CREATE_PATCH_CABLES:
                from racktables_netbox_migration.extended.patch_cables import migrate_patch_cables
                migrate_patch_cables(cursor, netbox)
            
            if CREATE_FILES:
                from racktables_netbox_migration.extended.files import migrate_files
                migrate_files(cursor, netbox)
                
            if CREATE_VIRTUAL_SERVICES:
                from racktables_netbox_migration.extended.services import migrate_virtual_services
                migrate_virtual_services(cursor, netbox)
                
            if CREATE_NAT_MAPPINGS:
                from racktables_netbox_migration.extended.nat import migrate_nat_mappings
                migrate_nat_mappings(cursor, netbox)
                
            if CREATE_LOAD_BALANCING:
                from racktables_netbox_migration.extended.load_balancer import migrate_load_balancing
                migrate_load_balancing(cursor, netbox)
                
            if CREATE_MONITORING_DATA:
                from racktables_netbox_migration.extended.monitoring import migrate_monitoring
                migrate_monitoring(cursor, netbox)
    
    # Create available subnets after all other migration steps
    if CREATE_AVAILABLE_SUBNETS:
        from racktables_netbox_migration.extended.available_subnets import create_available_subnets
        create_available_subnets(netbox)
    
    print("\nAdditional migration completed successfully!")

if __name__ == "__main__":
    migrate_additional()

#!/usr/bin/env python3
"""
Extended migration script for additional Racktables data
"""

from racktables_netbox_migration.config import *
from racktables_netbox_migration.utils import *
from racktables_netbox_migration.db import *

def migrate_additional():
    """Run the additional migration components"""
    # Check if target site exists when site filtering is enabled
    if not verify_site_exists(netbox, TARGET_SITE):
        print("Migration aborted: Target site not found")
        return
    
    # Initialize NetBox connection
    netbox = NetBox(host=NB_HOST, port=NB_PORT, use_ssl=NB_USE_SSL, auth_token=NB_TOKEN)
    
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

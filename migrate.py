#!/usr/bin/env python3
"""
Main migration script for transferring data from Racktables to NetBox
"""

# Import the modular components
from racktables_netbox_migration.config import *
from racktables_netbox_migration.utils import *
from racktables_netbox_migration.db import *

# Import necessary modules
import ipaddress
import random
import time

def main():
    """Main migration function"""
    # Check if target site exists when site filtering is enabled
    if not verify_site_exists(netbox, TARGET_SITE):
        print("Migration aborted: Target site not found")
        return
    
    # Initialize NetBox connection
    netbox = NetBox(host=NB_HOST, port=NB_PORT, use_ssl=NB_USE_SSL, auth_token=NB_TOKEN)
    
    # Create standard tags
    global_tags = set(tag['name'] for tag in netbox.extras.get_tags())
    create_global_tags(netbox, (IPV4_TAG, IPV6_TAG))
    
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            cursor.execute("SELECT tag FROM TagTree")
            create_global_tags(netbox, (row["tag"] for row in cursor.fetchall()))
    
    print("Created tags")
    
    # Process components according to flags
    if CREATE_VLAN_GROUPS:
        import racktables_netbox_migration.vlans as vlans
        vlans.create_vlan_groups(netbox)
    
    if CREATE_VLANS:
        import racktables_netbox_migration.vlans as vlans
        vlans.create_vlans(netbox)
    
    if CREATE_MOUNTED_VMS or CREATE_UNMOUNTED_VMS:
        import racktables_netbox_migration.vms as vms
        vms.create_vms(netbox, CREATE_MOUNTED_VMS, CREATE_UNMOUNTED_VMS)
    
    if CREATE_RACKED_DEVICES:
        import racktables_netbox_migration.devices as devices
        import racktables_netbox_migration.sites as sites
        sites.create_sites_and_racks(netbox)
        devices.create_racked_devices(netbox)
    
    if CREATE_NON_RACKED_DEVICES:
        import racktables_netbox_migration.devices as devices
        devices.create_non_racked_devices(netbox)
    
    if CREATE_INTERFACES:
        import racktables_netbox_migration.interfaces as interfaces
        interfaces.create_interfaces(netbox)
    
    if CREATE_INTERFACE_CONNECTIONS:
        import racktables_netbox_migration.interfaces as interfaces
        interfaces.create_interface_connections(netbox)
    
    if CREATE_IPV4 or CREATE_IPV6:
        import racktables_netbox_migration.ips as ips
        versions = []
        if CREATE_IPV4:
            versions.append("4")
        if CREATE_IPV6:
            versions.append("6")
        
        for IP in versions:
            if CREATE_IP_NETWORKS:
                ips.create_ip_networks(netbox, IP, TARGET_SITE)
            
            if CREATE_IP_ALLOCATED:
                ips.create_ip_allocated(netbox, IP, TARGET_SITE)
            
            if CREATE_IP_NOT_ALLOCATED:
                ips.create_ip_not_allocated(netbox, IP, TARGET_SITE)
    
    print("Base migration completed successfully!")

if __name__ == "__main__":
    main()

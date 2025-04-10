#!/usr/bin/env python3
"""
Unified migration script for Racktables to NetBox
"""

import os
import sys
import argparse
import importlib.util
import logging
from datetime import datetime

# Setup directory-based imports that work without package installation
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Import core modules
from migration.config import *
from migration.utils import *
from migration.db import *
from migration.custom_netbox import NetBox

def check_config():
    """Verify configuration is not using defaults"""
    default_token = "0123456789abcdef0123456789abcdef01234567"
    if NB_TOKEN == default_token:
        logging.error("Default API token detected in config.py")
        logging.error("Please update migration/config.py with your NetBox configuration")
        return False
    
    if DB_CONFIG['password'] == 'secure-password':
        logging.error("Default database password detected in config.py")
        logging.error("Please update migration/config.py with your database credentials")
        return False
    
    if NB_HOST == "localhost" and NB_PORT == 8000:
        logging.warning("Using default NetBox connection settings (localhost:8000)")
        logging.warning("If this is not your actual NetBox server, update migration/config.py")
    
    return True

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Migrate data from Racktables to NetBox')
    parser.add_argument('--site', type=str, help='Target site name to restrict migration to')
    parser.add_argument('--config', type=str, help='Path to custom configuration file')
    parser.add_argument('--basic-only', action='store_true', help='Run only basic migration (no extended components)')
    parser.add_argument('--extended-only', action='store_true', help='Run only extended migration components')
    parser.add_argument('--skip-custom-fields', action='store_true', help='Skip setting up custom fields')
    return parser.parse_args()

def verify_site_exists(netbox, site_name):
    """Verify that the specified site exists in NetBox"""
    if not site_name:
        return True
    
    sites = netbox.dcim.get_sites(name=site_name)
    if sites:
        print(f"Target site '{site_name}' found - restricting migration to this site")
        return True
    else:
        print(f"ERROR: Target site '{site_name}' not found in NetBox")
        return False

def setup_custom_fields():
    """Run custom fields setup script"""
    try:
        script_path = os.path.join(BASE_DIR, "migration", "set_custom_fields.py")
        spec = importlib.util.spec_from_file_location("set_custom_fields", script_path)
        custom_fields = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(custom_fields)
        custom_fields.main()
        return True
    except Exception as e:
        print(f"Error setting up custom fields: {e}")
        return False

def run_base_migration(netbox):
    """Run the basic migration components"""
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
        import migration.vlans as vlans
        vlans.create_vlan_groups(netbox)
    
    if CREATE_VLANS:
        import migration.vlans as vlans
        vlans.create_vlans(netbox)
    
    if CREATE_MOUNTED_VMS or CREATE_UNMOUNTED_VMS:
        import migration.vms as vms
        vms.create_vms(netbox, CREATE_MOUNTED_VMS, CREATE_UNMOUNTED_VMS)
    
    if CREATE_RACKED_DEVICES:
        import migration.devices as devices
        import migration.sites as sites
        sites.create_sites_and_racks(netbox)
        devices.create_racked_devices(netbox)
    
    if CREATE_NON_RACKED_DEVICES:
        import migration.devices as devices
        devices.create_non_racked_devices(netbox)
    
    if CREATE_INTERFACES:
        import migration.interfaces as interfaces
        interfaces.create_interfaces(netbox)
    
    if CREATE_INTERFACE_CONNECTIONS:
        import migration.interfaces as interfaces
        interfaces.create_interface_connections(netbox)
    
    if CREATE_IPV4 or CREATE_IPV6:
        import migration.ips as ips
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
    return True

def run_extended_migration(netbox):
    """Run the additional migration components"""
    with get_db_connection() as connection:
        with get_cursor(connection) as cursor:
            if CREATE_PATCH_CABLES:
                from migration.extended.patch_cables import migrate_patch_cables
                migrate_patch_cables(cursor, netbox)
            
            if CREATE_FILES:
                from migration.extended.files import migrate_files
                migrate_files(cursor, netbox)
                
            if CREATE_VIRTUAL_SERVICES:
                from migration.extended.services import migrate_virtual_services
                migrate_virtual_services(cursor, netbox)
                
            if CREATE_NAT_MAPPINGS:
                from migration.extended.nat import migrate_nat_mappings
                migrate_nat_mappings(cursor, netbox)
                
            if CREATE_LOAD_BALANCING:
                from migration.extended.load_balancer import migrate_load_balancing
                migrate_load_balancing(cursor, netbox)
                
            if CREATE_MONITORING_DATA:
                from migration.extended.monitoring import migrate_monitoring
                migrate_monitoring(cursor, netbox)
    
    # Create available subnets after all other migration steps
    if CREATE_AVAILABLE_SUBNETS:
        from migration.extended.available_subnets import create_available_subnets
        create_available_subnets(netbox)
    
    print("Extended migration completed successfully!")
    return True

def main():
    """Main migration function"""
    # Parse command line arguments
    args = parse_arguments()
    
    # Set up logging
    log_filename = f"migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set target site if specified
    if args.site:
        global TARGET_SITE
        TARGET_SITE = args.site
        logging.info(f"Filtering migration for site: {TARGET_SITE}")
    
    # Load custom config if specified
    if args.config:
        if os.path.exists(args.config):
            try:
                exec(open(args.config).read())
                logging.info(f"Loaded custom configuration from {args.config}")
            except Exception as e:
                logging.error(f"Error loading config: {e}")
                return False
        else:
            logging.error(f"Config file not found: {args.config}")
            return False
    
    # Verify configuration is not using defaults
    if not check_config():
        return False
    
    # Attempt database connection
    try:
        logging.info("Testing database connection...")
        with get_db_connection() as connection:
            logging.info("Database connection successful")
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return False
    
    # Set up custom fields if not skipped
    if not args.skip_custom_fields:
        logging.info("Setting up custom fields...")
        if not setup_custom_fields():
            logging.warning("Custom fields setup had errors. Continuing with migration...")
    
    # Initialize NetBox connection
    logging.info("Initializing NetBox connection...")
    try:
        netbox = NetBox(host=NB_HOST, port=NB_PORT, use_ssl=NB_USE_SSL, auth_token=NB_TOKEN)
    except Exception as e:
        logging.error(f"Failed to initialize NetBox connection: {e}")
        return False
    
    # Verify site exists
    if not verify_site_exists(netbox, TARGET_SITE):
        logging.error("Migration aborted: Target site not found")
        return False
    
    # Run migrations based on arguments
    success = True
    
    if not args.extended_only:
        logging.info("Starting base migration...")
        success = run_base_migration(netbox) and success
    
    if not args.basic_only:
        logging.info("Starting extended migration...")
        success = run_extended_migration(netbox) and success
    
    if success:
        logging.info("Migration completed successfully!")
    else:
        logging.error("Migration completed with errors. Check log for details.")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

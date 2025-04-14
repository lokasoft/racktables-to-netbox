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

# Add parent directory to path to allow running directly
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)

# Define BASE_DIR for custom fields setup
BASE_DIR = os.path.dirname(SCRIPT_DIR)

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
    parser.add_argument('--tenant', type=str, help='Target tenant name to restrict migration to')
    parser.add_argument('--config', type=str, help='Path to custom configuration file')
    parser.add_argument('--basic-only', action='store_true', help='Run only basic migration (no extended components)')
    parser.add_argument('--extended-only', action='store_true', help='Run only extended migration components')
    parser.add_argument('--skip-custom-fields', action='store_true', help='Skip setting up custom fields')
    return parser.parse_args()

def create_helper_modules():
    """Create required helper modules if they don't exist"""
    # Create directory if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "migration"), exist_ok=True)
    
    # Create netbox_status.py module
    netbox_status_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migration", "netbox_status.py")
    if not os.path.exists(netbox_status_path):
        with open(netbox_status_path, 'w') as f:
            f.write("""\"\"\"
Helper module to determine valid NetBox statuses across versions
Can be imported by other modules to ensure consistent status handling
\"\"\"
import requests
import logging
from migration.config import NB_HOST, NB_PORT, NB_TOKEN, NB_USE_SSL

# Cache for valid status choices
_valid_status_choices = {
    'prefix': None,
    'ip_address': None
}

def get_valid_status_choices(netbox, object_type):
    \"\"\"
    Get valid status choices for a specific object type in NetBox
    
    Args:
        netbox: NetBox client instance
        object_type: Type of object to get status choices for (e.g., 'prefix')
        
    Returns:
        list: List of valid status choices
    \"\"\"
    global _valid_status_choices
    
    # Return cached choices if available
    if _valid_status_choices[object_type]:
        return _valid_status_choices[object_type]
    
    # API endpoints for different object types
    endpoints = {
        'prefix': 'ipam/prefixes',
        'ip_address': 'ipam/ip-addresses'
    }
    
    # Determine URL based on object type
    if object_type not in endpoints:
        logging.error(f"Invalid object type: {object_type}")
        return ['active']  # Default fallback
    
    protocol = "https" if NB_USE_SSL else "http"
    url = f"{protocol}://{NB_HOST}:{NB_PORT}/api/{endpoints[object_type]}/choices/"
    
    try:
        headers = {"Authorization": f"Token {NB_TOKEN}"}
        response = requests.get(url, headers=headers, verify=NB_USE_SSL)
        
        if response.status_code == 200:
            choices_data = response.json()
            # Extract status choices from the response
            status_choices = []
            
            # Different NetBox versions have different response formats
            if 'status' in choices_data:
                # Newer NetBox versions
                status_choices = [choice[0] for choice in choices_data['status']]
            elif 'choices' in choices_data and 'status' in choices_data['choices']:
                # Older NetBox versions
                status_choices = [choice[0] for choice in choices_data['choices']['status']]
            
            if status_choices:
                # Cache the results
                _valid_status_choices[object_type] = status_choices
                print(f"Valid {object_type} status choices: {', '.join(status_choices)}")
                return status_choices
        
        logging.error(f"Failed to get status choices for {object_type}: {response.status_code}")
    except Exception as e:
        logging.error(f"Error getting status choices for {object_type}: {str(e)}")
    
    # Default fallback for common statuses
    fallback = ['active', 'container', 'reserved']
    _valid_status_choices[object_type] = fallback
    return fallback

def determine_prefix_status(prefix_name, comment, valid_statuses=None):
    \"\"\"
    Determine the appropriate NetBox status for a prefix based on its name and comments
    
    Args:
        prefix_name: Name of the prefix from Racktables
        comment: Comment for the prefix from Racktables
        valid_statuses: List of valid status choices in NetBox
        
    Returns:
        str: Most appropriate status for the prefix
    \"\"\"
    # Use default statuses if none provided
    if valid_statuses is None:
        valid_statuses = ['active', 'container', 'reserved', 'deprecated']
    
    # Default to 'container' or first valid status if name/comment are empty
    if (not prefix_name or prefix_name.strip() == "") and (not comment or comment.strip() == ""):
        # For empty prefixes, use container (if available) or first valid status
        return 'container' if 'container' in valid_statuses else valid_statuses[0]
    
    # Determine status based on content patterns
    lower_name = prefix_name.lower() if prefix_name else ""
    lower_comment = comment.lower() if comment else ""
    
    # Check for hints that the prefix is specifically reserved
    if any(term in lower_name or term in lower_comment for term in 
           ['reserved', 'hold', 'future', 'planned']):
        return 'reserved' if 'reserved' in valid_statuses else 'active'
    
    # Check for hints that the prefix is deprecated
    if any(term in lower_name or term in lower_comment for term in 
           ['deprecated', 'obsolete', 'old', 'inactive', 'decommissioned']):
        return 'deprecated' if 'deprecated' in valid_statuses else 'active'
    
    # Check for specific hints that the prefix should be a container
    if any(term in lower_name or term in lower_comment for term in 
           ['container', 'parent', 'supernet', 'aggregate']):
        return 'container' if 'container' in valid_statuses else 'active'
    
    # Check for hints that this is available/unused space
    if any(term in lower_name or term in lower_comment for term in 
           ['available', 'unused', 'free', '[here be dragons', '[create network here]', 'unallocated']):
        return 'container' if 'container' in valid_statuses else 'active'
    
    # Check for hints that this is actively used
    if any(term in lower_name or term in lower_comment for term in 
           ['in use', 'used', 'active', 'production', 'allocated']):
        return 'active' if 'active' in valid_statuses else valid_statuses[0]
    
    # When we can't clearly determine from the content, default to 'active' for anything with a name/comment
    # This assumes that if someone took the time to name it, it's likely in use
    return 'active' if 'active' in valid_statuses else valid_statuses[0]
""")
    
    # Create site_tenant.py module
    site_tenant_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migration", "site_tenant.py")
    if not os.path.exists(site_tenant_path):
        with open(site_tenant_path, 'w') as f:
            f.write("""\"\"\"
Add site and tenant associations to all NetBox objects
\"\"\"
import os
import sys
import logging
from slugify import slugify

def ensure_site_tenant_associations(netbox, site_name, tenant_name):
    \"\"\"
    Ensures that site and tenant IDs are properly retrieved and set globally
    
    Args:
        netbox: NetBox client instance
        site_name: Site name to use
        tenant_name: Tenant name to use
        
    Returns:
        tuple: (site_id, tenant_id) or (None, None) if not available
    \"\"\"
    # Set up logging to capture detailed information
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("association_debug.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    site_id = None
    tenant_id = None
    
    # Handle site association
    if site_name:
        logging.info(f"Looking up site: {site_name}")
        try:
            sites = list(netbox.dcim.get_sites(name=site_name))
            if sites:
                site = sites[0]
                # Extract ID based on available format (could be property or dict key)
                site_id = site.id if hasattr(site, 'id') else site.get('id')
                logging.info(f"Found site '{site_name}' with ID: {site_id}")
            else:
                # Try to create the site if it doesn't exist
                logging.info(f"Site '{site_name}' not found, creating it...")
                try:
                    new_site = netbox.dcim.create_site(site_name, slugify(site_name))
                    site_id = new_site.id if hasattr(new_site, 'id') else new_site.get('id')
                    logging.info(f"Created site '{site_name}' with ID: {site_id}")
                except Exception as e:
                    logging.error(f"Failed to create site '{site_name}': {str(e)}")
        except Exception as e:
            logging.error(f"Error looking up site '{site_name}': {str(e)}")
    
    # Handle tenant association
    if tenant_name:
        logging.info(f"Looking up tenant: {tenant_name}")
        try:
            tenants = list(netbox.tenancy.get_tenants(name=tenant_name))
            if tenants:
                tenant = tenants[0]
                # Extract ID based on available format (could be property or dict key)
                tenant_id = tenant.id if hasattr(tenant, 'id') else tenant.get('id')
                logging.info(f"Found tenant '{tenant_name}' with ID: {tenant_id}")
            else:
                # Try to create the tenant if it doesn't exist
                logging.info(f"Tenant '{tenant_name}' not found, creating it...")
                try:
                    new_tenant = netbox.tenancy.create_tenant(tenant_name, slugify(tenant_name))
                    tenant_id = new_tenant.id if hasattr(new_tenant, 'id') else new_tenant.get('id')
                    logging.info(f"Created tenant '{tenant_name}' with ID: {tenant_id}")
                except Exception as e:
                    logging.error(f"Failed to create tenant '{tenant_name}': {str(e)}")
        except Exception as e:
            logging.error(f"Error looking up tenant '{tenant_name}': {str(e)}")
    
    # Save to environment variables for consistent access
    if site_id:
        os.environ['NETBOX_SITE_ID'] = str(site_id)
    if tenant_id:
        os.environ['NETBOX_TENANT_ID'] = str(tenant_id)
    
    return site_id, tenant_id

def get_site_tenant_params():
    \"\"\"
    Get site and tenant parameters for API calls
    
    Returns:
        dict: Parameters for site and tenant to be passed to API calls
    \"\"\"
    params = {}
    
    # Get site ID from environment or global variable
    site_id = os.environ.get('NETBOX_SITE_ID')
    if site_id:
        params['site'] = site_id
    
    # Get tenant ID from environment or global variable
    tenant_id = os.environ.get('NETBOX_TENANT_ID')
    if tenant_id:
        params['tenant'] = tenant_id
    
    return params
""")

def verify_site_exists(netbox, site_name):
    """Verify that the specified site exists in NetBox and create a matching tag"""
    global TARGET_SITE_ID  # Global declaration must come first

    if not site_name:
        return True
    
    sites = list(netbox.dcim.get_sites(name=site_name))
    if sites:
        print(f"Target site '{site_name}' found - restricting migration to this site")
        
        # Create a tag with the same name as the site
        from migration.utils import create_global_tags
        create_global_tags(netbox, [site_name])
        print(f"Created tag '{site_name}' to match site name")
        
        # Store the site ID in the global config
        TARGET_SITE_ID = sites[0].id if hasattr(sites[0], 'id') else sites[0]['id']
        print(f"Using site ID: {TARGET_SITE_ID}")
        
        return True
    else:
        # Create the site if it doesn't exist
        try:
            from slugify import slugify
            print(f"Target site '{site_name}' not found in NetBox, creating it...")
            new_site = netbox.dcim.create_site(site_name, slugify(site_name))
            
            # Store the site ID in the global config
            TARGET_SITE_ID = new_site.id if hasattr(new_site, 'id') else new_site['id']
            print(f"Created site '{site_name}' with ID: {TARGET_SITE_ID}")
            
            # Create a tag with the same name as the site
            from migration.utils import create_global_tags
            create_global_tags(netbox, [site_name])
            print(f"Created tag '{site_name}' to match site name")
            
            return True
        except Exception as e:
            print(f"ERROR: Failed to create site '{site_name}': {e}")
            return False

def verify_tenant_exists(netbox, tenant_name):
    """Verify that the specified tenant exists in NetBox and create a matching tag"""
    global TARGET_TENANT_ID  # Global declaration must come first

    if not tenant_name:
        return True
    
    tenants = list(netbox.tenancy.get_tenants(name=tenant_name))
    if tenants:
        print(f"Target tenant '{tenant_name}' found - restricting migration to this tenant")
        
        # Create a tag with the same name as the tenant
        from migration.utils import create_global_tags
        create_global_tags(netbox, [tenant_name])
        print(f"Created tag '{tenant_name}' to match tenant name")
        
        # Store the tenant ID in the global config
        TARGET_TENANT_ID = tenants[0].id if hasattr(tenants[0], 'id') else tenants[0]['id']
        print(f"Using tenant ID: {TARGET_TENANT_ID}")
        
        return True
    else:
        # Create the tenant if it doesn't exist
        try:
            from slugify import slugify
            print(f"Target tenant '{tenant_name}' not found in NetBox, creating it...")
            new_tenant = netbox.tenancy.create_tenant(tenant_name, slugify(tenant_name))
            
            # Store the tenant ID in the global config
            TARGET_TENANT_ID = new_tenant.id if hasattr(new_tenant, 'id') else new_tenant['id']
            print(f"Created tenant '{tenant_name}' with ID: {TARGET_TENANT_ID}")
            
            # Create a tag with the same name as the tenant
            from migration.utils import create_global_tags
            create_global_tags(netbox, [tenant_name])
            print(f"Created tag '{tenant_name}' to match tenant name")
            
            return True
        except Exception as e:
            print(f"ERROR: Failed to create tenant '{tenant_name}': {e}")
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
    
    # Create available subnets
    if CREATE_AVAILABLE_SUBNETS:
        # First use the API-based approach to get accurate available prefixes
        from migration.extended.available_subnets import create_available_prefixes
        create_available_prefixes(netbox)
        
        # Then use the algorithmic approach as a fallback
        from migration.extended.available_subnets import create_available_subnets
        create_available_subnets(netbox)
    
    # Generate IP ranges based on imported IP data
    if CREATE_IP_RANGES:
        # First create IP ranges from API-detected available prefixes
        from migration.extended.ip_ranges import create_ip_ranges_from_available_prefixes
        create_ip_ranges_from_available_prefixes(netbox)
        
        # Then create ranges from algorithmic detection
        from migration.extended.ip_ranges import create_ip_ranges
        create_ip_ranges(netbox)
    
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
    
    # Set target tenant if specified
    if args.tenant:
        global TARGET_TENANT
        TARGET_TENANT = args.tenant
        logging.info(f"Filtering migration for tenant: {TARGET_TENANT}")
        
    # Create required helper modules
    create_helper_modules()
    
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
    
    # Ensure site and tenant associations are set up
    from migration.site_tenant import ensure_site_tenant_associations
    ensure_site_tenant_associations(netbox, TARGET_SITE, TARGET_TENANT)
    
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

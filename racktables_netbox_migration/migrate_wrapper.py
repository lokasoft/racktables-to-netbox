#!/usr/bin/env python3
"""
Wrapper script to run the migration from Racktables to NetBox

This script imports the custom_netbox module to extend the NetBox library with
the necessary methods for migration, then runs the migration script with these
extensions applied.
"""

import os
import sys
import importlib.util
import argparse
import logging

# Add the current directory to the Python path to enable direct import of
# racktables_netbox_migration as a package
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the custom NetBox wrapper class
from custom_netbox import NetBox

# Keep the original environment
original_env = dict(os.environ)

def parse_arguments():
    """Parse command line arguments for the migration script"""
    parser = argparse.ArgumentParser(description='Migrate data from Racktables to NetBox')
    parser.add_argument('--site', type=str, help='Target site name to restrict migration to')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    return parser.parse_args()

def run_migration(args):
    """Run the migration script with the updated NetBox wrapper class"""
    print("Starting Racktables to NetBox migration with enhanced NetBox library...")
    
    # Configure logging
    logging.basicConfig(level=logging.INFO, 
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.FileHandler('migration.log'),
                            logging.StreamHandler(sys.stdout)
                        ])
    
    # Import the migrate module
    try:
        migrate_spec = importlib.util.spec_from_file_location("migrate", os.path.join(os.path.dirname(__file__), "migrate.py"))
        migrate = importlib.util.module_from_spec(migrate_spec)
        migrate_spec.loader.exec_module(migrate)
    except Exception as e:
        logging.error(f"Failed to import migrate module: {e}")
        return False
    
    # Import the extended_migrate module
    try:
        extended_spec = importlib.util.spec_from_file_location("extended_migrate", os.path.join(os.path.dirname(__file__), "extended_migrate.py"))
        extended_migrate = importlib.util.module_from_spec(extended_spec)
        extended_spec.loader.exec_module(extended_migrate)
    except Exception as e:
        logging.error(f"Failed to import extended_migrate module: {e}")
        return False
    
    # Verify site exists before proceeding
    if args.site:
        try:
            # Import the configuration
            import racktables_netbox_migration.config as config
            
            # Set the target site
            config.TARGET_SITE = args.site
            
            # Create NetBox client
            netbox = NetBox(
                host=config.NB_HOST, 
                port=config.NB_PORT, 
                use_ssl=config.NB_USE_SSL, 
                auth_token=config.NB_TOKEN
            )
            
            # Verify site exists
            sites = netbox.dcim.get_sites(name=args.site)
            if not sites:
                logging.error(f"Target site '{args.site}' not found in NetBox")
                return False
            
            logging.info(f"Migrating data for site: {args.site}")
        except Exception as e:
            logging.error(f"Error verifying site {args.site}: {e}")
            return False
    
    try:
        logging.info("Starting migration...")
        
        # Execute the migration modules
        sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
        
        # Run main migration
        migrate.main()
        
        # Run extended migration
        extended_migrate.migrate_additional()
        
        logging.info("Migration completed successfully!")
        return True
        
    except Exception as e:
        logging.error(f"Error during migration: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    # First run set_custom_fields.py to ensure all custom fields are created
    print("Setting up custom fields...")
    try:
        custom_fields_spec = importlib.util.spec_from_file_location("set_custom_fields", os.path.join(os.path.dirname(__file__), "set_custom_fields.py"))
        custom_fields = importlib.util.module_from_spec(custom_fields_spec)
        custom_fields_spec.loader.exec_module(custom_fields)
    except Exception as e:
        print(f"Warning: Error setting up custom fields: {e}")
        print("Continuing with migration...")
    
    # Run the migration
    success = run_migration(args)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

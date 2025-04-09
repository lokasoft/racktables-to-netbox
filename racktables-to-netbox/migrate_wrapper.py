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
    
    # Import the migrate module
    migrate_spec = importlib.util.spec_from_file_location("migrate", "migrate.py")
    migrate = importlib.util.module_from_spec(migrate_spec)
    
    # Import the extended_migrate module
    extended_spec = importlib.util.spec_from_file_location("extended_migrate", "extended_migrate.py")
    extended_migrate = importlib.util.module_from_spec(extended_spec)
    
    try:
        # Set the target site if specified
        if args.site:
            print(f"Target site specified: {args.site}")
            # Import the config module to set TARGET_SITE
            import racktables_netbox_migration.config as config
            config.TARGET_SITE = args.site
        
        # Execute the migration modules
        migrate_spec.loader.exec_module(migrate)
        extended_spec.loader.exec_module(extended_migrate)
        
        print("Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()
    
    # First run set_custom_fields.py to ensure all custom fields are created
    print("Setting up custom fields...")
    try:
        custom_fields_spec = importlib.util.spec_from_file_location("set_custom_fields", "set_custom_fields.py")
        custom_fields = importlib.util.module_from_spec(custom_fields_spec)
        custom_fields_spec.loader.exec_module(custom_fields)
    except Exception as e:
        print(f"Warning: Error setting up custom fields: {e}")
        print("Continuing with migration...")
    
    # Run the migration
    success = run_migration(args)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

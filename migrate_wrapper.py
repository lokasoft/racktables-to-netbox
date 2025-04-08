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
from custom_netbox import ExtendedNetBox

# Keep the original environment
original_env = dict(os.environ)

def run_migration():
    """Run the migration script with the extended NetBox class"""
    print("Starting Racktables to NetBox migration with enhanced NetBox library...")
    
    # Import the migrate module
    spec = importlib.util.spec_from_file_location("migrate", "migrate.py")
    migrate = importlib.util.module_from_spec(spec)
    
    # Save original NetBox import
    import netbox
    original_netbox = netbox.NetBox
    
    try:
        # Replace the NetBox class with our extended version
        netbox.NetBox = ExtendedNetBox
        
        # Execute the migrate module
        spec.loader.exec_module(migrate)
        
        print("Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        return False
        
    finally:
        # Restore the original NetBox class
        netbox.NetBox = original_netbox
        
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)

if __name__ == "__main__":
    # Run the migration
    success = run_migration()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

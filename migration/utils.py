"""
Utility functions for the Racktables to NetBox migration tool
"""
import os
import pickle
import time
from contextlib import contextmanager
import pymysql
from slugify import slugify

from migration.config import DB_CONFIG, STORE_DATA, TARGET_TENANT_ID

def error_log(string):
    """
    Log an error message to the errors file
    
    Args:
        string: Error message to log
    """
    with open("errors", "a") as error_file:
        error_file.write(string + "\n")

def pickleLoad(filename, default):
    """
    Load data from a pickle file with fallback to default value
    
    Args:
        filename: Path to pickle file
        default: Default value to return if file doesn't exist
        
    Returns:
        Unpickled data or default value
    """
    if os.path.exists(filename):
        with open(filename, 'rb') as file:
            data = pickle.load(file)
            return data
    return default

def pickleDump(filename, data):
    """
    Save data to a pickle file if storage is enabled
    
    Args:
        filename: Path to pickle file
        data: Data to pickle
    """
    if STORE_DATA:
        with open(filename, 'wb') as file:
            pickle.dump(data, file)

@contextmanager
def get_db_connection():
    """
    Create a database connection context manager
    
    Yields:
        pymysql.Connection: Database connection
    """
    connection = None
    try:
        connection = pymysql.connect(**DB_CONFIG)
        yield connection
    except pymysql.MySQLError as e:
        print(f"Database connection error: {e}")
        raise
    finally:
        if connection:
            connection.close()

@contextmanager
def get_cursor(connection):
    """
    Create a database cursor context manager
    
    Args:
        connection: Database connection
        
    Yields:
        pymysql.cursors.Cursor: Database cursor
    """
    cursor = None
    try:
        cursor = connection.cursor()
        yield cursor
    finally:
        if cursor:
            cursor.close()

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
    
    sites = list(netbox.dcim.get_sites(name=site_name))
    if sites:
        print(f"Target site '{site_name}' found - restricting migration to this site")
        return True
    else:
        print(f"ERROR: Target site '{site_name}' not found in NetBox")
        return False

def verify_tenant_exists(netbox, tenant_name):
    """
    Verify that the specified tenant exists in NetBox
    
    Args:
        netbox: NetBox client instance
        tenant_name: Name of tenant to verify
        
    Returns:
        bool: True if tenant exists or if tenant_name is None, False otherwise
    """
    global TARGET_TENANT_ID  # Global declaration must come first
    
    if not tenant_name:
        return True  # No tenant filter, proceed with all
    
    tenants = list(netbox.tenancy.get_tenants(name=tenant_name))
    if tenants:
        print(f"Target tenant '{tenant_name}' found - restricting migration to this tenant")
        TARGET_TENANT_ID = tenants[0].id if hasattr(tenants[0], 'id') else tenants[0]['id']
        print(f"Using tenant ID: {TARGET_TENANT_ID}")
        return True
    else:
        try:
            print(f"Target tenant '{tenant_name}' not found in NetBox, creating it...")
            new_tenant = netbox.tenancy.create_tenant(tenant_name, slugify(tenant_name))
            
            TARGET_TENANT_ID = new_tenant.id if hasattr(new_tenant, 'id') else new_tenant['id']
            print(f"Created tenant '{tenant_name}' with ID: {TARGET_TENANT_ID}")
            
            return True
        except Exception as e:
            print(f"ERROR: Failed to create tenant '{tenant_name}': {e}")
            return False

def create_global_tags(netbox, tags):
    """
    Create tags in NetBox if they don't already exist
    
    Args:
        netbox: NetBox client instance
        tags: Set of tag names to create
    """
    # Convert tags from NetBox to a list of names
    tag_objects = list(netbox.extras.get_tags())
    global_tags = set()
    
    for tag in tag_objects:
        if hasattr(tag, 'name'):
            global_tags.add(tag.name)
        elif isinstance(tag, dict) and 'name' in tag:
            global_tags.add(tag['name'])
    
    for tag in tags:
        if tag not in global_tags:
            try:
                netbox.extras.create_tag(tag, slugify(tag))
            except Exception as e:
                print(f"Error creating tag {tag}: {e}")
            global_tags.add(tag)

def ensure_tag_exists(netbox, tag_name):
    """
    Ensure a tag exists in NetBox before using it
    
    Args:
        netbox: NetBox client instance
        tag_name: Name of the tag
        
    Returns:
        bool: True if tag exists or was created, False otherwise
    """
    try:
        # Check if tag exists
        tags = list(netbox.extras.get_tags(name=tag_name))
        if tags:
            return True
            
        # Create the tag if it doesn't exist
        tag_slug = slugify(tag_name)
        netbox.extras.create_tag(
            name=tag_name,
            slug=tag_slug
        )
        print(f"Created tag: {tag_name}")
        return True
    except Exception as e:
        print(f"Failed to create tag {tag_name}: {e}")
        return False

def is_available_prefix(prefix_name, comment):
    """
    Determine if a prefix should be marked as available based on its data
    
    Args:
        prefix_name: Name of the prefix from Racktables
        comment: Comment for the prefix from Racktables
        
    Returns:
        bool: True if prefix should be marked as available, False otherwise
    """
    # If name and comment are both empty or None, mark as available
    if (not prefix_name or prefix_name.strip() == "") and (not comment or comment.strip() == ""):
        return True
    
    # Check for the dragon icon indicators or other available markers
    if prefix_name and ("[Here be dragons" in prefix_name or "[create network here]" in prefix_name):
        return True
        
    return False

def format_prefix_description(prefix_name, tags, comment):
    """
    Format a description for a prefix including name, tags, and comment
    
    Args:
        prefix_name: Name of the prefix
        tags: List of tag objects
        comment: Comment for the prefix
        
    Returns:
        str: Formatted description string
    """
    # Extract tag names consistently whether they're objects or dicts
    tag_names = []
    for tag in tags:
        if hasattr(tag, 'name'):
            tag_names.append(tag.name)
        elif isinstance(tag, dict) and 'name' in tag:
            tag_names.append(tag['name'])
    
    tag_str = ", ".join(tag_names) if tag_names else ""
    description = f"{prefix_name}"
    if tag_str:
        description += f" [{tag_str}]"
    if comment:
        description += f" - {comment}" if description else comment
        
    return description[:200] if description else ""

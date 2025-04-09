"""
Utility functions for the Racktables to NetBox migration tool
"""
import os
import pickle
import time
from contextlib import contextmanager
import pymysql

from racktables_netbox_migration.config import DB_CONFIG, STORE_DATA

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
    
    sites = netbox.dcim.get_sites(name=site_name)
    if sites:
        print(f"Target site '{site_name}' found - restricting migration to this site")
        return True
    else:
        print(f"ERROR: Target site '{site_name}' not found in NetBox")
        return False

def create_global_tags(netbox, tags):
    """
    Create tags in NetBox if they don't already exist
    
    Args:
        netbox: NetBox client instance
        tags: Set of tag names to create
    """
    global_tags = set(tag['name'] for tag in netbox.extras.get_tags())
    
    for tag in tags:
        if tag not in global_tags:
            try:
                from slugify import slugify
                netbox.extras.create_tag(tag, slugify(tag))
            except Exception as e:
                print(f"Error creating tag {tag}: {e}")
            global_tags.add(tag)

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
    tag_names = ", ".join([tag['name'] for tag in tags]) if tags else ""
    description = f"{prefix_name}"
    if tag_names:
        description += f" [{tag_names}]"
    if comment:
        description += f" - {comment}" if description else comment
        
    return description[:200] if description else ""

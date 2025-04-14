"""
Site and rack related functions for the Racktables to NetBox migration
"""
from slugify import slugify

from racktables_netbox_migration.utils import get_db_connection, get_cursor
from racktables_netbox_migration.db import (
    getRowsAtSite, getRacksAtRow, getAtomsAtRack, getRackHeight, getTags
)
from racktables_netbox_migration.config import (
    SITE_NAME_LENGTH_THRESHOLD, TARGET_SITE, TARGET_TENANT, TARGET_TENANT_ID
)

def create_sites_and_racks(netbox):
    """
    Create sites, rows, and racks from Racktables in NetBox
    
    Args:
        netbox: NetBox client instance
    """
    print("Creating sites, rows, and racks")
    
    # Skip if site filtering is enabled - only process the target site
    if TARGET_SITE:
        existing_sites = netbox.dcim.get_sites(name=TARGET_SITE)
        if not existing_sites:
            print(f"Target site '{TARGET_SITE}' not found in NetBox")
            return
        
        print(f"Site filtering enabled - only processing target site: {TARGET_SITE}")
        sites_to_process = [(site['id'], site['name'], '', '', '') for site in existing_sites]
    else:
        # Get all locations from Racktables
        with get_db_connection() as connection:
            with get_cursor(connection) as cursor:
                cursor.execute("SELECT id, name, label, asset_no, comment FROM Object WHERE objtype_id=1562")
                sites_to_process = cursor.fetchall()
    
    for site_data in sites_to_process:
        site_id = site_data["id"] if isinstance(site_data, dict) else site_data[0]
        site_name = site_data["name"] if isinstance(site_data, dict) else site_data[1]
        site_label = site_data["label"] if isinstance(site_data, dict) else site_data[2]
        site_asset_no = site_data["asset_no"] if isinstance(site_data, dict) else site_data[3]
        site_comment = site_data["comment"] if isinstance(site_data, dict) else site_data[4]
        
        # Skip if filtering by site and not the target site
        if TARGET_SITE and site_name != TARGET_SITE:
            continue
        
        # Check if site exists or create it
        existing_site = netbox.dcim.get_sites(name=site_name)
        if not existing_site:
            # Skip if this is likely a location rather than a site
            if len(site_name) > SITE_NAME_LENGTH_THRESHOLD:
                print(f"Skipping probable location (address): {site_name}")
                continue
            
            # Add tenant parameter if TARGET_TENANT_ID is specified
            tenant_param = {}
            if TARGET_TENANT_ID:
                tenant_param = {"tenant": TARGET_TENANT_ID}
            
            print(f"Creating site: {site_name}")
            try:
                netbox.dcim.create_site(site_name, slugify(site_name), **tenant_param)
            except Exception as e:
                print(f"Failed to create site {site_name}: {e}")
                continue
        
        # Process rows in this site
        create_rows_and_racks(netbox, site_id, site_name)

def create_rows_and_racks(netbox, site_id, site_name):
    """
    Create rows and racks for a site
    
    Args:
        netbox: NetBox client instance
        site_id: Racktables site ID
        site_name: Site name
    """
    # Get all rows in this site
    for row_id, row_name, row_label, row_asset_no, row_comment in getRowsAtSite(site_id):
        # Process racks in this row
        for rack_id, rack_name, rack_label, rack_asset_no, rack_comment in getRacksAtRow(row_id):
            # Get rack height and tags
            rack_tags = getTags("rack", rack_id)
            rack_height = getRackHeight(rack_id)
            
            # Format the rack name to include site and row
            if not rack_name.startswith(row_name.rstrip(".") + "."):
                rack_name = site_name + "." + row_name + "." + rack_name 
            else:
                rack_name = site_name + "." + rack_name
            
            # Add tenant parameter if TARGET_TENANT_ID is specified
            tenant_param = {}
            if TARGET_TENANT_ID:
                tenant_param = {"tenant": TARGET_TENANT_ID}
            
            print(f"Creating rack: {rack_name}")
            try:
                # Create the rack
                rack = netbox.dcim.create_rack(
                    name=rack_name,
                    comment=rack_comment[:200] if rack_comment else "",
                    site_name=site_name,
                    u_height=rack_height,
                    tags=rack_tags,
                    **tenant_param  # Add tenant parameter
                )
                
                # Add rack to global tracking
                print(f"Created rack {rack_name} (ID: {rack['id']})")
            except Exception as e:
                print(f"Failed to create rack {rack_name}: {e}")

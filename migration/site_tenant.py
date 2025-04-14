"""
Add site and tenant associations to all NetBox objects
"""
import os
import sys
import logging
from slugify import slugify

def ensure_site_tenant_associations(netbox, site_name, tenant_name):
    """
    Ensures that site and tenant IDs are properly retrieved and set globally
    
    Args:
        netbox: NetBox client instance
        site_name: Site name to use
        tenant_name: Tenant name to use
        
    Returns:
        tuple: (site_id, tenant_id) or (None, None) if not available
    """
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
    """
    Get site and tenant parameters for API calls
    
    Returns:
        dict: Parameters for site and tenant to be passed to API calls
    """
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

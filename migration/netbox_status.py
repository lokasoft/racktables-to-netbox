"""
Helper module to determine valid NetBox statuses across versions
Can be imported by other modules to ensure consistent status handling
"""
import requests
import logging
from migration.config import NB_HOST, NB_PORT, NB_TOKEN, NB_USE_SSL

# Cache for valid status choices
_valid_status_choices = {
    'prefix': None,
    'ip_address': None
}

def get_valid_status_choices(netbox, object_type):
    """
    Get valid status choices for a specific object type in NetBox
    
    Args:
        netbox: NetBox client instance
        object_type: Type of object to get status choices for (e.g., 'prefix')
        
    Returns:
        list: List of valid status choices
    """
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
    headers = {"Authorization": f"Token {NB_TOKEN}"}
    
    # DIRECT APPROACH: Get real objects and read their status structure
    try:
        # First try to get a site as reference - sites almost always exist
        site_endpoint = f"{protocol}://{NB_HOST}:{NB_PORT}/api/dcim/sites/"
        response = requests.get(site_endpoint, headers=headers, verify=NB_USE_SSL, params={"limit": 1})
        
        if response.status_code == 200:
            data = response.json()
            if "results" in data and len(data["results"]) > 0:
                site = data["results"][0]
                if "status" in site and isinstance(site["status"], dict):
                    # Modern NetBox format with value and label
                    print(f"Found NetBox using dictionary status format")
                    
                    # Check if we can get actual objects of requested type
                    obj_endpoint = f"{protocol}://{NB_HOST}:{NB_PORT}/api/{endpoints[object_type]}/"
                    obj_response = requests.get(obj_endpoint, headers=headers, verify=NB_USE_SSL, params={"limit": 10})
                    
                    if obj_response.status_code == 200:
                        obj_data = obj_response.json()
                        if "results" in obj_data and len(obj_data["results"]) > 0:
                            # Extract all unique status values from objects
                            statuses = []
                            for obj in obj_data["results"]:
                                if "status" in obj and isinstance(obj["status"], dict):
                                    status_value = obj["status"].get("value")
                                    if status_value and status_value not in statuses:
                                        statuses.append(status_value)
                            
                            if statuses:
                                print(f"Found actual status values for {object_type}: {', '.join(statuses)}")
                                _valid_status_choices[object_type] = statuses
                                # Make sure we have common statuses
                                for common_status in ['active', 'reserved', 'deprecated', 'container']:
                                    if common_status not in statuses:
                                        statuses.append(common_status)
                                return statuses
                    
                    # Fall back to using site status value as reference
                    site_status = site["status"]["value"]
                    print(f"Using site status '{site_status}' as reference")
                    statuses = ['active', 'reserved', 'deprecated', 'container']
                    if site_status not in statuses:
                        statuses.append(site_status)
                    _valid_status_choices[object_type] = statuses
                    return statuses
    except Exception as e:
        logging.error(f"Error in direct status detection: {str(e)}")
    
    # Final fallback with standard values
    fallback = ['active', 'container', 'reserved', 'deprecated']
    print(f"Using fallback status choices: {', '.join(fallback)}")
    _valid_status_choices[object_type] = fallback
    return fallback

def determine_prefix_status(prefix_name, comment, valid_statuses=None):
    """
    Determine the appropriate NetBox status for a prefix based on its name and comments
    
    Args:
        prefix_name: Name of the prefix from Racktables
        comment: Comment for the prefix from Racktables
        valid_statuses: List of valid status choices in NetBox
        
    Returns:
        str: Most appropriate status for the prefix
    """
    # Use default statuses if none provided
    if valid_statuses is None:
        valid_statuses = ['active', 'container', 'reserved', 'deprecated']
    
    # Default to 'active' if available, otherwise first valid status
    default_status = 'active' if 'active' in valid_statuses else valid_statuses[0]
    
    # Default to 'reserved' if name/comment are empty
    if (not prefix_name or prefix_name.strip() == "") and (not comment or comment.strip() == ""):
        # For empty prefixes, use reserved (if available) or first valid status
        return 'reserved' if 'reserved' in valid_statuses else default_status
    
    # Determine status based on content patterns
    lower_name = prefix_name.lower() if prefix_name else ""
    lower_comment = comment.lower() if comment else ""
    
    # Check for hints that the prefix is specifically reserved
    if any(term in lower_name or term in lower_comment for term in 
           ['reserved', 'hold', 'future', 'planned']):
        return 'reserved' if 'reserved' in valid_statuses else default_status
    
    # Check for hints that the prefix is deprecated
    if any(term in lower_name or term in lower_comment for term in 
           ['deprecated', 'obsolete', 'old', 'inactive', 'decommissioned']):
        return 'deprecated' if 'deprecated' in valid_statuses else default_status
    
    # Check for specific hints that the prefix should be a container
    if any(term in lower_name or term in lower_comment for term in 
           ['container', 'parent', 'supernet', 'aggregate']):
        return 'container' if 'container' in valid_statuses else default_status
    
    # Check for hints that this is available/unused space
    if any(term in lower_name or term in lower_comment for term in 
           ['available', 'unused', 'free', '[here be dragons', '[create network here]', 'unallocated']):
        return 'container' if 'container' in valid_statuses else default_status
    
    # Check for hints that this is actively used
    if any(term in lower_name or term in lower_comment for term in 
           ['in use', 'used', 'active', 'production', 'allocated']):
        return 'active' if 'active' in valid_statuses else default_status
    
    # When we can't clearly determine from the content, default to 'active' for anything with a name/comment
    # This assumes that if someone took the time to name it, it's likely in use
    return default_status

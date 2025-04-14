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
    
    # Default to 'reserved' if name/comment are empty - CHANGED FROM 'active'/'container'
    if (not prefix_name or prefix_name.strip() == "") and (not comment or comment.strip() == ""):
        # For empty prefixes, use reserved (if available) or first valid status
        return 'reserved' if 'reserved' in valid_statuses else valid_statuses[0]
    
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

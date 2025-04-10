"""
Functions for creating available subnet prefixes with improved detection
"""
import ipaddress
import requests
from migration.utils import error_log, is_available_prefix, ensure_tag_exists
from migration.config import NB_HOST, NB_PORT, NB_TOKEN, NB_USE_SSL

def create_available_prefixes(netbox):
    """
    Create available subnet prefixes using NetBox API
    
    Args:
        netbox: NetBox client instance
    """
    print("\nCreating available subnet prefixes using NetBox API...")
    
    # Create the Available tag if it doesn't exist
    tag_exists = ensure_tag_exists(netbox, "Available")
    
    # Configure API access
    protocol = "https" if NB_USE_SSL else "http"
    api_url = f"{protocol}://{NB_HOST}:{NB_PORT}/api"
    headers = {
        "Authorization": f"Token {NB_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Get all prefixes that could contain available prefixes
    existing_prefixes = list(netbox.ipam.get_ip_prefixes())
    
    # Try to analyze a sample prefix to understand structure
    if existing_prefixes and len(existing_prefixes) > 0:
        sample = existing_prefixes[0]
        print(f"DEBUG: Sample prefix type: {type(sample)}")
        if hasattr(sample, '__dict__'):
            print(f"DEBUG: Sample prefix attrs: {dir(sample)[:5]}...")
    
    parent_prefixes = []
    
    # Get all possible parent prefixes - use less strict filtering
    for p in existing_prefixes:
        try:
            # Extract prefix string regardless of response format
            prefix_str = None
            if hasattr(p, 'prefix'):
                prefix_str = p.prefix
            elif isinstance(p, dict) and 'prefix' in p:
                prefix_str = p['prefix']
            else:
                # Try accessing as dictionary even if it's an object
                try:
                    prefix_str = p['prefix']
                except:
                    # Last resort - try string conversion
                    prefix_str = str(p)
                    if '/' not in prefix_str:
                        continue
            
            if not prefix_str:
                continue
                
            # Don't filter as strictly - include all potential parents
            parent_prefixes.append(p)
            
        except Exception as e:
            error_log(f"Error processing potential parent prefix: {str(e)}")
    
    print(f"Found {len(parent_prefixes)} potential parent prefixes")
    available_count = 0
    
    # Process each parent to find available subnets
    for parent in parent_prefixes:
        # Extract parent ID and prefix string
        parent_id = None
        if hasattr(parent, 'id'):
            parent_id = parent.id
        elif isinstance(parent, dict) and 'id' in parent:
            parent_id = parent['id']
        
        if not parent_id:
            continue
            
        # Extract prefix for logging
        parent_prefix = None
        if hasattr(parent, 'prefix'):
            parent_prefix = parent.prefix
        elif isinstance(parent, dict) and 'prefix' in parent:
            parent_prefix = parent['prefix']
        
        # Get available prefixes directly from API
        available_url = f"{api_url}/ipam/prefixes/{parent_id}/available-prefixes/"
        
        try:
            response = requests.get(
                available_url, 
                headers=headers,
                verify=NB_USE_SSL
            )
            
            if response.status_code != 200:
                error_log(f"Error getting available prefixes for {parent_prefix}: {response.text}")
                continue
                
            available_prefixes = response.json()
            if not available_prefixes:
                continue
            
            print(f"Found {len(available_prefixes)} available prefixes in {parent_prefix}")
            
            # Process found available prefixes - minimal filtering
            for available in available_prefixes:
                prefix_str = available['prefix']
                
                # Create the available prefix - don't filter by prefix length
                try:
                    # Only add tags if the tag exists
                    tags_param = [{'name': 'Available'}] if tag_exists else []
                    
                    netbox.ipam.create_ip_prefix(
                        prefix=prefix_str,
                        description="Available prefix",
                        tags=tags_param
                    )
                    available_count += 1
                    print(f"Created available prefix: {prefix_str}")
                except Exception as e:
                    error_log(f"Error creating available prefix {prefix_str}: {str(e)}")
                    print(f"DEBUG ERROR: {str(e)}")
                        
        except Exception as e:
            error_log(f"Error processing parent prefix {parent_prefix}: {str(e)}")
            print(f"DEBUG ERROR: {str(e)}")
                
    print(f"Created {available_count} available subnet prefixes using API")

def create_available_subnets(netbox):
    """
    Identify and create available subnets in gaps between allocated prefixes
    
    Args:
        netbox: NetBox client instance
    """
    print("\nAnalyzing IP space for available subnets...")
    
    # Create the Available tag if it doesn't exist
    tag_exists = ensure_tag_exists(netbox, "Available")
    
    # Get all existing prefixes
    existing_prefixes = list(netbox.ipam.get_ip_prefixes())
    
    # Group prefixes by parent networks
    network_groups = {}
    for prefix in existing_prefixes:
        try:
            # Extract prefix string
            prefix_str = None
            if hasattr(prefix, 'prefix'):
                prefix_str = prefix.prefix
            elif isinstance(prefix, dict) and 'prefix' in prefix:
                prefix_str = prefix['prefix']
            else:
                continue
                
            network = ipaddress.ip_network(prefix_str)
            
            # Less strict filtering
            if network.prefixlen >= 31 and isinstance(network, ipaddress.IPv4Network):
                continue
            if network.prefixlen >= 127 and isinstance(network, ipaddress.IPv6Network):
                continue
            
            # Find the smallest containing prefix
            parent_prefix = None
            for potential_parent in existing_prefixes:
                # Extract parent prefix string
                parent_str = None
                if hasattr(potential_parent, 'prefix'):
                    parent_str = potential_parent.prefix
                elif isinstance(potential_parent, dict) and 'prefix' in potential_parent:
                    parent_str = potential_parent['prefix']
                else:
                    continue
                    
                if prefix_str == parent_str:
                    continue
                    
                try:
                    parent_network = ipaddress.ip_network(parent_str)
                    
                    # Skip if potential parent has same/smaller mask
                    if parent_network.prefixlen >= network.prefixlen:
                        continue
                        
                    if network.subnet_of(parent_network):
                        if not parent_prefix or ipaddress.ip_network(parent_prefix).prefixlen > parent_network.prefixlen:
                            parent_prefix = parent_str
                except Exception:
                    continue
            
            # Group by parent prefix
            if parent_prefix:
                if parent_prefix not in network_groups:
                    network_groups[parent_prefix] = []
                network_groups[parent_prefix].append(prefix)
        except Exception as e:
            continue
    
    # Track created available subnets
    available_count = 0
    
    # Process each network group to find gaps
    for parent_prefix, child_prefixes in network_groups.items():
        try:
            parent = ipaddress.ip_network(parent_prefix)
            
            # Sort child prefixes by network address
            def get_network_addr(p):
                p_str = None
                if hasattr(p, 'prefix'):
                    p_str = p.prefix
                elif isinstance(p, dict) and 'prefix' in p:
                    p_str = p['prefix']
                else:
                    return 0
                try:
                    return int(ipaddress.ip_network(p_str).network_address)
                except:
                    return 0
            
            child_prefixes.sort(key=get_network_addr)
            
            # Track previous network end
            prev_end = int(parent.network_address)
            
            # Find gaps between consecutive prefixes
            for child in child_prefixes:
                # Extract child prefix
                child_str = None
                if hasattr(child, 'prefix'):
                    child_str = child.prefix
                elif isinstance(child, dict) and 'prefix' in child:
                    child_str = child['prefix']
                else:
                    continue
                    
                child_net = ipaddress.ip_network(child_str)
                start = int(child_net.network_address)
                
                # If there's a gap between previous end and current start
                if start > prev_end:
                    # Create available subnets in the gap - less filtering
                    try:
                        gap_network = ipaddress.ip_network((prev_end, parent.prefixlen))
                        
                        # Determine suitable prefix sizes based on network type
                        prefix_sizes = [24, 25, 26, 27, 28, 29] if isinstance(parent, ipaddress.IPv4Network) else [64, 80, 96, 112]
                        
                        for new_prefix_len in prefix_sizes:
                            if new_prefix_len > parent.prefixlen:
                                try:
                                    subnets = list(gap_network.subnets(new_prefix=new_prefix_len))
                                    
                                    # Create first 2 available subnets of each size
                                    for subnet in subnets[:2]:
                                        if int(subnet.network_address) < start and int(subnet.broadcast_address) < start:
                                            try:
                                                # Only add tags if the tag exists
                                                tags_param = [{'name': 'Available'}] if tag_exists else []
                                                
                                                netbox.ipam.create_ip_prefix(
                                                    prefix=str(subnet),
                                                    description="Available subnet",
                                                    tags=tags_param
                                                )
                                                available_count += 1
                                                print(f"Created available subnet: {subnet}")
                                            except Exception as e:
                                                error_log(f"Error creating available subnet {subnet}: {str(e)}")
                                                print(f"DEBUG ERROR: {str(e)}")
                                except Exception:
                                    continue
                    except Exception as e:
                        error_log(f"Error processing subnets for gap: {str(e)}")
                        print(f"DEBUG ERROR: {str(e)}")
                
                # Update previous end for next iteration
                prev_end = int(child_net.broadcast_address) + 1
            
            # Check for gap between last child and end of parent
            if prev_end < int(parent.broadcast_address):
                try:
                    gap_network = ipaddress.ip_network((prev_end, parent.prefixlen))
                    
                    # Determine suitable prefix sizes based on network type
                    prefix_sizes = [24, 25, 26, 27, 28, 29] if isinstance(parent, ipaddress.IPv4Network) else [64, 80, 96, 112]
                    
                    for new_prefix_len in prefix_sizes:
                        if new_prefix_len > parent.prefixlen:
                            try:
                                subnets = list(gap_network.subnets(new_prefix=new_prefix_len))
                                
                                # Create first 2 available subnets of each size
                                for subnet in subnets[:2]:
                                    try:
                                        # Only add tags if the tag exists
                                        tags_param = [{'name': 'Available'}] if tag_exists else []
                                        
                                        netbox.ipam.create_ip_prefix(
                                            prefix=str(subnet),
                                            description="Available end gap subnet",
                                            tags=tags_param
                                        )
                                        available_count += 1
                                        print(f"Created end gap subnet: {subnet}")
                                    except Exception as e:
                                        error_log(f"Error creating end gap subnet {subnet}: {str(e)}")
                                        print(f"DEBUG ERROR: {str(e)}")
                            except Exception:
                                continue
                except Exception as e:
                    error_log(f"Error creating end gap network: {str(e)}")
                    print(f"DEBUG ERROR: {str(e)}")
        
        except Exception as e:
            error_log(f"Error processing parent network {parent_prefix}: {str(e)}")
            print(f"DEBUG ERROR: {str(e)}")
    
    print(f"Created {available_count} available subnet prefixes")

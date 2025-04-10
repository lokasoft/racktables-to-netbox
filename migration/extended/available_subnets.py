"""
Functions for creating available subnet prefixes with improved detection
"""
import ipaddress
import requests
from migration.utils import error_log, is_available_prefix
from migration.config import NB_HOST, NB_PORT, NB_TOKEN, NB_USE_SSL

def create_available_prefixes(netbox):
    """
    Create available subnet prefixes using NetBox API
    
    Args:
        netbox: NetBox client instance
    """
    print("\nCreating available subnet prefixes using NetBox API...")
    
    # Configure API access
    protocol = "https" if NB_USE_SSL else "http"
    api_url = f"{protocol}://{NB_HOST}:{NB_PORT}/api"
    headers = {
        "Authorization": f"Token {NB_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Get all parent prefixes that could contain available prefixes
    existing_prefixes = netbox.ipam.get_ip_prefixes()
    parent_prefixes = []
    
    # Filter to find prefixes that could be parents (not too small)
    for p in existing_prefixes:
        try:
            # Check if prefix attribute exists and has a value
            if not hasattr(p, 'prefix') or not p.prefix:
                continue
                
            network = ipaddress.ip_network(p.prefix)
            
            # Consider only IPv4 prefixes up to /24
            if isinstance(network, ipaddress.IPv4Network) and network.prefixlen < 24:
                parent_prefixes.append(p)
        except Exception as e:
            prefix_str = getattr(p, 'prefix', 'unknown')
            error_log(f"Error processing potential parent prefix {prefix_str}: {str(e)}")
    
    print(f"Found {len(parent_prefixes)} potential parent prefixes")
    available_count = 0
    
    # Process parent prefixes in batches to avoid overwhelming the API
    batch_size = 10
    max_prefixes_per_parent = 5
    min_prefix_size = 16  # Only create prefixes of this size or larger
    
    for i in range(0, len(parent_prefixes), batch_size):
        batch = parent_prefixes[i:i+batch_size]
        
        for parent in batch:
            parent_id = parent.id
            parent_prefix = parent.prefix
            
            # Skip if the parent is already marked as available
            status_value = getattr(getattr(parent, 'status', None), 'value', None)
            if status_value == 'available':
                continue
                
            # Get available prefixes from API
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
                
                # Filter prefixes - select larger prefixes first
                sorted_prefixes = sorted(
                    available_prefixes,
                    key=lambda p: ipaddress.ip_network(p['prefix']).prefixlen
                )
                
                # Only create a limited number of prefixes per parent
                prefix_count = 0
                for available in sorted_prefixes:
                    prefix_str = available['prefix']
                    prefix_obj = ipaddress.ip_network(prefix_str)
                    
                    # Only create larger prefixes
                    if prefix_obj.prefixlen > min_prefix_size:
                        continue
                        
                    try:
                        # Create the available prefix
                        netbox.ipam.create_ip_prefix(
                            prefix=prefix_str,
                            status="available",
                            description=f"Available subnet in {parent_prefix}",
                            tags=[{'name': 'Available'}, {'name': 'Auto-Generated'}, {'name': 'API-Detected'}]
                        )
                        available_count += 1
                        print(f"Created available prefix: {prefix_str}")
                        
                        prefix_count += 1
                        if prefix_count >= max_prefixes_per_parent:
                            break
                            
                    except Exception as e:
                        error_log(f"Error creating available prefix {prefix_str}: {str(e)}")
                        
            except Exception as e:
                error_log(f"Error processing parent prefix {parent_prefix}: {str(e)}")
                
    print(f"Created {available_count} available subnet prefixes using API")

def create_available_subnets(netbox):
    """
    Identify and create available subnets in gaps between allocated prefixes
    
    Args:
        netbox: NetBox client instance
    """
    print("\nAnalyzing IP space for available subnets...")
    
    # Get all existing prefixes including inactive ones
    existing_prefixes = netbox.ipam.get_ip_prefixes()
    
    # Group prefixes by parent networks
    network_groups = {}
    for prefix in existing_prefixes:
        try:
            network = ipaddress.ip_network(prefix.prefix)
            
            # Skip very small networks
            if network.prefixlen >= 30 and isinstance(network, ipaddress.IPv4Network):
                continue
            if network.prefixlen >= 126 and isinstance(network, ipaddress.IPv6Network):
                continue
            
            # Find the smallest containing prefix
            parent_prefix = None
            for potential_parent in existing_prefixes:
                parent_network = ipaddress.ip_network(potential_parent.prefix)
                
                # Skip if same prefix or if potential parent is same/smaller
                if str(network) == str(parent_network) or parent_network.prefixlen >= network.prefixlen:
                    continue
                    
                if network.subnet_of(parent_network):
                    if not parent_prefix or ipaddress.ip_network(parent_prefix).prefixlen > parent_network.prefixlen:
                        parent_prefix = potential_parent.prefix
            
            # Group by parent prefix
            if parent_prefix:
                if parent_prefix not in network_groups:
                    network_groups[parent_prefix] = []
                network_groups[parent_prefix].append(prefix)
        except Exception as e:
            error_log(f"Error processing prefix {prefix.prefix}: {str(e)}")
    
    # Track created available subnets
    available_count = 0
    
    # Process each network group
    for parent_prefix, child_prefixes in network_groups.items():
        try:
            parent = ipaddress.ip_network(parent_prefix)
            
            # Sort child prefixes by network address
            child_prefixes.sort(key=lambda x: ipaddress.ip_network(x['prefix']).network_address)
            
            # Track previous network end
            prev_end = int(parent.network_address)
            
            # Find gaps between consecutive prefixes
            for child in child_prefixes:
                child_net = ipaddress.ip_network(child['prefix'])
                start = int(child_net.network_address)
                
                # If there's a gap between previous end and current start
                if start > prev_end:
                    # Create available subnets in the gap
                    try:
                        gap_network = ipaddress.ip_network((prev_end, parent.prefixlen))
                        
                        # Determine suitable prefix sizes based on network type
                        prefix_sizes = [24, 25, 26, 27, 28] if isinstance(parent, ipaddress.IPv4Network) else [64, 80, 96, 112]
                        
                        for new_prefix_len in prefix_sizes:
                            if new_prefix_len > parent.prefixlen and new_prefix_len < child_net.prefixlen:
                                subnets = list(gap_network.subnets(new_prefix=new_prefix_len))
                                
                                # Create first 2 available subnets of each size
                                for subnet in subnets[:2]:
                                    if int(subnet.network_address) < start and int(subnet.broadcast_address) < start:
                                        try:
                                            # Use a very descriptive status and description
                                            netbox.ipam.create_ip_prefix(
                                                prefix=str(subnet),
                                                status="available",
                                                description=f"Available subnet in {parent_prefix} network space",
                                                tags=[{'name': 'Available'}, {'name': 'Auto-Generated'}]
                                            )
                                            available_count += 1
                                            print(f"Created available subnet: {subnet}")
                                        except Exception as e:
                                            error_log(f"Error creating available subnet {subnet}: {str(e)}")
                    except Exception as e:
                        error_log(f"Error processing subnets for gap: {str(e)}")
                
                # Update previous end for next iteration
                prev_end = int(child_net.broadcast_address) + 1
            
            # Check for gap between last child and end of parent
            if prev_end < int(parent.broadcast_address):
                try:
                    gap_network = ipaddress.ip_network((prev_end, parent.prefixlen))
                    
                    # Determine suitable prefix sizes based on network type
                    prefix_sizes = [24, 25, 26, 27, 28] if isinstance(parent, ipaddress.IPv4Network) else [64, 80, 96, 112]
                    
                    for new_prefix_len in prefix_sizes:
                        if new_prefix_len > parent.prefixlen:
                            try:
                                subnets = list(gap_network.subnets(new_prefix=new_prefix_len))
                                
                                # Create first 2 available subnets of each size
                                for subnet in subnets[:2]:
                                    try:
                                        netbox.ipam.create_ip_prefix(
                                            prefix=str(subnet),
                                            status="available",
                                            description=f"Available subnet in end of {parent_prefix} network space",
                                            tags=[{'name': 'Available'}, {'name': 'Auto-Generated'}]
                                        )
                                        available_count += 1
                                        print(f"Created end gap subnet: {subnet}")
                                    except Exception as e:
                                        error_log(f"Error creating end gap subnet {subnet}: {str(e)}")
                            except Exception as e:
                                error_log(f"Error processing end gap subnets: {str(e)}")
                except Exception as e:
                    error_log(f"Error creating end gap network: {str(e)}")
        
        except Exception as e:
            error_log(f"Error processing parent network {parent_prefix}: {str(e)}")
    
    print(f"Created {available_count} available subnet prefixes")

"""
Functions for creating available subnet prefixes with improved detection
"""
import ipaddress
from racktables_netbox_migration.utils import error_log, is_available_prefix

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
            network = ipaddress.ip_network(prefix['prefix'])
            
            # Skip very small networks
            if network.prefixlen >= 30 and isinstance(network, ipaddress.IPv4Network):
                continue
            if network.prefixlen >= 126 and isinstance(network, ipaddress.IPv6Network):
                continue
            
            # Find the smallest containing prefix
            parent_prefix = None
            for potential_parent in existing_prefixes:
                parent_network = ipaddress.ip_network(potential_parent['prefix'])
                
                # Skip if same prefix or if potential parent is same/smaller
                if str(network) == str(parent_network) or parent_network.prefixlen >= network.prefixlen:
                    continue
                    
                if network.subnet_of(parent_network):
                    if not parent_prefix or ipaddress.ip_network(parent_prefix).prefixlen > parent_network.prefixlen:
                        parent_prefix = potential_parent['prefix']
            
            # Group by parent prefix
            if parent_prefix:
                if parent_prefix not in network_groups:
                    network_groups[parent_prefix] = []
                network_groups[parent_prefix].append(prefix)
        except Exception as e:
            error_log(f"Error processing prefix {prefix['prefix']}: {str(e)}")
    
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

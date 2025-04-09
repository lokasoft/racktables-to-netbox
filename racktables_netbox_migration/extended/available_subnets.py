"""
Functions for creating available subnet prefixes
"""
import ipaddress
from racktables_netbox_migration.utils import error_log

def create_available_subnets(netbox):
    """
    Identify and create available subnets in gaps between allocated prefixes
    
    Args:
        netbox: NetBox client instance
    """
    print("\nAnalyzing IP space for available subnets...")
    
    # Get all existing active prefixes
    existing_prefixes = netbox.ipam.get_ip_prefixes(status="active")
    
    # Group prefixes by parent networks
    prefix_hierarchy = {}
    for prefix in existing_prefixes:
        network = ipaddress.ip_network(prefix['prefix'])
        parent_prefix = None
        
        # Skip /32 or /128 addresses
        if network.prefixlen >= 32 and isinstance(network, ipaddress.IPv4Network):
            continue
        if network.prefixlen >= 128 and isinstance(network, ipaddress.IPv6Network):
            continue
        
        # Find the smallest containing prefix
        for potential_parent in existing_prefixes:
            parent_network = ipaddress.ip_network(potential_parent['prefix'])
            
            # Skip if same prefix or if potential parent is same/smaller
            if str(network) == str(parent_network) or parent_network.prefixlen >= network.prefixlen:
                continue
                
            if network.subnet_of(parent_network):
                if not parent_prefix or parent_network.prefixlen > ipaddress.ip_network(parent_prefix).prefixlen:
                    parent_prefix = potential_parent['prefix']
        
        if parent_prefix:
            if parent_prefix not in prefix_hierarchy:
                prefix_hierarchy[parent_prefix] = []
            prefix_hierarchy[parent_prefix].append(prefix)
    
    available_count = 0
    for parent_prefix, child_prefixes in prefix_hierarchy.items():
        parent = ipaddress.ip_network(parent_prefix)
        
        # Sort child prefixes by network address
        child_prefixes.sort(key=lambda x: ipaddress.ip_network(x['prefix']).network_address)
        
        # Find gaps between consecutive prefixes
        prev_end = int(parent.network_address)
        for child in child_prefixes:
            child_net = ipaddress.ip_network(child['prefix'])
            start = int(child_net.network_address)
            
            # If there's a gap between previous end and current start
            if start > prev_end:
                # Find subnets that fit in the gap
                try:
                    gap_network = ipaddress.ip_network((prev_end, parent.prefixlen))
                    
                    # Create available prefixes in common sizes
                    for new_prefix_len in [24, 25, 26, 27, 28] if isinstance(parent, ipaddress.IPv4Network) else [64, 80, 96, 112]:
                        if new_prefix_len > parent.prefixlen and new_prefix_len < child_net.prefixlen:
                            # Get subnets that fit the gap
                            try:
                                subnets = list(gap_network.subnets(new_prefix=new_prefix_len))
                                
                                # Only create first 2 available subnets of each size to avoid clutter
                                for subnet in subnets[:2]:
                                    if int(subnet.network_address) < start and int(subnet.broadcast_address) < start:
                                        try:
                                            netbox.ipam.create_ip_prefix(
                                                prefix=str(subnet),
                                                status="available",
                                                description=f"Available subnet in {parent_prefix}",
                                                tags=[{'name': 'Available'}]
                                            )
                                            available_count += 1
                                            print(f"Created available subnet: {subnet}")
                                        except Exception as e:
                                            error_log(f"Error creating available subnet {subnet}: {str(e)}")
                            except Exception as e:
                                error_log(f"Error processing subnets for {gap_network}: {str(e)}")
                except Exception as e:
                    error_log(f"Error creating gap network: {str(e)}")
            
            # Update previous end for next iteration
            prev_end = int(child_net.broadcast_address) + 1
        
        # Check for gap between last child and end of parent
        if prev_end < int(parent.broadcast_address):
            try:
                gap_network = ipaddress.ip_network((prev_end, parent.prefixlen))
                
                # Create available prefixes in common sizes
                for new_prefix_len in [24, 25, 26, 27, 28] if isinstance(parent, ipaddress.IPv4Network) else [64, 80, 96, 112]:
                    if new_prefix_len > parent.prefixlen:
                        try:
                            subnets = list(gap_network.subnets(new_prefix=new_prefix_len))
                            
                            # Only create first 2 available subnets of each size to avoid clutter
                            for subnet in subnets[:2]:
                                try:
                                    netbox.ipam.create_ip_prefix(
                                        prefix=str(subnet),
                                        status="available",
                                        description=f"Available subnet in {parent_prefix}",
                                        tags=[{'name': 'Available'}]
                                    )
                                    available_count += 1
                                    print(f"Created available subnet: {subnet}")
                                except Exception as e:
                                    error_log(f"Error creating available subnet {subnet}: {str(e)}")
                        except Exception as e:
                            error_log(f"Error processing subnets for end gap in {gap_network}: {str(e)}")
            except Exception as e:
                error_log(f"Error creating end gap network for {parent_prefix}: {str(e)}")
    
    print(f"Created {available_count} available subnet prefixes")

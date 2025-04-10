"""
IP range generation module to identify and create available IP ranges
"""
import ipaddress
from migration.utils import error_log
from migration.config import TARGET_SITE, IPV4_TAG, IPV6_TAG

def create_ip_ranges_from_available_prefixes(netbox):
    """
    Create IP ranges from available prefixes
    
    Args:
        netbox: NetBox client instance
    """
    print("\nCreating IP ranges from available prefixes...")
    
    # Get all prefixes with Available tag
    all_prefixes = netbox.ipam.get_ip_prefixes()
    available_prefixes = []
    
    # Find prefixes with Available tag
    for prefix in all_prefixes:
        has_available_tag = False
        
        # Handle both dictionary and object responses for tags
        if isinstance(prefix, dict):
            tags = prefix.get('tags', [])
            for tag in tags:
                if isinstance(tag, dict) and tag.get('name') == 'Available':
                    has_available_tag = True
                    break
        else:
            tags = getattr(prefix, 'tags', [])
            for tag in tags:
                tag_name = tag.get('name', '') if isinstance(tag, dict) else getattr(tag, 'name', '')
                if tag_name == 'Available':
                    has_available_tag = True
                    break
                
        if has_available_tag:
            available_prefixes.append(prefix)
    
    print(f"Found {len(available_prefixes)} available prefixes")
    
    # Get existing IP ranges to avoid duplicates
    existing_ranges = netbox.ipam.get_ip_ranges()
    existing_range_cidrs = set()
    
    for ip_range in existing_ranges:
        # Handle both dictionary and object responses
        if isinstance(ip_range, dict):
            start_ip = ip_range.get('start_address', '').split('/')[0] if ip_range.get('start_address') else None
            end_ip = ip_range.get('end_address', '').split('/')[0] if ip_range.get('end_address') else None
        else:
            start_ip = getattr(ip_range, 'start_address', '').split('/')[0] if getattr(ip_range, 'start_address', None) else None
            end_ip = getattr(ip_range, 'end_address', '').split('/')[0] if getattr(ip_range, 'end_address', None) else None
            
        if start_ip and end_ip:
            existing_range_cidrs.add(f"{start_ip}-{end_ip}")
    
    ranges_created = 0
    
    for prefix in available_prefixes:
        # Handle both dictionary and object responses
        prefix_str = prefix['prefix'] if isinstance(prefix, dict) else prefix.prefix
        prefix_obj = ipaddress.ip_network(prefix_str)
        
        # Skip very small prefixes
        if prefix_obj.prefixlen >= 30 and isinstance(prefix_obj, ipaddress.IPv4Network):
            continue
            
        # Create an IP range for the whole prefix
        start_ip = prefix_obj.network_address
        end_ip = prefix_obj.broadcast_address
        range_cidr = f"{start_ip}-{end_ip}"
        
        if range_cidr not in existing_range_cidrs:
            try:
                ip_range = netbox.ipam.create_ip_range(
                    start_address=str(start_ip),
                    end_address=str(end_ip),
                    status="reserved",
                    tags=[{"name": "Available"}]
                )
                existing_range_cidrs.add(range_cidr)
                ranges_created += 1
                print(f"Created IP range for available prefix: {start_ip} - {end_ip}")
            except Exception as e:
                error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
    
    print(f"Created {ranges_created} IP ranges from available prefixes")

def create_ip_ranges(netbox):
    """
    Create IP ranges from IP prefixes and addresses
    
    Args:
        netbox: NetBox client instance
    """
    print("\nGenerating IP ranges...")
    
    # Get all prefixes
    prefixes = netbox.ipam.get_ip_prefixes()
    print(f"Found {len(prefixes)} IP prefixes")
    
    # Get all IP addresses
    ip_addresses = netbox.ipam.get_ip_addresses()
    print(f"Found {len(ip_addresses)} IP addresses")
    
    # Get existing IP ranges to avoid duplicates
    existing_ranges = netbox.ipam.get_ip_ranges()
    existing_range_cidrs = set()
    
    for ip_range in existing_ranges:
        # Handle both dictionary and object responses
        if isinstance(ip_range, dict):
            start_ip = ip_range.get('start_address', '').split('/')[0] if ip_range.get('start_address') else None
            end_ip = ip_range.get('end_address', '').split('/')[0] if ip_range.get('end_address') else None
        else:
            start_ip = getattr(ip_range, 'start_address', '').split('/')[0] if getattr(ip_range, 'start_address', None) else None
            end_ip = getattr(ip_range, 'end_address', '').split('/')[0] if getattr(ip_range, 'end_address', None) else None
            
        if start_ip and end_ip:
            existing_range_cidrs.add(f"{start_ip}-{end_ip}")
    
    print(f"Found {len(existing_ranges)} existing IP ranges")
    
    # Group prefixes by larger containing prefixes
    network_groups = {}
    standalone_prefixes = []
    
    for prefix in prefixes:
        # Handle both dictionary and object responses
        prefix_str = prefix['prefix'] if isinstance(prefix, dict) else prefix.prefix
        prefix_net = ipaddress.ip_network(prefix_str)
        parent_found = False
        
        # Skip very small prefixes for analysis
        if prefix_net.prefixlen >= 30 and isinstance(prefix_net, ipaddress.IPv4Network):
            continue
        if prefix_net.prefixlen >= 126 and isinstance(prefix_net, ipaddress.IPv6Network):
            continue
        
        # Find parent prefix
        for potential_parent in prefixes:
            # Handle both dictionary and object responses
            parent_str = potential_parent['prefix'] if isinstance(potential_parent, dict) else potential_parent.prefix
            
            if prefix_str == parent_str:
                continue
                
            parent_net = ipaddress.ip_network(parent_str)
            
            # Skip if potential parent has same or higher prefix length
            if parent_net.prefixlen >= prefix_net.prefixlen:
                continue
                
            if prefix_net.subnet_of(parent_net):
                if parent_str not in network_groups:
                    network_groups[parent_str] = []
                network_groups[parent_str].append(prefix)
                parent_found = True
                break
        
        if not parent_found:
            standalone_prefixes.append(prefix)
    
    # Process each network group to find gaps
    ranges_created = 0
    
    for parent_prefix, child_prefixes in network_groups.items():
        try:
            parent = ipaddress.ip_network(parent_prefix)
            
            # Sort child prefixes by network address
            child_prefixes.sort(key=lambda x: ipaddress.ip_network(
                x['prefix'] if isinstance(x, dict) else x.prefix
            ).network_address)
            
            # Process gaps between child prefixes
            prev_end = None
            
            for i, child in enumerate(child_prefixes):
                # Handle both dictionary and object responses
                child_str = child['prefix'] if isinstance(child, dict) else child.prefix
                current = ipaddress.ip_network(child_str)
                current_start = int(current.network_address)
                
                # If this is not the first prefix and there's a gap
                if prev_end is not None and current_start > prev_end + 1:
                    # We found a gap between prev_end and current_start
                    start_ip = ipaddress.ip_address(prev_end + 1)
                    end_ip = ipaddress.ip_address(current_start - 1)
                    
                    # Create an IP range for this gap
                    range_cidr = f"{start_ip}-{end_ip}"
                    if range_cidr not in existing_range_cidrs:
                        try:
                            ip_range = netbox.ipam.create_ip_range(
                                start_address=str(start_ip),
                                end_address=str(end_ip),
                                status="reserved",
                                tags=[{"name": "Available"}]
                            )
                            existing_range_cidrs.add(range_cidr)
                            ranges_created += 1
                            print(f"Created IP range: {start_ip} - {end_ip}")
                        except Exception as e:
                            error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                
                # Update prev_end for next iteration
                prev_end = int(current.broadcast_address)
            
            # Check for gap after the last child prefix
            if prev_end is not None and prev_end < int(parent.broadcast_address):
                # Gap between last child and end of parent
                start_ip = ipaddress.ip_address(prev_end + 1)
                end_ip = ipaddress.ip_address(int(parent.broadcast_address))
                
                # Create IP range for this gap
                range_cidr = f"{start_ip}-{end_ip}"
                if range_cidr not in existing_range_cidrs:
                    try:
                        ip_range = netbox.ipam.create_ip_range(
                            start_address=str(start_ip),
                            end_address=str(end_ip),
                            status="reserved",
                            tags=[{"name": "Available"}]
                        )
                        existing_range_cidrs.add(range_cidr)
                        ranges_created += 1
                        print(f"Created IP range: {start_ip} - {end_ip}")
                    except Exception as e:
                        error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                        
        except Exception as e:
            error_log(f"Error processing parent network {parent_prefix}: {str(e)}")
    
    # Process standalone prefixes
    for prefix in standalone_prefixes:
        try:
            # Handle both dictionary and object responses
            prefix_str = prefix['prefix'] if isinstance(prefix, dict) else prefix.prefix
            network = ipaddress.ip_network(prefix_str)
            
            # Check for addresses within this prefix
            contained_addresses = []
            for ip in ip_addresses:
                try:
                    # Handle both dictionary and object responses
                    ip_addr_str = ip['address'] if isinstance(ip, dict) else ip.address
                    addr = ipaddress.ip_address(ip_addr_str.split('/')[0])
                    if addr in network:
                        contained_addresses.append(addr)
                except (ValueError, AttributeError):
                    continue
            
            if not contained_addresses:
                # No addresses in this prefix, create range for whole prefix
                start_ip = network.network_address
                end_ip = network.broadcast_address
                range_cidr = f"{start_ip}-{end_ip}"
                
                if range_cidr not in existing_range_cidrs:
                    try:
                        ip_range = netbox.ipam.create_ip_range(
                            start_address=str(start_ip),
                            end_address=str(end_ip),
                            status="reserved",
                            tags=[{"name": "Available"}]
                        )
                        existing_range_cidrs.add(range_cidr)
                        ranges_created += 1
                        print(f"Created IP range for empty prefix: {start_ip} - {end_ip}")
                    except Exception as e:
                        error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
            else:
                # Has addresses, find gaps
                contained_addresses.sort()
                
                # Check for gap at the beginning
                if int(contained_addresses[0]) > int(network.network_address):
                    start_ip = network.network_address
                    end_ip = ipaddress.ip_address(int(contained_addresses[0]) - 1)
                    range_cidr = f"{start_ip}-{end_ip}"
                    
                    if range_cidr not in existing_range_cidrs:
                        try:
                            ip_range = netbox.ipam.create_ip_range(
                                start_address=str(start_ip),
                                end_address=str(end_ip),
                                status="reserved",
                                tags=[{"name": "Available"}]
                            )
                            existing_range_cidrs.add(range_cidr)
                            ranges_created += 1
                            print(f"Created IP range: {start_ip} - {end_ip}")
                        except Exception as e:
                            error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                
                # Check for gaps between addresses
                for i in range(len(contained_addresses) - 1):
                    curr_addr = int(contained_addresses[i])
                    next_addr = int(contained_addresses[i + 1])
                    
                    if next_addr > curr_addr + 1:
                        start_ip = ipaddress.ip_address(curr_addr + 1)
                        end_ip = ipaddress.ip_address(next_addr - 1)
                        range_cidr = f"{start_ip}-{end_ip}"
                        
                        if range_cidr not in existing_range_cidrs:
                            try:
                                ip_range = netbox.ipam.create_ip_range(
                                    start_address=str(start_ip),
                                    end_address=str(end_ip),
                                    status="reserved",
                                    tags=[{"name": "Available"}]
                                )
                                existing_range_cidrs.add(range_cidr)
                                ranges_created += 1
                                print(f"Created IP range: {start_ip} - {end_ip}")
                            except Exception as e:
                                error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                
                # Check for gap at the end
                if int(contained_addresses[-1]) < int(network.broadcast_address):
                    start_ip = ipaddress.ip_address(int(contained_addresses[-1]) + 1)
                    end_ip = network.broadcast_address
                    range_cidr = f"{start_ip}-{end_ip}"
                    
                    if range_cidr not in existing_range_cidrs:
                        try:
                            ip_range = netbox.ipam.create_ip_range(
                                start_address=str(start_ip),
                                end_address=str(end_ip),
                                status="reserved",
                                tags=[{"name": "Available"}]
                            )
                            existing_range_cidrs.add(range_cidr)
                            ranges_created += 1
                            print(f"Created IP range: {start_ip} - {end_ip}")
                        except Exception as e:
                            error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
        
        except Exception as e:
            prefix_str = prefix['prefix'] if isinstance(prefix, dict) else getattr(prefix, 'prefix', str(prefix))
            error_log(f"Error processing standalone prefix {prefix_str}: {str(e)}")
    
    print(f"IP range generation completed. Created {ranges_created} IP ranges.")

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
    
    # Get all prefixes first
    all_prefixes = netbox.ipam.get_ip_prefixes()
    available_prefixes = []
    
    # A prefix is available only if it has no attributes set except for the prefix itself
    for prefix in all_prefixes:
        # Check if it has tags, description, vrf, role, tenant, or other attributes
        has_description = bool(getattr(prefix, 'description', '').strip())
        has_vrf = getattr(prefix, 'vrf', None) is not None
        has_role = getattr(prefix, 'role', None) is not None
        has_tenant = getattr(prefix, 'tenant', None) is not None
        has_tags = len(getattr(prefix, 'tags', [])) > 0
        has_prefix_name = False
        
        # Check custom fields for Prefix_name
        custom_fields = getattr(prefix, 'custom_fields', {})
        if isinstance(custom_fields, dict) and custom_fields.get('Prefix_Name'):
            has_prefix_name = True
        
        # Only consider it available if it has the Available tag
        has_available_tag = False
        for tag in getattr(prefix, 'tags', []):
            if hasattr(tag, 'name') and tag.name == 'Available':
                has_available_tag = True
                break
        
        # Must have Available tag and no other attributes
        if has_available_tag and not (has_description or has_vrf or has_role or has_tenant or has_prefix_name):
            available_prefixes.append(prefix)
    
    print(f"Found {len(available_prefixes)} available prefixes")
    
    # Get existing IP ranges to avoid duplicates
    existing_ranges = netbox.ipam.get_ip_ranges()
    existing_range_cidrs = set()
    for ip_range in existing_ranges:
        if hasattr(ip_range, 'start_address') and hasattr(ip_range, 'end_address'):
            start_ip = ip_range.start_address.split('/')[0] if ip_range.start_address else None
            end_ip = ip_range.end_address.split('/')[0] if ip_range.end_address else None
            if start_ip and end_ip:
                existing_range_cidrs.add(f"{start_ip}-{end_ip}")
    
    ranges_created = 0
    
    for prefix in available_prefixes:
        prefix_str = prefix.prefix
        prefix_obj = ipaddress.ip_network(prefix_str)
        
        # Skip very small prefixes
        if prefix_obj.prefixlen >= 30 and isinstance(prefix_obj, ipaddress.IPv4Network):
            continue
            
        # Check if this was created from API detection
        api_detected = False
        tags = getattr(prefix, 'tags', [])
        for tag in tags:
            if hasattr(tag, 'name') and tag.name == 'API-Detected':
                api_detected = True
                break
                
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
        if hasattr(ip_range, 'start_address') and hasattr(ip_range, 'end_address'):
            start_ip = ip_range.start_address.split('/')[0] if ip_range.start_address else None
            end_ip = ip_range.end_address.split('/')[0] if ip_range.end_address else None
            if start_ip and end_ip:
                existing_range_cidrs.add(f"{start_ip}-{end_ip}")
    
    print(f"Found {len(existing_ranges)} existing IP ranges")
    
    # Group prefixes by larger containing prefixes
    network_groups = {}
    standalone_prefixes = []
    
    for prefix in prefixes:
        prefix_net = ipaddress.ip_network(prefix.prefix)
        parent_found = False
        
        # Skip very small prefixes for analysis
        if prefix_net.prefixlen >= 30 and isinstance(prefix_net, ipaddress.IPv4Network):
            continue
        if prefix_net.prefixlen >= 126 and isinstance(prefix_net, ipaddress.IPv6Network):
            continue
        
        # Find parent prefix
        for potential_parent in prefixes:
            if prefix.prefix == potential_parent.prefix:
                continue
                
            parent_net = ipaddress.ip_network(potential_parent.prefix)
            
            # Skip if potential parent has same or higher prefix length
            if parent_net.prefixlen >= prefix_net.prefixlen:
                continue
                
            if prefix_net.subnet_of(parent_net):
                if potential_parent.prefix not in network_groups:
                    network_groups[potential_parent.prefix] = []
                network_groups[potential_parent.prefix].append(prefix)
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
            child_prefixes.sort(key=lambda x: ipaddress.ip_network(x.prefix).network_address)
            
            # Process gaps between child prefixes
            prev_end = None
            
            for i, child in enumerate(child_prefixes):
                current = ipaddress.ip_network(child.prefix)
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
            network = ipaddress.ip_network(prefix.prefix)
            
            # Check for addresses within this prefix
            contained_addresses = []
            for ip in ip_addresses:
                try:
                    addr = ipaddress.ip_address(ip.address.split('/')[0])
                    if addr in network:
                        contained_addresses.append(addr)
                except ValueError:
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
            error_log(f"Error processing standalone prefix {prefix.prefix}: {str(e)}")
    
    print(f"IP range generation completed. Created {ranges_created} IP ranges.")

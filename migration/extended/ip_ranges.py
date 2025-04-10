"""
IP range generation module to identify and create available IP ranges
"""
import ipaddress
from migration.utils import error_log, ensure_tag_exists
from migration.config import TARGET_SITE, IPV4_TAG, IPV6_TAG

def create_ip_ranges_from_available_prefixes(netbox):
    """
    Create IP ranges from available prefixes
    
    Args:
        netbox: NetBox client instance
    """
    print("\nCreating IP ranges from available prefixes...")
    
    # Create the Available tag if it doesn't exist
    tag_exists = ensure_tag_exists(netbox, "Available")
    
    # Get all prefixes with Available tag
    all_prefixes = list(netbox.ipam.get_ip_prefixes())
    available_prefixes = []
    
    # Find prefixes with Available tag
    for prefix in all_prefixes:
        # Check for Available tag in different formats
        has_available_tag = False
        
        # Method 1: Check for tags attribute
        if hasattr(prefix, 'tags'):
            tags = prefix.tags
            for tag in tags:
                if hasattr(tag, 'name') and tag.name == 'Available':
                    has_available_tag = True
                    break
                elif isinstance(tag, dict) and tag.get('name') == 'Available':
                    has_available_tag = True
                    break
        
        # Method 2: Check for tags as dict key
        elif isinstance(prefix, dict) and 'tags' in prefix:
            tags = prefix['tags']
            for tag in tags:
                if isinstance(tag, dict) and tag.get('name') == 'Available':
                    has_available_tag = True
                    break
        
        # Method 3: Check directly for tag as a property
        elif hasattr(prefix, 'tag') and prefix.tag == 'Available':
            has_available_tag = True
        
        # Method 4: Direct string search in serialized representation
        elif 'Available' in str(prefix):
            has_available_tag = True
                
        if has_available_tag:
            available_prefixes.append(prefix)
    
    print(f"Found {len(available_prefixes)} available prefixes")
    
    # Debug prefix format if available
    if available_prefixes:
        sample = available_prefixes[0]
        print(f"DEBUG: Available prefix sample type: {type(sample)}")
        if hasattr(sample, '__dict__'):
            print(f"DEBUG: Sample attributes: {dir(sample)[:5]}...")
    
    # Get existing IP ranges to avoid duplicates
    existing_ranges = list(netbox.ipam.get_ip_ranges())
    existing_range_cidrs = set()
    
    for ip_range in existing_ranges:
        # Extract addresses with multiple methods
        start_ip = None
        end_ip = None
        
        # Method 1: Direct attribute access
        if hasattr(ip_range, 'start_address'):
            start_ip = getattr(ip_range, 'start_address', '').split('/')[0]
        if hasattr(ip_range, 'end_address'):
            end_ip = getattr(ip_range, 'end_address', '').split('/')[0]
        
        # Method 2: Dictionary access
        if start_ip is None and isinstance(ip_range, dict) and 'start_address' in ip_range:
            start_ip = ip_range['start_address'].split('/')[0]
        if end_ip is None and isinstance(ip_range, dict) and 'end_address' in ip_range:
            end_ip = ip_range['end_address'].split('/')[0]
        
        # Only add if we have both addresses
        if start_ip and end_ip:
            existing_range_cidrs.add(f"{start_ip}-{end_ip}")
    
    ranges_created = 0
    
    for prefix in available_prefixes:
        # Try multiple methods to extract prefix string
        prefix_str = None
        
        # Method 1: Direct attribute access
        if hasattr(prefix, 'prefix'):
            prefix_str = prefix.prefix
        
        # Method 2: Dictionary access
        elif isinstance(prefix, dict) and 'prefix' in prefix:
            prefix_str = prefix['prefix']
        
        # Method 3: Direct string conversion
        else:
            try:
                prefix_str = str(prefix)
                if '/' not in prefix_str:
                    # Not a valid prefix
                    continue
            except:
                continue
        
        try:
            prefix_obj = ipaddress.ip_network(prefix_str)
            
            # Skip very small prefixes - use less strict filtering
            if prefix_obj.prefixlen >= 31 and isinstance(prefix_obj, ipaddress.IPv4Network):
                continue
                
            # Create an IP range for the whole prefix
            start_ip = prefix_obj.network_address
            end_ip = prefix_obj.broadcast_address
            range_cidr = f"{start_ip}-{end_ip}"
            
            if range_cidr not in existing_range_cidrs:
                try:
                    # Only add tags if the tag exists
                    tags_param = [{"name": "Available"}] if tag_exists else []
                    
                    ip_range = netbox.ipam.create_ip_range(
                        start_address=str(start_ip),
                        end_address=str(end_ip),
                        description="Available IP range",
                        tags=tags_param
                    )
                    existing_range_cidrs.add(range_cidr)
                    ranges_created += 1
                    print(f"Created IP range for available prefix: {start_ip} - {end_ip}")
                except Exception as e:
                    error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                    print(f"DEBUG ERROR: {str(e)}")
        except Exception as e:
            error_log(f"Error processing available prefix: {str(e)}")
            print(f"DEBUG ERROR: {str(e)}")
    
    print(f"Created {ranges_created} IP ranges from available prefixes")

def create_ip_ranges(netbox):
    """
    Create IP ranges from IP prefixes and addresses
    
    Args:
        netbox: NetBox client instance
    """
    print("\nGenerating IP ranges...")
    
    # Create the Available tag if it doesn't exist
    tag_exists = ensure_tag_exists(netbox, "Available")
    
    # Get all prefixes
    prefixes = list(netbox.ipam.get_ip_prefixes())
    print(f"Found {len(prefixes)} IP prefixes")
    
    # Get all IP addresses
    ip_addresses = list(netbox.ipam.get_ip_addresses())
    print(f"Found {len(ip_addresses)} IP addresses")
    
    # Get existing IP ranges to avoid duplicates
    existing_ranges = list(netbox.ipam.get_ip_ranges())
    existing_range_cidrs = set()
    
    for ip_range in existing_ranges:
        # Extract addresses with multiple methods
        start_ip = None
        end_ip = None
        
        # Method 1: Direct attribute access
        if hasattr(ip_range, 'start_address'):
            start_ip = getattr(ip_range, 'start_address', '').split('/')[0]
        if hasattr(ip_range, 'end_address'):
            end_ip = getattr(ip_range, 'end_address', '').split('/')[0]
        
        # Method 2: Dictionary access
        if start_ip is None and isinstance(ip_range, dict) and 'start_address' in ip_range:
            start_ip = ip_range['start_address'].split('/')[0]
        if end_ip is None and isinstance(ip_range, dict) and 'end_address' in ip_range:
            end_ip = ip_range['end_address'].split('/')[0]
        
        # Only add if we have both addresses
        if start_ip and end_ip:
            existing_range_cidrs.add(f"{start_ip}-{end_ip}")
    
    print(f"Found {len(existing_ranges)} existing IP ranges")
    
    # Group prefixes by larger containing prefixes
    network_groups = {}
    standalone_prefixes = []
    
    for prefix in prefixes:
        try:
            # Extract prefix string
            prefix_str = None
            if hasattr(prefix, 'prefix'):
                prefix_str = prefix.prefix
            elif isinstance(prefix, dict) and 'prefix' in prefix:
                prefix_str = prefix['prefix']
            else:
                continue
                
            prefix_net = ipaddress.ip_network(prefix_str)
            parent_found = False
            
            # Skip very small prefixes for analysis - less strict filtering
            if prefix_net.prefixlen >= 31 and isinstance(prefix_net, ipaddress.IPv4Network):
                continue
            if prefix_net.prefixlen >= 127 and isinstance(prefix_net, ipaddress.IPv6Network):
                continue
            
            # Find parent prefix
            for potential_parent in prefixes:
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
                except:
                    continue
            
            if not parent_found:
                standalone_prefixes.append(prefix)
        except Exception as e:
            continue
    
    # Process each network group to find gaps
    ranges_created = 0
    
    # Helper function to extract prefix string
    def get_prefix_str(p):
        if hasattr(p, 'prefix'):
            return p.prefix
        elif isinstance(p, dict) and 'prefix' in p:
            return p['prefix']
        return None
    
    # Helper function to extract network address
    def get_network_addr(p):
        p_str = get_prefix_str(p)
        if not p_str:
            return 0
        try:
            return int(ipaddress.ip_network(p_str).network_address)
        except:
            return 0
    
    for parent_prefix, child_prefixes in network_groups.items():
        try:
            parent = ipaddress.ip_network(parent_prefix)
            
            # Sort child prefixes by network address
            child_prefixes.sort(key=get_network_addr)
            
            # Process gaps between child prefixes
            prev_end = None
            
            for child in child_prefixes:
                child_str = get_prefix_str(child)
                if not child_str:
                    continue
                    
                try:
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
                                # Only add tags if the tag exists
                                tags_param = [{"name": "Available"}] if tag_exists else []
                                
                                ip_range = netbox.ipam.create_ip_range(
                                    start_address=str(start_ip),
                                    end_address=str(end_ip),
                                    description="Gap IP range",
                                    tags=tags_param
                                )
                                existing_range_cidrs.add(range_cidr)
                                ranges_created += 1
                                print(f"Created IP range: {start_ip} - {end_ip}")
                            except Exception as e:
                                error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                                print(f"DEBUG ERROR: {str(e)}")
                    
                    # Update prev_end for next iteration
                    prev_end = int(current.broadcast_address)
                except Exception:
                    continue
            
            # Check for gap after the last child prefix
            if prev_end is not None and prev_end < int(parent.broadcast_address):
                # Gap between last child and end of parent
                start_ip = ipaddress.ip_address(prev_end + 1)
                end_ip = ipaddress.ip_address(int(parent.broadcast_address))
                
                # Create IP range for this gap
                range_cidr = f"{start_ip}-{end_ip}"
                if range_cidr not in existing_range_cidrs:
                    try:
                        # Only add tags if the tag exists
                        tags_param = [{"name": "Available"}] if tag_exists else []
                        
                        ip_range = netbox.ipam.create_ip_range(
                            start_address=str(start_ip),
                            end_address=str(end_ip),
                            description="End gap IP range",
                            tags=tags_param
                        )
                        existing_range_cidrs.add(range_cidr)
                        ranges_created += 1
                        print(f"Created IP range: {start_ip} - {end_ip}")
                    except Exception as e:
                        error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                        print(f"DEBUG ERROR: {str(e)}")
                        
        except Exception as e:
            error_log(f"Error processing parent network {parent_prefix}: {str(e)}")
            print(f"DEBUG ERROR: {str(e)}")
    
    # Process standalone prefixes
    for prefix in standalone_prefixes:
        try:
            prefix_str = get_prefix_str(prefix)
            if not prefix_str:
                continue
                
            network = ipaddress.ip_network(prefix_str)
            
            # Check for addresses within this prefix
            contained_addresses = []
            for ip in ip_addresses:
                try:
                    # Extract IP address string
                    ip_addr_str = None
                    if hasattr(ip, 'address'):
                        ip_addr_str = ip.address
                    elif isinstance(ip, dict) and 'address' in ip:
                        ip_addr_str = ip['address']
                    else:
                        continue
                        
                    addr = ipaddress.ip_address(ip_addr_str.split('/')[0])
                    if addr in network:
                        contained_addresses.append(addr)
                except:
                    continue
            
            if not contained_addresses:
                # No addresses in this prefix, create range for whole prefix
                start_ip = network.network_address
                end_ip = network.broadcast_address
                range_cidr = f"{start_ip}-{end_ip}"
                
                if range_cidr not in existing_range_cidrs:
                    try:
                        # Only add tags if the tag exists
                        tags_param = [{"name": "Available"}] if tag_exists else []
                        
                        ip_range = netbox.ipam.create_ip_range(
                            start_address=str(start_ip),
                            end_address=str(end_ip),
                            description="Empty prefix IP range",
                            tags=tags_param
                        )
                        existing_range_cidrs.add(range_cidr)
                        ranges_created += 1
                        print(f"Created IP range for empty prefix: {start_ip} - {end_ip}")
                    except Exception as e:
                        error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                        print(f"DEBUG ERROR: {str(e)}")
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
                            # Only add tags if the tag exists
                            tags_param = [{"name": "Available"}] if tag_exists else []
                            
                            ip_range = netbox.ipam.create_ip_range(
                                start_address=str(start_ip),
                                end_address=str(end_ip),
                                description="Beginning gap IP range",
                                tags=tags_param
                            )
                            existing_range_cidrs.add(range_cidr)
                            ranges_created += 1
                            print(f"Created IP range: {start_ip} - {end_ip}")
                        except Exception as e:
                            error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                            print(f"DEBUG ERROR: {str(e)}")
                
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
                                # Only add tags if the tag exists
                                tags_param = [{"name": "Available"}] if tag_exists else []
                                
                                ip_range = netbox.ipam.create_ip_range(
                                    start_address=str(start_ip),
                                    end_address=str(end_ip),
                                    description="Middle gap IP range",
                                    tags=tags_param
                                )
                                existing_range_cidrs.add(range_cidr)
                                ranges_created += 1
                                print(f"Created IP range: {start_ip} - {end_ip}")
                            except Exception as e:
                                error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                                print(f"DEBUG ERROR: {str(e)}")
                
                # Check for gap at the end
                if int(contained_addresses[-1]) < int(network.broadcast_address):
                    start_ip = ipaddress.ip_address(int(contained_addresses[-1]) + 1)
                    end_ip = network.broadcast_address
                    range_cidr = f"{start_ip}-{end_ip}"
                    
                    if range_cidr not in existing_range_cidrs:
                        try:
                            # Only add tags if the tag exists
                            tags_param = [{"name": "Available"}] if tag_exists else []
                            
                            ip_range = netbox.ipam.create_ip_range(
                                start_address=str(start_ip),
                                end_address=str(end_ip),
                                description="End gap IP range",
                                tags=tags_param
                            )
                            existing_range_cidrs.add(range_cidr)
                            ranges_created += 1
                            print(f"Created IP range: {start_ip} - {end_ip}")
                        except Exception as e:
                            error_log(f"Error creating IP range {start_ip} - {end_ip}: {str(e)}")
                            print(f"DEBUG ERROR: {str(e)}")
        
        except Exception as e:
            continue
    
    print(f"IP range generation completed. Created {ranges_created} IP ranges.")

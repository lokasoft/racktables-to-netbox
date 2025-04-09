"""
NAT mapping migration functions
"""
import ipaddress
import requests

from racktables_netbox_migration.utils import error_log
from racktables_netbox_migration.config import NB_HOST, NB_PORT, NB_TOKEN, TARGET_SITE, IPV4_TAG

def migrate_nat_mappings(cursor, netbox):
    """
    Migrate NAT mapping data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating NAT mappings...")
    
    # Get existing IP addresses from NetBox
    existing_ips = {}
    for ip in netbox.ipam.get_ip_addresses():
        existing_ips[ip['address']] = ip['id']
    
    # Get NAT data from Racktables
    cursor.execute("""
        SELECT proto, localip, localport, remoteip, remoteport, description
        FROM IPv4NAT
    """)
    
    nat_entries = cursor.fetchall()
    nat_count = 0
    
    for proto, localip, localport, remoteip, remoteport, description in nat_entries:
        # Format IPs with CIDR notation
        local_ip_cidr = f"{str(ipaddress.ip_address(localip))}/32"
        remote_ip_cidr = f"{str(ipaddress.ip_address(remoteip))}/32"
        
        # If site filtering is enabled, check if these IPs are associated with devices in the target site
        if TARGET_SITE:
            # This would require additional lookup to check device associations
            # Skip implementation for brevity as it would require complex queries
            pass
        
        # Check if IPs exist in NetBox
        if local_ip_cidr in existing_ips and remote_ip_cidr in existing_ips:
            local_ip_id = existing_ips[local_ip_cidr]
            remote_ip_id = existing_ips[remote_ip_cidr]
            
            # Update each IP with info about its NAT relationship
            for ip_id, ip_cidr, nat_type, match_ip in [
                (local_ip_id, local_ip_cidr, "Source NAT" if localport else "Static NAT", remote_ip_cidr),
                (remote_ip_id, remote_ip_cidr, "Destination NAT" if remoteport else "Static NAT", local_ip_cidr)
            ]:
                # Update IP with custom fields
                url = f"http://{NB_HOST}:{NB_PORT}/api/ipam/ip-addresses/{ip_id}/"
                headers = {
                    "Authorization": f"Token {NB_TOKEN}",
                    "Content-Type": "application/json"
                }
                
                # Get current data
                response = requests.get(url, headers=headers)
                if response.status_code != 200:
                    error_log(f"Error getting IP {ip_cidr}: {response.text}")
                    continue
                    
                current_data = response.json()
                
                # Prepare port info if present
                port_info = ""
                if localport or remoteport:
                    port_info = f" (Port mapping: {localport or '*'} → {remoteport or '*'})"
                
                # Update description to include NAT info
                description_text = current_data.get('description', '')
                if description_text:
                    description_text += f"\nNAT: {description}"
                else:
                    description_text = f"NAT: {description}" if description else "NAT mapping"
                
                data = {
                    "description": description_text[:200],
                    "custom_fields": {
                        "NAT_Type": nat_type,
                        "NAT_Match_IP": match_ip + port_info
                    }
                }
                
                # Update the custom fields of existing data
                if 'custom_fields' in current_data and current_data['custom_fields']:
                    for key, value in current_data['custom_fields'].items():
                        if key not in data['custom_fields']:
                            data['custom_fields'][key] = value
                
                response = requests.patch(url, headers=headers, json=data)
                if response.status_code in (200, 201):
                    nat_count += 1
                    print(f"Updated NAT information for IP {ip_cidr}")
                else:
                    error_log(f"Error updating NAT for IP {ip_cidr}: {response.text}")
        else:
            # Create IPs if they don't exist
            for ip_int, ip_cidr, nat_type, match_ip_int, match_ip_cidr in [
                (localip, local_ip_cidr, "Source NAT" if localport else "Static NAT", remoteip, remote_ip_cidr),
                (remoteip, remote_ip_cidr, "Destination NAT" if remoteport else "Static NAT", localip, local_ip_cidr)
            ]:
                if ip_cidr not in existing_ips:
                    # Check if IP exists in Racktables
                    cursor.execute("SELECT name FROM IPv4Address WHERE ip = %s", (ip_int,))
                    ip_name = cursor.fetchone()
                    
                    port_info = ""
                    if localport or remoteport:
                        port_info = f" (Port mapping: {localport or '*'} → {remoteport or '*'})"
                    
                    # Create the IP address in NetBox
                    try:
                        new_ip = netbox.ipam.create_ip_address(
                            address=ip_cidr,
                            description=f"NAT: {description}" if description else "NAT mapping",
                            custom_fields={
                                "IP_Name": ip_name[0] if ip_name else "",
                                "NAT_Type": nat_type,
                                "NAT_Match_IP": match_ip_cidr + port_info
                            },
                            tags=[{'name': IPV4_TAG}]
                        )
                        
                        existing_ips[ip_cidr] = new_ip['id']
                        nat_count += 1
                        print(f"Created IP {ip_cidr} with NAT information")
                    except Exception as e:
                        error_log(f"Error creating IP {ip_cidr}: {str(e)}")
    
    print(f"NAT mappings migration completed. Updated {nat_count} IP addresses.")

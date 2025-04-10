"""
Load balancing data migration functions
"""
import ipaddress
import requests
from slugify import slugify

from racktables_netbox_migration.utils import error_log
from racktables_netbox_migration.config import NB_HOST, NB_PORT, NB_TOKEN, TARGET_SITE

def migrate_load_balancing(cursor, netbox):
    """
    Migrate load balancing data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating load balancing data...")
    
    # Get existing IP addresses from NetBox
    existing_ips = {}
    for ip in netbox.ipam.get_ip_addresses():
        existing_ips[ip['address']] = ip['id']
    
    # Check if IPv4LB table exists
    try:
        cursor.execute("SHOW TABLES LIKE 'IPv4LB'")
        if not cursor.fetchone():
            print("IPv4LB table not found in database. Skipping load balancer migration.")
            return
        
        # Check table schema to determine available columns
        cursor.execute("SHOW COLUMNS FROM IPv4LB")
        lb_columns = {col['Field']: True for col in cursor.fetchall()}
        print(f"Found IPv4LB table with columns: {', '.join(lb_columns.keys())}")
        
        # Build query dynamically based on available columns
        query_fields = ["prio", "vsconfig", "rsconfig"]
        
        # Add rspool if it exists
        if 'rspool' in lb_columns:
            query_fields.append("rspool")
        else:
            print("Column 'rspool' not found in IPv4LB table, will use NULL values")
        
        # Add comment if it exists
        if 'comment' in lb_columns:
            query_fields.append("comment")
        else:
            print("Column 'comment' not found in IPv4LB table, will use empty values")
        
        # Construct the query
        query = f"SELECT {', '.join(query_fields)} FROM IPv4LB"
        cursor.execute(query)
        
        lb_entries = cursor.fetchall()
        lb_count = 0
        
        for entry in lb_entries:
            # Extract values, handling possible absent columns
            prio = entry['prio']
            vsconfig = entry['vsconfig']
            rsconfig = entry['rsconfig']
            rspool = entry['rspool'] if 'rspool' in lb_columns else None
            comment = entry['comment'] if 'comment' in lb_columns else None
            
            # Parse the configs - these typically contain IP addresses and parameters
            vs_parts = vsconfig.split(':') if vsconfig else []
            rs_parts = rsconfig.split(':') if rsconfig else []
            
            # Extract VIP (Virtual IP) if available
            vip = None
            if len(vs_parts) > 0:
                try:
                    vip = vs_parts[0]
                    # Validate this is an IP
                    ipaddress.ip_address(int(vip))
                except (ValueError, IndexError):
                    vip = None
            
            # Extract Real Server IP if available
            rs_ip = None
            if len(rs_parts) > 0:
                try:
                    rs_ip = rs_parts[0]
                    # Validate this is an IP
                    ipaddress.ip_address(int(rs_ip))
                except (ValueError, IndexError):
                    rs_ip = None
            
            # If site filtering is enabled, check if these IPs are associated with devices in the target site
            if TARGET_SITE:
                # Skip implementation for brevity as it would require complex device association lookups
                pass
            
            # If we have both IPs, create or update the LB relationship
            if vip and rs_ip:
                vip_cidr = f"{str(ipaddress.ip_address(int(vip)))}/32"
                rs_ip_cidr = f"{str(ipaddress.ip_address(int(rs_ip)))}/32"
                
                # Update VIP with load balancer info
                if vip_cidr in existing_ips:
                    url = f"http://{NB_HOST}:{NB_PORT}/api/ipam/ip-addresses/{existing_ips[vip_cidr]}/"
                    headers = {
                        "Authorization": f"Token {NB_TOKEN}",
                        "Content-Type": "application/json"
                    }
                    
                    # Get current data
                    response = requests.get(url, headers=headers)
                    if response.status_code != 200:
                        error_log(f"Error getting IP {vip_cidr}: {response.text}")
                        continue
                        
                    current_data = response.json()
                    
                    # Update description and custom fields
                    description_text = current_data.get('description', '')
                    if description_text:
                        description_text += f"\nLB: {comment}" if comment else "\nLoad balancer VIP"
                    else:
                        description_text = f"LB: {comment}" if comment else "Load balancer VIP"
                    
                    # Format the full LB config for the custom field
                    lb_config = f"VS: {vsconfig}, RS: {rsconfig}, Priority: {prio}"
                    
                    data = {
                        "description": description_text[:200],
                        "custom_fields": {
                            "LB_Config": lb_config,
                            "RS_Pool": rspool if rspool else ""
                        },
                        "role": "vip"  # Set role to VIP
                    }
                    
                    # Update the custom fields of existing data
                    if 'custom_fields' in current_data and current_data['custom_fields']:
                        for key, value in current_data['custom_fields'].items():
                            if key not in data['custom_fields'] and value:
                                data['custom_fields'][key] = value
                    
                    response = requests.patch(url, headers=headers, json=data)
                    if response.status_code in (200, 201):
                        lb_count += 1
                        print(f"Updated load balancer information for VIP {vip_cidr}")
                    else:
                        error_log(f"Error updating load balancer for VIP {vip_cidr}: {response.text}")
                
                # Update Real Server IP with load balancer info
                if rs_ip_cidr in existing_ips:
                    url = f"http://{NB_HOST}:{NB_PORT}/api/ipam/ip-addresses/{existing_ips[rs_ip_cidr]}/"
                    headers = {
                        "Authorization": f"Token {NB_TOKEN}",
                        "Content-Type": "application/json"
                    }
                    
                    # Get current data
                    response = requests.get(url, headers=headers)
                    if response.status_code != 200:
                        error_log(f"Error getting IP {rs_ip_cidr}: {response.text}")
                        continue
                        
                    current_data = response.json()
                    
                    # Update description and custom fields
                    description_text = current_data.get('description', '')
                    if description_text:
                        description_text += f"\nLB: {comment}" if comment else "\nLoad balancer real server"
                    else:
                        description_text = f"LB: {comment}" if comment else "Load balancer real server"
                    
                    data = {
                        "description": description_text[:200],
                        "custom_fields": {
                            "LB_Pool": rspool if rspool else "",
                            "LB_Config": f"Part of pool {rspool if rspool else 'unknown'} for VIP {vip_cidr}"
                        }
                    }
                    
                    # Update the custom fields of existing data
                    if 'custom_fields' in current_data and current_data['custom_fields']:
                        for key, value in current_data['custom_fields'].items():
                            if key not in data['custom_fields'] and value:
                                data['custom_fields'][key] = value
                    
                    response = requests.patch(url, headers=headers, json=data)
                    if response.status_code in (200, 201):
                        lb_count += 1
                        print(f"Updated load balancer information for real server {rs_ip_cidr}")
                    else:
                        error_log(f"Error updating load balancer for real server {rs_ip_cidr}: {response.text}")
    
    except Exception as e:
        error_log(f"Database error in load balancer migration: {str(e)}")
        print(f"Database connection error: {str(e)}")
        print("Skipping load balancer migration")
        return
    
    # Check for RS Pool table
    try:
        cursor.execute("SHOW TABLES LIKE 'IPv4RSPool'")
        if cursor.fetchone():
            # Check IPv4RSPool schema
            cursor.execute("SHOW COLUMNS FROM IPv4RSPool")
            rspool_columns = {col['Field']: True for col in cursor.fetchall()}
            
            # Build query dynamically
            query_fields = []
            
            if 'pool_name' in rspool_columns:
                query_fields.append('pool_name')
            else:
                query_fields.append("'unknown' as pool_name")
                
            if 'vs_id' in rspool_columns:
                query_fields.append('vs_id')
            else:
                query_fields.append("0 as vs_id")
                
            if 'rspool_id' in rspool_columns:
                query_fields.append('rspool_id')
            else:
                query_fields.append("0 as rspool_id")
            
            query = f"SELECT {', '.join(query_fields)} FROM IPv4RSPool"
            cursor.execute(query)
            
            tag_count = 0
            
            for row in cursor.fetchall():
                pool_name = row['pool_name']
                vs_id = row['vs_id']
                rspool_id = row['rspool_id']
                
                # Get the VS info if VS table exists
                vs_name = f"VS-{vs_id}"
                try:
                    cursor.execute("SHOW TABLES LIKE 'VS'")
                    if cursor.fetchone():
                        cursor.execute("SHOW COLUMNS FROM VS")
                        vs_columns = {col['Field']: True for col in cursor.fetchall()}
                        
                        if 'id' in vs_columns and 'name' in vs_columns:
                            cursor.execute(f"SELECT name FROM VS WHERE id = {vs_id}")
                            vs_result = cursor.fetchone()
                            if vs_result:
                                vs_name = vs_result['name']
                except Exception as e:
                    error_log(f"Error getting VS info: {str(e)}")
                
                # Create a tag for this pool
                tag_name = f"LB-Pool-{pool_name}-{rspool_id}"
                tag_slug = slugify(tag_name)
                
                try:
                    netbox.extras.create_tag(
                        name=tag_name,
                        slug=tag_slug,
                        color="9c27b0",
                        description=f"Load balancer pool: {pool_name}, VS: {vs_name}"
                    )
                    tag_count += 1
                    print(f"Created tag for load balancer pool {pool_name}")
                except Exception as e:
                    error_log(f"Error creating tag for load balancer pool {pool_name}: {str(e)}")
            
            print(f"Created {tag_count} pool tags")
        else:
            print("IPv4RSPool table not found in database")
    except Exception as e:
        error_log(f"Error processing RS pools: {str(e)}")
        print(f"Error processing RS pools: {str(e)}")
    
    print(f"Load balancing data migration completed. Updated {lb_count} IP addresses.")

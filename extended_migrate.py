"""
Extended migration script for transferring data from Racktables to NetBox
This version includes support for additional tables not covered in the original migration
"""

# Import from existing migrate.py to avoid duplicating code
from migrate import *
import os
import base64
import requests
from slugify import slugify
import time

# Additional flags for new migration components
CREATE_PATCH_CABLES =          True
CREATE_FILES =                 True
CREATE_VIRTUAL_SERVICES =      True
CREATE_NAT_MAPPINGS =          True
CREATE_LOAD_BALANCING =        True
CREATE_MONITORING_DATA =       True

# Dictionary to map patch cable connector types
connector_types = {}

# Dictionary to map patch cable types
cable_types = {}

# Function to migrate patch cable data
def migrate_patch_cables(cursor, netbox):
    """
    Migrate patch cable data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating patch cable data...")
    
    # Load connector types
    cursor.execute("SELECT id, connector_name FROM PatchCableConnector")
    for conn_id, conn_name in cursor.fetchall():
        connector_types[conn_id] = conn_name
        
    # Load cable types
    cursor.execute("SELECT id, pctype_name FROM PatchCableType")
    for type_id, type_name in cursor.fetchall():
        cable_types[type_id] = type_name
    
    # Get existing cables in NetBox to avoid duplicates
    existing_cables = set()
    for cable in netbox.dcim.get_cables():
        if cable['termination_a_type'] == 'dcim.interface' and cable['termination_b_type'] == 'dcim.interface':
            cable_key = f"{cable['termination_a_id']}-{cable['termination_b_id']}"
            existing_cables.add(cable_key)
    
    # Get patch cable heap (inventory)
    cursor.execute("""
        SELECT id, pctype_id, end1_conn_id, end2_conn_id, length, color, description 
        FROM PatchCableHeap
    """)
    
    # Process patch cables in inventory (not yet connected)
    for cable_id, pctype_id, end1_conn_id, end2_conn_id, length, color, description in cursor.fetchall():
        # For inventory items, we'll create custom tags since they're not connected yet
        cable_type = cable_types.get(pctype_id, "Unknown")
        connector_a = connector_types.get(end1_conn_id, "Unknown")
        connector_b = connector_types.get(end2_conn_id, "Unknown")
        
        # Create a tag that represents this cable in inventory
        tag_name = f"Cable-{cable_id}-{cable_type}-{color}"
        tag_slug = slugify(tag_name)
        
        try:
            netbox.extras.create_tag(
                name=tag_name, 
                slug=tag_slug,
                color="2196f3",
                description=f"Cable type: {cable_type}, Length: {length}, Connectors: {connector_a}/{connector_b}, Description: {description}"
            )
            print(f"Created inventory tag for cable ID {cable_id}")
        except Exception as e:
            error_log(f"Error creating tag for cable {cable_id}: {str(e)}")
    
    # Process connections from the Link table that represent cables
    # These are already created in the CREATE_INTERFACE_CONNECTIONS section,
    # so we'll update them with additional information
    cursor.execute("""
        SELECT L.porta, L.portb, L.cable 
        FROM Link L
        WHERE L.cable IS NOT NULL
    """)
    
    connection_ids = pickleLoad('connection_ids', dict())
    
    for porta_id, portb_id, cable_id in cursor.fetchall():
        if porta_id not in connection_ids or portb_id not in connection_ids:
            continue
            
        netbox_id_a = connection_ids[porta_id]
        netbox_id_b = connection_ids[portb_id]
        
        # Skip if the cable already exists
        cable_key = f"{netbox_id_a}-{netbox_id_b}"
        if cable_key in existing_cables:
            # Get the cable
            for cable in netbox.dcim.get_cables():
                if ((cable['termination_a_id'] == netbox_id_a and cable['termination_b_id'] == netbox_id_b) or
                    (cable['termination_a_id'] == netbox_id_b and cable['termination_b_id'] == netbox_id_a)):
                    
                    # Get cable details from PatchCableHeap
                    cursor.execute("""
                        SELECT pctype_id, end1_conn_id, end2_conn_id, length, color, description
                        FROM PatchCableHeap
                        WHERE id = %s
                    """, (cable_id,))
                    
                    cable_data = cursor.fetchone()
                    if cable_data:
                        pctype_id, end1_conn_id, end2_conn_id, length, color, description = cable_data
                        
                        # Update the cable with custom fields
                        cable_type = cable_types.get(pctype_id, "Unknown")
                        connector_a = connector_types.get(end1_conn_id, "Unknown")
                        connector_b = connector_types.get(end2_conn_id, "Unknown")
                        
                        # Use the requests library to update the cable directly with custom fields
                        url = f"http://{nb_host}:{nb_port}/api/dcim/cables/{cable['id']}/"
                        headers = {
                            "Authorization": f"Token {nb_token}",
                            "Content-Type": "application/json"
                        }
                        
                        data = {
                            "custom_fields": {
                                "Patch_Cable_Type": cable_type,
                                "Patch_Cable_Connector_A": connector_a,
                                "Patch_Cable_Connector_B": connector_b,
                                "Cable_Color": color,
                                "Cable_Length": str(length) if length else ""
                            },
                            "label": f"{cable_type}-{color}",
                            "color": color,
                            "length": length,
                            "length_unit": "m",
                            "description": description
                        }
                        
                        response = requests.patch(url, headers=headers, json=data)
                        if response.status_code in (200, 201):
                            print(f"Updated cable information for cable between {netbox_id_a} and {netbox_id_b}")
                        else:
                            error_log(f"Error updating cable {cable['id']}: {response.text}")
                            
                    break
    
    print("Patch cable migration completed.")

# Function to migrate file attachments
def migrate_files(cursor, netbox):
    """
    Migrate file attachments from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating file attachments...")
    
    # Get files from Racktables
    cursor.execute("SELECT id, name, type, size, contents FROM File")
    file_data = cursor.fetchall()
    
    # Track migrated files for reference
    migrated_files = {}
    
    # Set up directory for file storage
    file_dir = "racktables_files"
    os.makedirs(file_dir, exist_ok=True)
    
    for file_id, file_name, file_type, file_size, file_contents in file_data:
        # Save file locally
        file_path = os.path.join(file_dir, f"{file_id}_{file_name}")
        with open(file_path, "wb") as f:
            f.write(file_contents)
        
        migrated_files[file_id] = {
            "name": file_name,
            "path": file_path,
            "type": file_type,
            "size": file_size
        }
        
        print(f"Saved file: {file_name} (ID: {file_id})")
    
    # Now get file links to associate files with objects
    cursor.execute("""
        SELECT FL.file_id, FL.entity_type, FL.entity_id, F.name
        FROM FileLink FL
        JOIN File F ON FL.file_id = F.id
    """)
    
    for file_id, entity_type, entity_id, file_name in cursor.fetchall():
        if entity_type == 'object':
            # Get the object name
            cursor.execute("SELECT name, objtype_id FROM Object WHERE id = %s", (entity_id,))
            obj_data = cursor.fetchone()
            
            if not obj_data:
                continue
                
            obj_name, objtype_id = obj_data
            
            # Skip if the name is empty
            if not obj_name:
                continue
                
            obj_name = obj_name.strip()
            
            # Determine if this is a device or VM
            is_vm = (objtype_id == 1504)  # VM objtype_id
            
            # Find the object in NetBox
            if is_vm:
                obj = netbox.virtualization.get_virtual_machines(name=obj_name)
            else:
                obj = netbox.dcim.get_devices(name=obj_name)
            
            if not obj:
                error_log(f"Could not find object {obj_name} to attach file {file_name}")
                continue
                
            obj = obj[0]
            
            # Update the object with file reference in custom fields
            if is_vm:
                url = f"http://{nb_host}:{nb_port}/api/virtualization/virtual-machines/{obj['id']}/"
            else:
                url = f"http://{nb_host}:{nb_port}/api/dcim/devices/{obj['id']}/"
                
            headers = {
                "Authorization": f"Token {nb_token}",
                "Content-Type": "application/json"
            }
            
            # Get current value if it exists
            response = requests.get(url, headers=headers)
            current_data = response.json()
            
            file_refs = current_data.get('custom_fields', {}).get('File_References', "")
            if file_refs:
                file_refs += f", {file_name} (from Racktables)"
            else:
                file_refs = f"{file_name} (from Racktables)"
            
            data = {
                "custom_fields": {
                    "File_References": file_refs
                }
            }
            
            response = requests.patch(url, headers=headers, json=data)
            if response.status_code in (200, 201):
                print(f"Updated file reference for {obj_name}: {file_name}")
            else:
                error_log(f"Error updating file reference: {response.text}")
    
    # Create a summary document about migrated files
    with open(os.path.join(file_dir, "migrated_files.txt"), "w") as f:
        f.write("# Migrated Files from Racktables\n\n")
        f.write("This document lists files migrated from Racktables to local storage.\n")
        f.write("File references have been added to device custom fields.\n\n")
        
        f.write("## File List\n\n")
        for file_id, file_info in migrated_files.items():
            f.write(f"- {file_info['name']} (ID: {file_id})\n")
            f.write(f"  Type: {file_info['type']}, Size: {file_info['size']} bytes\n")
            f.write(f"  Saved to: {file_info['path']}\n\n")
    
    print(f"File migration completed. Files saved to {file_dir} directory.")
    print(f"See {os.path.join(file_dir, 'migrated_files.txt')} for a summary.")

# Function to migrate virtual services
def migrate_virtual_services(cursor, netbox):
    """
    Migrate virtual services data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating virtual services...")
    
    # Get existing services to avoid duplicates
    existing_services = {}
    for service in netbox.ipam.get_services():
        key = f"{service.get('device_id') or service.get('virtual_machine_id')}-{service['name']}-{','.join(map(str, service['ports']))}"
        existing_services[key] = service['id']
    
    # Get VS data from Racktables
    cursor.execute("SELECT vs_id, name, description FROM VS")
    
    for vs_id, name, description in cursor.fetchall():
        # Get the enabled IPs for this VS
        cursor.execute("""
            SELECT IP.ip, IP.name, OBJ.name, OBJ.objtype_id 
            FROM VSEnabledIPs VS
            JOIN IPv4Address IP ON VS.ip_id = IP.id
            LEFT JOIN IPv4Allocation ALLOC ON IP.ip = ALLOC.ip
            LEFT JOIN Object OBJ ON ALLOC.object_id = OBJ.id
            WHERE VS.vs_id = %s
        """, (vs_id,))
        
        vs_ips = cursor.fetchall()
        
        # Get the enabled ports for this VS
        cursor.execute("""
            SELECT vsp.port_name, vsp.port_type, vsp.real_port_name
            FROM VSPorts vsp
            WHERE vsp.vs_id = %s
        """, (vs_id,))
        
        vs_ports = cursor.fetchall()
        
        # Collect port numbers
        port_numbers = []
        for port_name, port_type, real_port_name in vs_ports:
            try:
                port_number = int(port_name)
                port_numbers.append(port_number)
            except ValueError:
                # If port_name isn't a number, check real_port_name
                try:
                    if real_port_name:
                        port_number = int(real_port_name)
                        port_numbers.append(port_number)
                except ValueError:
                    pass
        
        if not port_numbers:
            # Default port if none specified
            port_numbers = [80]
        
        # Default protocol to TCP if we don't have specific info
        protocol = "tcp"
        
        # Create a service for each associated device or VM
        for ip, ip_name, obj_name, objtype_id in vs_ips:
            if not obj_name:
                continue
                
            obj_name = obj_name.strip()
            
            # Determine if this is a VM or a device
            is_vm = (objtype_id == 1504)  # VM objtype_id
            
            # Create a unique service name including IP info
            service_name = f"{name}-{ip_name}" if ip_name else name
            
            # Skip if service already exists
            service_key = ""
            if is_vm:
                vm = netbox.virtualization.get_virtual_machines(name=obj_name)
                if vm:
                    service_key = f"{vm[0]['id']}-{service_name}-{','.join(map(str, port_numbers))}"
                    if service_key in existing_services:
                        continue
            else:
                device = netbox.dcim.get_devices(name=obj_name)
                if device:
                    service_key = f"{device[0]['id']}-{service_name}-{','.join(map(str, port_numbers))}"
                    if service_key in existing_services:
                        continue
            
            try:
                # Create the service
                if is_vm:
                    vm = netbox.virtualization.get_virtual_machines(name=obj_name)
                    if vm:
                        service = netbox.virtualization.create_service(
                            virtual_machine=obj_name,
                            name=service_name,
                            ports=port_numbers,
                            protocol=protocol,
                            description=description[:200] if description else "",
                            custom_fields={
                                "VS_Enabled": True,
                                "VS_Type": "Virtual Service",
                                "VS_Protocol": protocol
                            }
                        )
                        print(f"Created service {service_name} for VM {obj_name}")
                else:
                    device = netbox.dcim.get_devices(name=obj_name)
                    if device:
                        service = netbox.ipam.create_service(
                            device=obj_name,
                            name=service_name,
                            ports=port_numbers,
                            protocol=protocol,
                            description=description[:200] if description else "",
                            custom_fields={
                                "VS_Enabled": True,
                                "VS_Type": "Virtual Service",
                                "VS_Protocol": protocol
                            }
                        )
                        print(f"Created service {service_name} for device {obj_name}")
            except Exception as e:
                error_log(f"Error creating service {service_name}: {str(e)}")
    
    print("Virtual services migration completed.")

# Function to migrate NAT mappings
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
    
    for proto, localip, localport, remoteip, remoteport, description in nat_entries:
        # Format IPs with CIDR notation
        local_ip_cidr = f"{str(ipaddress.ip_address(localip))}/32"
        remote_ip_cidr = f"{str(ipaddress.ip_address(remoteip))}/32"
        
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
                url = f"http://{nb_host}:{nb_port}/api/ipam/ip-addresses/{ip_id}/"
                headers = {
                    "Authorization": f"Token {nb_token}",
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
                            tags=[{'name': 'IPv4'}]
                        )
                        
                        existing_ips[ip_cidr] = new_ip['id']
                        print(f"Created IP {ip_cidr} with NAT information")
                    except Exception as e:
                        error_log(f"Error creating IP {ip_cidr}: {str(e)}")
    
    print("NAT mappings migration completed.")

# Function to migrate load balancing data
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
    
    # Get load balancer data from Racktables
    cursor.execute("""
        SELECT prio, vsconfig, rsconfig, rspool, comment
        FROM IPv4LB
    """)
    
    lb_entries = cursor.fetchall()
    
    for prio, vsconfig, rsconfig, rspool, comment in lb_entries:
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
        
        # If we have both IPs, create or update the LB relationship
        if vip and rs_ip:
            vip_cidr = f"{str(ipaddress.ip_address(int(vip)))}/32"
            rs_ip_cidr = f"{str(ipaddress.ip_address(int(rs_ip)))}/32"
            
            # Update VIP with load balancer info
            if vip_cidr in existing_ips:
                url = f"http://{nb_host}:{nb_port}/api/ipam/ip-addresses/{existing_ips[vip_cidr]}/"
                headers = {
                    "Authorization": f"Token {nb_token}",
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
                        "RS_Pool": rspool
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
                    print(f"Updated load balancer information for VIP {vip_cidr}")
                else:
                    error_log(f"Error updating load balancer for VIP {vip_cidr}: {response.text}")
            
            # Update Real Server IP with load balancer info
            if rs_ip_cidr in existing_ips:
                url = f"http://{nb_host}:{nb_port}/api/ipam/ip-addresses/{existing_ips[rs_ip_cidr]}/"
                headers = {
                    "Authorization": f"Token {nb_token}",
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
                        "LB_Pool": rspool,
                        "LB_Config": f"Part of pool {rspool} for VIP {vip_cidr}"
                    }
                }
                
                # Update the custom fields of existing data
                if 'custom_fields' in current_data and current_data['custom_fields']:
                    for key, value in current_data['custom_fields'].items():
                        if key not in data['custom_fields'] and value:
                            data['custom_fields'][key] = value
                
                response = requests.patch(url, headers=headers, json=data)
                if response.status_code in (200, 201):
                    print(f"Updated load balancer information for real server {rs_ip_cidr}")
                else:
                    error_log(f"Error updating load balancer for real server {rs_ip_cidr}: {response.text}")
    
    # Handle RS Pool data
    cursor.execute("""
        SELECT pool_name, vs_id, rspool_id
        FROM IPv4RSPool
    """)
    
    for pool_name, vs_id, rspool_id in cursor.fetchall():
        # Get the VS info
        cursor.execute("SELECT name FROM VS WHERE vs_id = %s", (vs_id,))
        vs_result = cursor.fetchone()
        vs_name = vs_result[0] if vs_result else f"VS-{vs_id}"
        
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
            print(f"Created tag for load balancer pool {pool_name}")
        except Exception as e:
            error_log(f"Error creating tag for load balancer pool {pool_name}: {str(e)}")
    
    print("Load balancing data migration completed.")

# Function to migrate monitoring data
def migrate_monitoring(cursor, netbox):
    """
    Migrate monitoring data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating monitoring data...")
    
    # Get Cacti servers
    cursor.execute("SELECT id, base_url FROM CactiServer")
    cacti_servers = {}
    
    for server_id, base_url in cursor.fetchall():
        cacti_servers[server_id] = base_url
    
    # Get Cacti graphs associated with objects
    cursor.execute("""
        SELECT CG.object_id, CG.server_id, CG.graph_id, CG.caption, OBJ.name, OBJ.objtype_id
        FROM CactiGraph CG
        JOIN Object OBJ ON CG.object_id = OBJ.id
    """)
    
    for object_id, server_id, graph_id, caption, obj_name, objtype_id in cursor.fetchall():
        if not obj_name:
            continue
            
        obj_name = obj_name.strip()
        
        # Determine if this is a VM or a device
        is_vm = (objtype_id == 1504)  # VM objtype_id
        
        # Find the object in NetBox
        if is_vm:
            objects = netbox.virtualization.get_virtual_machines(name=obj_name)
        else:
            objects = netbox.dcim.get_devices(name=obj_name)
        
        if not objects:
            error_log(f"Could not find object {obj_name} to update monitoring data")
            continue
            
        obj = objects[0]
        
        # Get the Cacti server base URL
        base_url = cacti_servers.get(server_id, "")
        
        # Construct the monitoring URL if we have the base URL
        monitoring_url = ""
        if base_url and graph_id:
            monitoring_url = f"{base_url.rstrip('/')}/graph_view.php?action=tree&select_first=true&graph_id={graph_id}"
        
        # Update the object with monitoring information
        if is_vm:
            url = f"http://{nb_host}:{nb_port}/api/virtualization/virtual-machines/{obj['id']}/"
        else:
            url = f"http://{nb_host}:{nb_port}/api/dcim/devices/{obj['id']}/"
            
        headers = {
            "Authorization": f"Token {nb_token}",
            "Content-Type": "application/json"
        }
        
        # Get current data
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            error_log(f"Error getting object {obj_name}: {response.text}")
            continue
            
        current_data = response.json()
        
        # Prepare data for update
        data = {
            "custom_fields": {
                "Cacti_Server": base_url,
                "Cacti_Graph_ID": str(graph_id),
                "Monitoring_URL": monitoring_url
            }
        }
        
        # Update the custom fields of existing data
        if 'custom_fields' in current_data and current_data['custom_fields']:
            for key, value in current_data['custom_fields'].items():
                if key not in data['custom_fields'] and value:
                    data['custom_fields'][key] = value
        
        response = requests.patch(url, headers=headers, json=data)
        if response.status_code in (200, 201):
            print(f"Updated monitoring information for {obj_name}")
        else:
            error_log(f"Error updating monitoring for {obj_name}: {response.text}")
    
    print("Monitoring data migration completed.")

# Extended main function that calls existing migrations and adds new ones
def migrate_extended():
    """Run the extended migration process including additional tables"""
    
    # Run original migration components if enabled
    if CREATE_VLAN_GROUPS or CREATE_VLANS or CREATE_MOUNTED_VMS or CREATE_UNMOUNTED_VMS or \
       CREATE_RACKED_DEVICES or CREATE_NON_RACKED_DEVICES or CREATE_INTERFACES or \
       CREATE_INTERFACE_CONNECTIONS or CREATE_IPV4 or CREATE_IPV6 or CREATE_IP_NETWORKS or \
       CREATE_IP_ALLOCATED or CREATE_IP_NOT_ALLOCATED:
        print("\nRunning base migration components...")
        
        # Import original functions from migrate.py
        # All these will run as part of the normal workflow
    
    # Run additional migration components if enabled
    with connection.cursor() as cursor:
        if CREATE_PATCH_CABLES:
            migrate_patch_cables(cursor, netbox)
        
        if CREATE_FILES:
            migrate_files(cursor, netbox)
            
        if CREATE_VIRTUAL_SERVICES:
            migrate_virtual_services(cursor, netbox)
            
        if CREATE_NAT_MAPPINGS:
            migrate_nat_mappings(cursor, netbox)
            
        if CREATE_LOAD_BALANCING:
            migrate_load_balancing(cursor, netbox)
            
        if CREATE_MONITORING_DATA:
            migrate_monitoring(cursor, netbox)
    
    print("\nExtended migration completed successfully!")

if __name__ == "__main__":
    migrate_extended()

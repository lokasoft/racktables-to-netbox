"""
Virtual services migration functions
"""
from migration.utils import error_log
from migration.config import TARGET_SITE

def migrate_virtual_services(cursor, netbox):
    """
    Migrate virtual services data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating virtual services...")
    
    # Check if VS table exists
    try:
        cursor.execute("SHOW TABLES LIKE 'VS'")
        vs_exists = cursor.fetchone() is not None
        
        if not vs_exists:
            print("VS table not found in database. Skipping virtual services migration.")
            return
        
        # Get columns for VS table
        cursor.execute("SHOW COLUMNS FROM VS")
        vs_columns = [col['Field'] for col in cursor.fetchall()]
        print(f"VS table columns: {', '.join(vs_columns)}")
        
        # Check for required columns
        if 'vs_id' not in vs_columns:
            print("VS table doesn't have 'vs_id' column. Looking for alternative primary key.")
            # Look for potential primary key columns
            primary_key = 'id' if 'id' in vs_columns else vs_columns[0]
            print(f"Using {primary_key} as primary key for VS table")
        else:
            primary_key = 'vs_id'
        
        # Check if name column exists
        if 'name' in vs_columns:
            name_col = 'name'
        else:
            # Try to find a name-like column
            name_cols = [col for col in vs_columns if 'name' in col.lower()]
            if name_cols:
                name_col = name_cols[0]
            else:
                name_col = vs_columns[1] if len(vs_columns) > 1 else None
            
        if not name_col:
            print("No suitable name column found in VS table. Skipping virtual services migration.")
            return
        print(f"Using {name_col} as name column for VS table")
        
        # Check if description column exists
        description_col = None
        for col in vs_columns:
            if 'description' in col.lower() or 'comment' in col.lower() or 'desc' in col.lower():
                description_col = col
                break
        
        if description_col:
            print(f"Using {description_col} as description column for VS table")
        else:
            print("No description column found in VS table. Using empty descriptions.")
    
    except Exception as e:
        error_log(f"Database error checking VS table: {str(e)}")
        print(f"Database error: {e}")
        print("Skipping virtual services migration.")
        return
    
    # Get device names in target site if site filtering is enabled
    site_device_names = set()
    if TARGET_SITE:
        print(f"Filtering services for site: {TARGET_SITE}")
        site_devices = netbox.dcim.get_devices(site=TARGET_SITE)
        site_device_names = set(device['name'] for device in site_devices)
        
        # Also include VMs in clusters at the target site
        site_clusters = netbox.virtualization.get_clusters(site=TARGET_SITE)
        for cluster in site_clusters:
            cluster_vms = netbox.virtualization.get_virtual_machines(cluster_id=cluster['id'])
            site_device_names.update(vm['name'] for vm in cluster_vms)
    
    # Get existing services to avoid duplicates
    existing_services = {}
    for service in netbox.ipam.get_services():
        device_id = service.get('device_id') or service.get('virtual_machine_id')
        if device_id:
            key = f"{device_id}-{service['name']}-{','.join(map(str, service['ports']))}"
            existing_services[key] = service['id']
    
    # Get VS data from Racktables with dynamic column names
    try:
        query = f"SELECT {primary_key}, {name_col}"
        if description_col:
            query += f", {description_col}"
        query += " FROM VS"
        
        cursor.execute(query)
        vs_data = cursor.fetchall()
        print(f"Found {len(vs_data)} virtual services")
    except Exception as e:
        error_log(f"Error querying VS table: {str(e)}")
        print(f"Error querying VS table: {e}")
        return
    
    # Check for VSEnabledIPs table or alternatives
    vsenabled_exists = False
    vsenabled_table = None
    vs_id_col = None
    ip_id_col = None
    
    try:
        cursor.execute("SHOW TABLES LIKE 'VSEnabledIPs'")
        if cursor.fetchone():
            vsenabled_exists = True
            vsenabled_table = "VSEnabledIPs"
            vs_id_col = "vs_id"
            ip_id_col = "ip_id"
            print("Found VSEnabledIPs table")
        else:
            # Look for alternative tables 
            cursor.execute("SHOW TABLES LIKE '%VS%IP%'")
            alt_tables = [row[0] for row in cursor.fetchall()]
            
            if alt_tables:
                print(f"Found alternative IP tables: {', '.join(alt_tables)}")
                vsenabled_exists = True
                vsenabled_table = alt_tables[0]
                
                # Get columns for this table
                cursor.execute(f"SHOW COLUMNS FROM {vsenabled_table}")
                vsenabled_columns = [col['Field'] for col in cursor.fetchall()]
                print(f"{vsenabled_table} columns: {', '.join(vsenabled_columns)}")
                
                # Find vs_id-like column
                vs_cols = [col for col in vsenabled_columns if 'vs' in col.lower() and ('id' in col.lower() or 'key' in col.lower())]
                if vs_cols:
                    vs_id_col = vs_cols[0]
                else:
                    vs_id_col = vsenabled_columns[0]
                print(f"Using {vs_id_col} as VS ID column")
                
                # Find ip_id-like column
                ip_cols = [col for col in vsenabled_columns if 'ip' in col.lower() and ('id' in col.lower() or 'key' in col.lower())]
                if ip_cols:
                    ip_id_col = ip_cols[0]
                else:
                    ip_id_col = vsenabled_columns[1] if len(vsenabled_columns) > 1 else None
                
                if not ip_id_col:
                    vsenabled_exists = False
                    print(f"Couldn't identify IP ID column in {vsenabled_table}. Skipping IP lookup.")
                else:
                    print(f"Using {ip_id_col} as IP ID column")
            else:
                print("No suitable VS IP association tables found. Skipping IP lookup.")
    except Exception as e:
        error_log(f"Error checking VSEnabledIPs table: {str(e)}")
        print(f"Error checking VSEnabledIPs table: {e}")
        vsenabled_exists = False
    
    # Check for VSPorts table or alternatives
    vsports_exists = False
    vsports_table = None
    vs_id_col_ports = None
    port_name_col = None
    
    try:
        cursor.execute("SHOW TABLES LIKE 'VSPorts'")
        if cursor.fetchone():
            vsports_exists = True
            vsports_table = "VSPorts"
            vs_id_col_ports = "vs_id"
            port_name_col = "port_name"
            print("Found VSPorts table")
        else:
            # Look for alternative tables
            cursor.execute("SHOW TABLES LIKE '%VS%Port%'")
            alt_tables = [row[0] for row in cursor.fetchall()]
            
            if alt_tables:
                print(f"Found alternative port tables: {', '.join(alt_tables)}")
                vsports_exists = True
                vsports_table = alt_tables[0]
                
                # Get columns for this table
                cursor.execute(f"SHOW COLUMNS FROM {vsports_table}")
                vsports_columns = [col['Field'] for col in cursor.fetchall()]
                print(f"{vsports_table} columns: {', '.join(vsports_columns)}")
                
                # Find vs_id-like column
                vs_cols = [col for col in vsports_columns if 'vs' in col.lower() and ('id' in col.lower() or 'key' in col.lower())]
                if vs_cols:
                    vs_id_col_ports = vs_cols[0]
                else:
                    vs_id_col_ports = vsports_columns[0]
                print(f"Using {vs_id_col_ports} as VS ID column for ports")
                
                # Find port_name-like column
                port_cols = [col for col in vsports_columns if 'port' in col.lower() and 'name' in col.lower()]
                if port_cols:
                    port_name_col = port_cols[0]
                else:
                    port_name_col = vsports_columns[1] if len(vsports_columns) > 1 else None
                
                if not port_name_col:
                    vsports_exists = False
                    print(f"Couldn't identify port name column in {vsports_table}. Will use default port (80).")
                else:
                    print(f"Using {port_name_col} as port name column")
            else:
                print("No suitable VS port tables found. Will use default port (80).")
    except Exception as e:
        error_log(f"Error checking VSPorts table: {str(e)}")
        print(f"Error checking VSPorts table: {e}")
        vsports_exists = False
    
    service_count = 0
    
    for vs_row in vs_data:
        vs_id = vs_row[primary_key]
        vs_name = vs_row[name_col] or f"Service-{vs_id}"
        vs_description = vs_row[description_col] if description_col and description_col in vs_row else ""
        
        # Get the enabled IPs for this VS if available
        vs_ips = []
        if vsenabled_exists:
            try:
                ip_query = f"""
                    SELECT IP.ip, IP.name, OBJ.name, OBJ.objtype_id 
                    FROM {vsenabled_table} VS
                    JOIN IPv4Address IP ON VS.{ip_id_col} = IP.id
                    LEFT JOIN IPv4Allocation ALLOC ON IP.ip = ALLOC.ip
                    LEFT JOIN Object OBJ ON ALLOC.object_id = OBJ.id
                    WHERE VS.{vs_id_col} = %s
                """
                cursor.execute(ip_query, (vs_id,))
                vs_ips = cursor.fetchall()
                print(f"Found {len(vs_ips)} IP associations for VS {vs_id} ({vs_name})")
            except Exception as e:
                error_log(f"Error getting IPs for VS {vs_id}: {str(e)}")
                print(f"Error getting IPs for VS {vs_id}: {e}")
        
        # Get the enabled ports for this VS if available
        port_numbers = []
        if vsports_exists:
            try:
                port_query = f"""
                    SELECT {port_name_col}
                    FROM {vsports_table}
                    WHERE {vs_id_col_ports} = %s
                """
                cursor.execute(port_query, (vs_id,))
                for port_row in cursor.fetchall():
                    port_name = port_row[0]
                    try:
                        port_number = int(port_name)
                        port_numbers.append(port_number)
                    except (ValueError, TypeError):
                        # Try harder to find a port number
                        if isinstance(port_name, str):
                            # Extract numbers from string
                            import re
                            matches = re.findall(r'\d+', port_name)
                            if matches:
                                port_numbers.append(int(matches[0]))
            except Exception as e:
                error_log(f"Error getting ports for VS {vs_id}: {str(e)}")
                print(f"Error getting ports for VS {vs_id}: {e}")
        
        if not port_numbers:
            # Default port if none specified
            port_numbers = [80]
        
        # Default protocol to TCP if we don't have specific info
        protocol = "tcp"
        
        # Create a service for each associated device or VM
        if vs_ips:
            for ip_row in vs_ips:
                ip = ip_row[0]
                ip_name = ip_row[1]
                obj_name = ip_row[2]
                objtype_id = ip_row[3]
                
                if not obj_name:
                    continue
                    
                obj_name = obj_name.strip()
                
                # Skip if site filtering is enabled and device is not in target site
                if TARGET_SITE and obj_name not in site_device_names:
                    continue
                
                # Determine if this is a VM or a device
                is_vm = (objtype_id == 1504)  # VM objtype_id
                
                # Create a unique service name including IP info
                service_name = f"{vs_name}-{ip_name}" if ip_name else vs_name
                
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
                                description=vs_description[:200] if vs_description else "",
                                custom_fields={
                                    "VS_Enabled": True,
                                    "VS_Type": "Virtual Service",
                                    "VS_Protocol": protocol
                                }
                            )
                            service_count += 1
                            print(f"Created service {service_name} for VM {obj_name}")
                    else:
                        device = netbox.dcim.get_devices(name=obj_name)
                        if device:
                            service = netbox.ipam.create_service(
                                device=obj_name,
                                name=service_name,
                                ports=port_numbers,
                                protocol=protocol,
                                description=vs_description[:200] if vs_description else "",
                                custom_fields={
                                    "VS_Enabled": True,
                                    "VS_Type": "Virtual Service",
                                    "VS_Protocol": protocol
                                }
                            )
                            service_count += 1
                            print(f"Created service {service_name} for device {obj_name}")
                except Exception as e:
                    error_log(f"Error creating service {service_name}: {str(e)}")
        else:
            # If no IPs found, create a service with the VS name only
            print(f"No IP associations found for VS {vs_id} ({vs_name}). Skipping service creation.")
    
    print(f"Virtual services migration completed. Created {service_count} services.")

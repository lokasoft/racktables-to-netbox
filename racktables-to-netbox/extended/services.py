"""
Virtual services migration functions
"""
from racktables_netbox_migration.utils import error_log
from racktables_netbox_migration.config import TARGET_SITE

def migrate_virtual_services(cursor, netbox):
    """
    Migrate virtual services data from Racktables to NetBox
    
    Args:
        cursor: Database cursor for Racktables
        netbox: NetBox client instance
    """
    print("\nMigrating virtual services...")
    
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
    
    # Get VS data from Racktables
    cursor.execute("SELECT vs_id, name, description FROM VS")
    
    service_count = 0
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
            
            # Skip if site filtering is enabled and device is not in target site
            if TARGET_SITE and obj_name not in site_device_names:
                continue
            
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
                            description=description[:200] if description else "",
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
    
    print(f"Virtual services migration completed. Created {service_count} services.")

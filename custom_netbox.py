"""
This module extends the pynetbox library with custom methods needed for the migration.
It wraps the pynetbox client to provide a compatible interface with the original code.
"""

import pynetbox


class NetBoxWrapper:
    """
    Wrapper class that provides compatibility with the original python-netbox library
    by adapting the pynetbox interface to match the expected methods and structure.
    """
    
    def __init__(self, host, port=None, use_ssl=True, auth_token=None):
        """Initialize the NetBox API client with the given parameters"""
        url = f"{'https' if use_ssl else 'http'}://{host}"
        if port:
            url = f"{url}:{port}"
            
        self.nb = pynetbox.api(url, token=auth_token)
        
        # Create API endpoints that match the original library structure
        self.dcim = DcimWrapper(self.nb)
        self.ipam = IpamWrapper(self.nb)
        self.virtualization = VirtualizationWrapper(self.nb)
        self.extras = ExtrasWrapper(self.nb)


class DcimWrapper:
    """Wrapper for DCIM endpoints"""
    
    def __init__(self, nb):
        self.nb = nb
        
    def get_sites(self, **kwargs):
        """Get sites with optional filters"""
        return self.nb.dcim.sites.filter(**kwargs)
    
    def create_site(self, name, slug, **kwargs):
        """Create a new site"""
        return self.nb.dcim.sites.create(name=name, slug=slug, **kwargs)
    
    def get_devices(self, **kwargs):
        """Get devices with optional filters"""
        return self.nb.dcim.devices.filter(**kwargs)
    
    def create_device(self, name, device_type, device_role, site_name, **kwargs):
        """Create a new device"""
        # Handle nested attributes
        if 'manufacturer' in kwargs and isinstance(kwargs['manufacturer'], dict):
            kwargs['manufacturer'] = kwargs['manufacturer']['name']
            
        if 'rack' in kwargs and isinstance(kwargs['rack'], dict):
            kwargs['rack'] = kwargs['rack']['name']
            
        if 'cluster' in kwargs and isinstance(kwargs['cluster'], dict):
            kwargs['cluster'] = kwargs['cluster']['name']
            
        # Get site ID from name if needed
        site = self.nb.dcim.sites.get(name=site_name)
        
        # Get device role and type if they're strings
        if isinstance(device_role, str):
            device_role = self.nb.dcim.device_roles.get(name=device_role)
        
        if isinstance(device_type, str):
            device_type = self.nb.dcim.device_types.get(model=device_type)
            
        return self.nb.dcim.devices.create(
            name=name,
            device_type=device_type.id if hasattr(device_type, 'id') else device_type,
            device_role=device_role.id if hasattr(device_role, 'id') else device_role,
            site=site.id if site else site_name,
            **kwargs
        )
    
    def create_device_role(self, name, color, slug, **kwargs):
        """Create a new device role"""
        return self.nb.dcim.device_roles.create(name=name, color=color, slug=slug, **kwargs)
        
    def get_device_roles(self, **kwargs):
        """Get device roles with optional filters"""
        return self.nb.dcim.device_roles.filter(**kwargs)
    
    def create_manufacturer(self, name, slug, **kwargs):
        """Create a new manufacturer"""
        return self.nb.dcim.manufacturers.create(name=name, slug=slug, **kwargs)
        
    def get_manufacturers(self, **kwargs):
        """Get manufacturers with optional filters"""
        return self.nb.dcim.manufacturers.filter(**kwargs)
    
    def create_device_type(self, model, manufacturer, slug, **kwargs):
        """Create a new device type"""
        # Handle manufacturer if it's a dict
        if isinstance(manufacturer, dict):
            manufacturer = self.nb.dcim.manufacturers.get(name=manufacturer['name'])
            
        return self.nb.dcim.device_types.create(
            model=model,
            manufacturer=manufacturer.id if hasattr(manufacturer, 'id') else manufacturer,
            slug=slug,
            **kwargs
        )
        
    def get_device_types(self, **kwargs):
        """Get device types with optional filters"""
        return self.nb.dcim.device_types.filter(**kwargs)
    
    def create_interface(self, name, device_id, interface_type, **kwargs):
        """Create a new interface"""
        return self.nb.dcim.interfaces.create(
            name=name,
            device=device_id,
            type=interface_type,
            **kwargs
        )
        
    def get_interfaces(self, **kwargs):
        """Get interfaces with optional filters"""
        return self.nb.dcim.interfaces.filter(**kwargs)
    
    def get_interfaces_custom(self, limit, offset, **kwargs):
        """Get interfaces with pagination"""
        return self.nb.dcim.interfaces.filter(limit=limit, offset=offset, **kwargs)
    
    def create_interface_connection(self, termination_a_id, termination_b_id, termination_a_type, termination_b_type, **kwargs):
        """Create a new cable connection between interfaces"""
        data = {
            "termination_a_type": termination_a_type,
            "termination_a_id": termination_a_id,
            "termination_b_type": termination_b_type,
            "termination_b_id": termination_b_id
        }
        return self.nb.dcim.cables.create(**data, **kwargs)
    
    def create_device_bay(self, name, device_id, installed_device_id=None, **kwargs):
        """Create a new device bay"""
        data = {
            "name": name,
            "device": device_id
        }
        if installed_device_id:
            data["installed_device"] = installed_device_id
            
        return self.nb.dcim.device_bays.create(**data, **kwargs)
    
    def get_device_bays(self, **kwargs):
        """Get device bays with optional filters"""
        return self.nb.dcim.device_bays.filter(**kwargs)
    
    def create_rack(self, name, site_name, **kwargs):
        """Create a new rack"""
        # Get site ID from name
        site = self.nb.dcim.sites.get(name=site_name)
        
        return self.nb.dcim.racks.create(
            name=name,
            site=site.id if site else site_name,
            **kwargs
        )
        
    def create_reservation(self, rack_num, units, description, user, **kwargs):
        """Create a rack reservation"""
        return self.nb.dcim.rack_reservations.create(
            rack=rack_num,
            units=units,
            description=description,
            user=user,
            **kwargs
        )
        
    def create_cable(self, termination_a_id, termination_b_id, termination_a_type, termination_b_type, **kwargs):
        """Create a new cable"""
        data = {
            "termination_a_type": termination_a_type,
            "termination_a_id": termination_a_id,
            "termination_b_type": termination_b_type,
            "termination_b_id": termination_b_id
        }
        return self.nb.dcim.cables.create(**data, **kwargs)
        
    def get_cables(self, **kwargs):
        """Get cables with optional filters"""
        return self.nb.dcim.cables.filter(**kwargs)


class IpamWrapper:
    """Wrapper for IPAM endpoints"""
    
    def __init__(self, nb):
        self.nb = nb
        
    def create_vlan_group(self, name, slug, **kwargs):
        """Create a new VLAN group"""
        return self.nb.ipam.vlan_groups.create(name=name, slug=slug, **kwargs)
        
    def get_vlan_groups(self, **kwargs):
        """Get VLAN groups with optional filters"""
        return self.nb.ipam.vlan_groups.filter(**kwargs)
    
    def create_vlan(self, vid, vlan_name, **kwargs):
        """Create a new VLAN"""
        # Handle group if it's a dict
        if 'group' in kwargs and isinstance(kwargs['group'], dict):
            group = self.nb.ipam.vlan_groups.get(name=kwargs['group']['name'])
            kwargs['group'] = group.id if group else None
            
        return self.nb.ipam.vlans.create(vid=vid, name=vlan_name, **kwargs)
        
    def create_ip_prefix(self, prefix, **kwargs):
        """Create a new IP prefix"""
        # Handle VLAN if it's a dict
        if 'vlan' in kwargs and isinstance(kwargs['vlan'], dict) and kwargs['vlan'] is not None:
            vlan = self.nb.ipam.vlans.get(id=kwargs['vlan']['id'])
            kwargs['vlan'] = vlan.id if vlan else None
            
        return self.nb.ipam.prefixes.create(prefix=prefix, **kwargs)
        
    def get_ip_prefixes(self, **kwargs):
        """Get IP prefixes with optional filters"""
        if 'tag' in kwargs:
            return self.nb.ipam.prefixes.filter(tag=kwargs['tag'])
        return self.nb.ipam.prefixes.filter(**kwargs)
    
    def create_ip_address(self, address, **kwargs):
        """Create a new IP address"""
        # Handle assigned object
        if 'assigned_object_id' in kwargs and 'assigned_object_type' in kwargs:
            kwargs['assigned_object'] = {
                'id': kwargs.pop('assigned_object_id'),
                'object_type': kwargs.pop('assigned_object_type')
            }
            
        # Handle device or VM in assigned object
        if 'assigned_object' in kwargs and isinstance(kwargs['assigned_object'], dict):
            if 'device' in kwargs['assigned_object'] and isinstance(kwargs['assigned_object']['device'], dict):
                device_name = kwargs['assigned_object']['device'].get('name', kwargs['assigned_object']['device'].get('id'))
                if device_name:
                    device = self.nb.dcim.devices.get(name=device_name)
                    if device:
                        kwargs['assigned_object']['device'] = device.id
                        
            if 'virtual_machine' in kwargs['assigned_object'] and isinstance(kwargs['assigned_object']['virtual_machine'], dict):
                vm_name = kwargs['assigned_object']['virtual_machine'].get('name', kwargs['assigned_object']['virtual_machine'].get('id'))
                if vm_name:
                    vm = self.nb.virtualization.virtual_machines.get(name=vm_name)
                    if vm:
                        kwargs['assigned_object']['virtual_machine'] = vm.id
        
        return self.nb.ipam.ip_addresses.create(address=address, **kwargs)
        
    def get_ip_addresses(self, **kwargs):
        """Get IP addresses with optional filters"""
        if 'tag' in kwargs:
            return self.nb.ipam.ip_addresses.filter(tag=kwargs['tag'])
        return self.nb.ipam.ip_addresses.filter(**kwargs)
        
    def create_service(self, device, name, ports, protocol, **kwargs):
        """Create a new service"""
        # Handle device if it's a string
        if isinstance(device, str):
            device = self.nb.dcim.devices.get(name=device)
            
        return self.nb.ipam.services.create(
            device=device.id if hasattr(device, 'id') else device,
            name=name,
            ports=ports,
            protocol=protocol,
            **kwargs
        )
        
    def get_services(self, **kwargs):
        """Get services with optional filters"""
        return self.nb.ipam.services.filter(**kwargs)


class VirtualizationWrapper:
    """Wrapper for Virtualization endpoints"""
    
    def __init__(self, nb):
        self.nb = nb
        
    def create_cluster_type(self, name, slug, **kwargs):
        """Create a new cluster type"""
        return self.nb.virtualization.cluster_types.create(name=name, slug=slug, **kwargs)
        
    def get_cluster_types(self, **kwargs):
        """Get cluster types with optional filters"""
        return self.nb.virtualization.cluster_types.filter(**kwargs)
    
    def create_cluster(self, name, cluster_type, **kwargs):
        """Create a new cluster"""
        # Get cluster type if it's a string
        if isinstance(cluster_type, str):
            cluster_type = self.nb.virtualization.cluster_types.get(name=cluster_type)
            
        return self.nb.virtualization.clusters.create(
            name=name,
            type=cluster_type.id if hasattr(cluster_type, 'id') else cluster_type,
            **kwargs
        )
        
    def get_clusters(self, **kwargs):
        """Get clusters with optional filters"""
        return self.nb.virtualization.clusters.filter(**kwargs)
    
    def create_virtual_machine(self, name, cluster_name, **kwargs):
        """Create a new virtual machine"""
        # Get cluster if it's a string
        cluster = self.nb.virtualization.clusters.get(name=cluster_name)
        
        return self.nb.virtualization.virtual_machines.create(
            name=name,
            cluster=cluster.id if cluster else cluster_name,
            **kwargs
        )
        
    def get_virtual_machines(self, **kwargs):
        """Get virtual machines with optional filters"""
        return self.nb.virtualization.virtual_machines.filter(**kwargs)
    
    def create_interface(self, name, virtual_machine, interface_type, **kwargs):
        """Create a new VM interface"""
        # Get VM if it's a string
        if isinstance(virtual_machine, str):
            virtual_machine = self.nb.virtualization.virtual_machines.get(name=virtual_machine)
            
        return self.nb.virtualization.interfaces.create(
            name=name,
            virtual_machine=virtual_machine.id if hasattr(virtual_machine, 'id') else virtual_machine,
            type=interface_type,
            **kwargs
        )
        
    def get_interfaces(self, **kwargs):
        """Get VM interfaces with optional filters"""
        return self.nb.virtualization.interfaces.filter(**kwargs)
        
    def create_service(self, virtual_machine, name, ports, protocol, **kwargs):
        """Create a new service for a VM"""
        # Handle VM if it's a string
        if isinstance(virtual_machine, str):
            virtual_machine = self.nb.virtualization.virtual_machines.get(name=virtual_machine)
            
        return self.nb.ipam.services.create(
            virtual_machine=virtual_machine.id if hasattr(virtual_machine, 'id') else virtual_machine,
            name=name,
            ports=ports,
            protocol=protocol,
            **kwargs
        )


class ExtrasWrapper:
    """Wrapper for Extras endpoints"""
    
    def __init__(self, nb):
        self.nb = nb
        
    def create_tag(self, name, slug, **kwargs):
        """Create a new tag"""
        return self.nb.extras.tags.create(name=name, slug=slug, **kwargs)
        
    def get_tags(self, **kwargs):
        """Get tags with optional filters"""
        return self.nb.extras.tags.filter(**kwargs)
        
    def create_custom_field(self, name, type, **kwargs):
        """Create a new custom field"""
        return self.nb.extras.custom_fields.create(name=name, type=type, **kwargs)
        
    def get_custom_fields(self, **kwargs):
        """Get custom fields with optional filters"""
        return self.nb.extras.custom_fields.filter(**kwargs)
        
    def create_export_template(self, name, content_type, template_code, **kwargs):
        """Create a new export template"""
        return self.nb.extras.export_templates.create(
            name=name,
            content_type=content_type,
            template_code=template_code,
            **kwargs
        )
        
    def create_object_change(self, changed_object_type, changed_object_id, action, **kwargs):
        """Create a record of an object change"""
        return self.nb.extras.object_changes.create(
            changed_object_type=changed_object_type,
            changed_object_id=changed_object_id,
            action=action,
            **kwargs
        )


# Create a replacement for the original NetBox class
ExtendedNetBox = NetBoxWrapper

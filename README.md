# Racktables to NetBox Migration Tool

Scripts to export Racktables data, accessible through a SQL connection, into a [Netbox](https://github.com/netbox-community/netbox/) instance. An easy way to test NetBox is with [netbox-docker](https://github.com/netbox-community/netbox-docker). 

Some benefits of NetBox are a strictly enforced naming and relationship hierarchy, custom scripts and reports, and an easy REST API with many wrappers.

## Migration Features

The `migrate.py` script will transfer:
- Racks at sites
- Device locations in racks and reservations
- All unracked stuff, notably VMs and clusters
- Parent-child relationships like servers in chassises, patch panels in patch panels
- IPs, networks, VLANs
- Interfaces and their associated IP. Note that if an "OS interface" in "IP addresses" is same as "local name" in "ports and links," the interface is not duplicated
- Connections between interfaces (from the 'ports and links' category)
- Tags, labels, asset numbers

## Installation

### Requirements
- Python 3.6+
- Access to Racktables SQL database
- NetBox instance with API access
- Python packages: `python-netbox`, `python-slugify`, `pymysql`

### Setup

1. Clone this repository
2. Install requirements:
   ```
   pip install -r requirements.txt
   ```
3. Configure your database and NetBox settings in `migrate.py`
4. Import the custom fields into NetBox using the `custom_fields.yml` file
5. Set `MAX_PAGE_SIZE=0` in your NetBox's `env/netbox.env` configuration

## Usage

### Main Migration

Run the migration using the wrapper script, which handles all the necessary library extensions:

```
python migrate_wrapper.py
```

The wrapper script automatically extends the NetBox library with the required methods without modifying the library files directly.

### Migration Options

You can control which parts of the migration process are executed by modifying the boolean flags at the top of `migrate.py`:

```python
CREATE_VLAN_GROUPS =           True
CREATE_VLANS =                 True
CREATE_MOUNTED_VMS =           True
CREATE_UNMOUNTED_VMS =         True
CREATE_RACKED_DEVICES =        True
CREATE_NON_RACKED_DEVICES =    True
CREATE_INTERFACES =            True
CREATE_INTERFACE_CONNECTIONS = True
CREATE_IPV4 =                  True
CREATE_IPV6 =                  True
CREATE_IP_NETWORKS =           True
CREATE_IP_ALLOCATED =          True
CREATE_IP_NOT_ALLOCATED =      True
```

### Additional Utilities

- **vm.py**: Update uniquely named VMs in NetBox with memory, disk and CPU data from RHEVM instances.
- **free.py**: List the number of free IP addresses in NetBox based on the tags on prefixes.

## Files

**migrate.py**  
The main migration script. Meant to be run once without interruption, although boolean flags exist to skip steps.
Steps that depend on others create cached data on disk, but the best procedure is to fully run once on an empty NetBox instance.

**custom_netbox.py**  
Extends the python-netbox library with the necessary methods for migration.

**migrate_wrapper.py**  
Wrapper script that runs the migration with the extended NetBox functionality.

**custom_fields.yml**  
The file to supply to the NetBox instance for custom fields. These fields are expected by the migrate script and must be there.

**vm.py**  
Update the uniquely named VMs in NetBox with memory, disk and CPU data from RHEVM instances. Since two VMs can be in separate clusters with the same name and there is no mapping between RT cluster names and RHEVM cluster names, any non-uniquely named VM is ignored.

**free.py**  
List the number of free IP addresses in NetBox based on the tags on prefixes.

## Troubleshooting

- Ensure all dependencies are installed
- Make sure custom fields are properly configured in NetBox
- Check database connection parameters
- Verify NetBox API token permissions
- Look for errors in the generated error log file

## License

Apache License 2.0

# Racktables to NetBox Migration Tool

A modular Python package for migrating data from Racktables to NetBox.

## Features

- Comprehensive migration of Racktables data to NetBox
- Modular architecture for maintainability and extensibility
- Site filtering to restrict migration to specific sites
- Automatic detection and creation of available IP subnets
- Support for extended data migration (files, services, NAT, etc.)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/racktables-netbox-migration.git
cd racktables-netbox-migration

# Install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Edit the configuration in `racktables_netbox_migration/config.py`:

```python
# NetBox API connection settings
NB_HOST = 'your-netbox-host'
NB_PORT = 8000
NB_TOKEN = 'your-api-token'

# Database connection parameters
DB_CONFIG = {
    'host': 'your-racktables-db-host',
    'port': 3306,
    'user': 'your-db-username',
    'password': 'your-db-password',
    'db': 'racktables-db-name',
}
```

## Usage

### Basic Migration

```bash
# Run setup to create custom fields
python set_custom_fields.py

# Run the migration
python migrate_wrapper.py
```

### Filtering by Site

```bash
# Migrate data for a specific site only
python migrate_wrapper.py --site "YourSiteName"
```

### Migration Components

You can control which components to migrate by editing the migration flags in `config.py`:

```python
CREATE_VLAN_GROUPS = True
CREATE_VLANS = True
CREATE_MOUNTED_VMS = True
# ... and so on
```

## Project Structure

```
racktables_netbox_migration/
├── __init__.py             # Package initialization
├── config.py               # Global configuration settings
├── utils.py                # Utility functions
├── db.py                   # Database connection and query helpers
├── sites.py                # Site and rack related functions
├── devices.py              # Device creation and management
├── interfaces.py           # Interface creation and management
├── ips.py                  # IP and network related functions
├── vlans.py                # VLAN management functions
├── vms.py                  # Virtual machine handling
├── extended/               # Extended functionality modules
│   ├── __init__.py
│   ├── available_subnets.py  # Available subnet detection
│   ├── patch_cables.py     # Patch cable migration
│   ├── files.py            # File attachment migration
│   ├── services.py         # Virtual services migration
│   ├── nat.py              # NAT mappings
│   ├── load_balancer.py    # Load balancing data
│   └── monitoring.py       # Monitoring data
```

## Entry Points

- `migrate.py` - Main migration script
- `extended_migrate.py` - Extended migration components
- `migrate_wrapper.py` - Wrapper with command-line interface

## Key Features

### Site Filtering

Restrict migration to a specific site:

```bash
python migrate_wrapper.py --site "DataCenter1"
```

### Available Subnet Detection

The tool automatically:
1. Identifies gaps in IP address space
2. Creates available prefixes in those gaps
3. Tags them with "Available" status for easy filtering

### Prefix Description Formatting

Prefixes include formatted descriptions with:
- Network name
- Tags in square brackets
- Comments

Example: `Customer Network [production, external] - Primary customer connection`

## Troubleshooting

- Check the `errors` log file for detailed error messages
- Ensure MAX_PAGE_SIZE=0 is set in your NetBox configuration
- Verify database connectivity and permissions
- Make sure custom fields are properly created

## License

GNU General Public License v3.0

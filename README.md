# Racktables to NetBox Migration Tool

A modular Python package for migrating data from Racktables to NetBox. This tool provides comprehensive migration of network infrastructure data with extended features for a complete data transfer experience.

## Features

- **Comprehensive Migration**: Transfer all your Racktables data to NetBox
- **Modular Architecture**: Maintainable and extensible codebase for easier updates
- **Site Filtering**: Restrict migration to specific sites when needed
- **Tenant Filtering**: Restrict migration to specific tenants and associate objects with tenants
- **Component Selection**: Choose which components to migrate with flexible flags
- **Custom Fields**: Automatic setup of required custom fields in NetBox
- **Extended Data Support**:
  - Available subnet detection and creation
  - Patch cable connections
  - File attachments
  - Virtual services
  - NAT mappings
  - Load balancer configurations
  - Monitoring data references
  - IP ranges

## Prerequisites

Before starting, ensure you have:

1. Python 3.6 or higher installed
2. Access to your Racktables MySQL/MariaDB database
3. A running NetBox instance (version 4.2.6 or higher) with API access
4. Administrative privileges on the NetBox instance to add custom fields

## Installation

### Automated Setup (Recommended)

The tool includes a setup script that automates the installation process:

```bash
# Clone the repository
git clone https://github.com/enoch85/racktables-to-netbox.git
cd racktables-to-netbox

# Make the setup script executable
chmod +x setup_dev.sh

# Run automated setup
./setup_dev.sh
```

The `setup_dev.sh` script has several options:

- `--netbox`: Sets up a complete NetBox Docker environment with proper configuration
- `--gitclone`: Configures minimal requirements after a git clone (default if no options specified)
- `--package`: Sets up for package distribution
- `--help`: Displays help message

For a complete setup with NetBox included:

```bash
./setup_dev.sh --netbox
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/enoch85/racktables-to-netbox.git
cd racktables-to-netbox

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Edit the configuration in `migration/config.py`:

```python
# NetBox API connection settings - can be overridden with environment variables
NB_HOST = os.environ.get('NETBOX_HOST', 'localhost')
NB_PORT = int(os.environ.get('NETBOX_PORT', '8000'))
NB_TOKEN = os.environ.get('NETBOX_TOKEN', 'your-api-token')
NB_USE_SSL = os.environ.get('NETBOX_USE_SSL', 'False').lower() in ('true', '1', 'yes')

# Database connection parameters - can be overridden with environment variables
DB_CONFIG = {
    'host': os.environ.get('RACKTABLES_DB_HOST', 'your-racktables-db-host'),
    'port': int(os.environ.get('RACKTABLES_DB_PORT', '3306')),
    'user': os.environ.get('RACKTABLES_DB_USER', 'your-db-username'),
    'password': os.environ.get('RACKTABLES_DB_PASSWORD', 'your-db-password'),
    'db': os.environ.get('RACKTABLES_DB_NAME', 'racktables-db-name'),
    'charset': 'utf8mb4',
    'cursorclass': DictCursor
}

# Migration flags - control which components are processed
CREATE_VLAN_GROUPS = True
CREATE_VLANS = True
# ... additional flags
```

Alternatively, you can use environment variables:

```bash
# NetBox connection
export NETBOX_HOST=localhost
export NETBOX_PORT=8000
export NETBOX_TOKEN=your-api-token
export NETBOX_USE_SSL=False

# Database connection
export RACKTABLES_DB_HOST=your-racktables-db-host
export RACKTABLES_DB_PORT=3306
export RACKTABLES_DB_USER=your-db-username
export RACKTABLES_DB_PASSWORD=your-db-password
export RACKTABLES_DB_NAME=racktables-db-name
```

### Important: Configure NetBox MAX_PAGE_SIZE

This setting is required for the migration tool to properly fetch all objects in a single request:

```bash
# Make the script executable
chmod +x scripts/max-page-size-check.sh

# Edit the script to set your NetBox Docker path
nano scripts/max-page-size-check.sh

# Run the script
./scripts/max-page-size-check.sh
```

## Usage

### Basic Migration

```bash
# Run setup to create custom fields (only needed once)
python migration/set_custom_fields.py

# Run the migration
python migration/migrate.py
```

### Advanced Options

```bash
# Migrate data for a specific site only
python migration/migrate.py --site "YourSiteName"

# Migrate data with a specific tenant
python migration/migrate.py --tenant "YourTenantName"

# Migrate data for a specific site and tenant
python migration/migrate.py --site "YourSiteName" --tenant "YourTenantName"

# Run only basic migration (no extended components)
python migration/migrate.py --basic-only

# Run only extended migration components
python migration/migrate.py --extended-only

# Skip setting up custom fields
python migration/migrate.py --skip-custom-fields

# Use custom configuration file
python migration/migrate.py --config your_config.py
```

## Project Structure

```
racktables-to-netbox/
├── migration/              # Main migration package
│   ├── __init__.py         # Package initialization
│   ├── config.py           # Global configuration settings
│   ├── custom_netbox.py    # Compatibility wrapper for pynetbox
│   ├── db.py               # Database connection and query helpers
│   ├── devices.py          # Device creation and management
│   ├── interfaces.py       # Interface creation and management
│   ├── ips.py              # IP and network related functions
│   ├── migrate.py          # Main migration script
│   ├── set_custom_fields.py # Custom fields setup
│   ├── sites.py            # Site and rack related functions
│   ├── utils.py            # Utility functions
│   ├── vlans.py            # VLAN management functions
│   ├── vms.py              # Virtual machine handling
│   ├── extended/           # Extended functionality modules
│       ├── __init__.py
│       ├── available_subnets.py  # Available subnet detection
│       ├── files.py        # File attachment migration
│       ├── ip_ranges.py    # IP range generation
│       ├── load_balancer.py # Load balancing data
│       ├── monitoring.py   # Monitoring data
│       ├── nat.py          # NAT mappings
│       ├── patch_cables.py # Patch cable migration
│       └── services.py     # Virtual services migration
├── scripts/                # Helper scripts
├── setup_dev.sh            # Development environment setup
├── requirements.txt        # Python dependencies
└── setup.py                # Package setup script
```

## Key Features

### Site and Tenant Filtering

Restrict migration to a specific site and/or tenant:

```bash
python migration/migrate.py --site "DataCenter1" --tenant "CustomerA"
```

This will:
1. Only migrate objects associated with the specified site
2. Associate all created objects with the specified tenant
3. Create the tenant if it doesn't exist in NetBox

### Available Subnet Detection

The tool automatically:
1. Identifies gaps in IP address space
2. Creates available prefixes in those gaps
3. Tags them with "Available" status for easy filtering

### IP Range Generation

The tool can create IP ranges based on:
1. Available subnets that it detects
2. Gaps between allocated IP addresses
3. Empty prefixes with no allocated IPs

### Extended Data Migration

1. **Patch Cables**: Migrates physical cable connections between devices
2. **Files**: Transfers file attachments from Racktables
3. **Virtual Services**: Migrates service configurations
4. **NAT**: Preserves Network Address Translation relationships
5. **Load Balancing**: Migrates load balancer configs
6. **Monitoring**: Transfers monitoring system references

## Troubleshooting

- Check the `errors` log file for detailed error messages
- Ensure MAX_PAGE_SIZE=0 is set in your NetBox configuration
- Verify database connectivity and permissions
- Make sure custom fields are properly created

### Common Issues

1. **Database Connection Issues**
   - Verify credentials in `config.py`
   - Check network connectivity to database server
   - Ensure database port is accessible

2. **NetBox API Connection Issues**
   - Verify API token has appropriate permissions
   - Check network connectivity to NetBox server
   - Confirm API is enabled in NetBox settings

3. **Memory or Performance Issues**
   - Try running parts of the migration by adjusting flags in `config.py`
   - Increase Python process memory limit
   - Consider filtering by site with the `--site` parameter

## License

GNU General Public License v3.0

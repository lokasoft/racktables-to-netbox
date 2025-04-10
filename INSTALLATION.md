# Installation and Setup Guide

This guide covers the detailed installation and setup process for the Racktables to NetBox migration tool.

## Prerequisites

Before starting, ensure you have:

1. Python 3.6 or higher installed
2. Access to your Racktables MySQL/MariaDB database
3. A running NetBox instance (version 4.2.6 or higher) with API access
4. Administrative privileges on the NetBox instance to add custom fields

## Automated Setup (Recommended)

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

This will:
1. Set up a virtual environment
2. Install all dependencies
3. Create a NetBox Docker installation with proper configuration
4. Generate secure credentials
5. Configure NetBox with MAX_PAGE_SIZE set to 0
6. Create symlinks for development
7. Save configuration for easy use

## Quick Manual Installation

```bash
# Clone the repository
git clone https://github.com/enoch85/racktables-to-netbox.git
cd racktables-to-netbox

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure connection settings in migration/config.py or use environment variables
# (See Configuration section below)

# Run the migration
python migrate.py --site "YourSiteName"  # Optional site filtering
```

## Detailed Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/enoch85/racktables-to-netbox.git
cd racktables-to-netbox
```

### 2. Set Up a Python Environment

Modern Python distributions like Ubuntu 24.04 use externally managed environments (PEP 668) which prevent installing packages directly with pip. You have two options:

#### Option A: Use a Virtual Environment (Recommended)

```bash
# Make sure you have the required packages
sudo apt install python3-full python3-venv

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

#### Option B: Use pipx

If you prefer to use pipx (which manages isolated environments for applications):

```bash
# Install pipx if not already installed
sudo apt install pipx
pipx ensurepath

# Create a directory for the tool to operate in
mkdir -p ~/.local/pipx/venvs/racktables-netbox
cd ~/.local/pipx/venvs/racktables-netbox

# Clone the repository here
git clone https://github.com/enoch85/racktables-to-netbox.git .

# Install dependencies in this isolated environment
pipx run --pip-args="-r requirements.txt" python -c ""
```

### 3. Install Dependencies

With your virtual environment activated (if using Option A):

```bash
pip install -r requirements.txt
```

### 4. Configure NetBox MAX_PAGE_SIZE Setting

This setting is required for the migration tool to properly fetch all objects in a single request.

```bash
# First, edit the script to set your NetBox Docker path
nano scripts/max-page-size-check.sh

# Make the script executable
chmod +x scripts/max-page-size-check.sh

# Run the script
./scripts/max-page-size-check.sh
```

This will check if the MAX_PAGE_SIZE is already set to 0 and offer to update it if needed.

### 5. Configure Database and API Connection

Edit `migration/config.py` to set your connection parameters:

```python
# NetBox API connection settings
NB_HOST = 'localhost'
NB_PORT = 8000
NB_TOKEN = '0123456789abcdef0123456789abcdef01234567'
NB_USE_SSL = False

# Database connection parameters
DB_CONFIG = {
    'host': '10.248.48.4',
    'port': 3306,
    'user': 'root',
    'password': 'secure-password',
    'db': 'test1',
    'charset': 'utf8mb4',
    'cursorclass': DictCursor
}
```

Alternatively, you can use environment variables:

```bash
# NetBox connection
export NETBOX_HOST=localhost
export NETBOX_PORT=8000
export NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
export NETBOX_USE_SSL=False

# Database connection
export RACKTABLES_DB_HOST=10.248.48.4
export RACKTABLES_DB_PORT=3306
export RACKTABLES_DB_USER=root
export RACKTABLES_DB_PASSWORD=secure-password
export RACKTABLES_DB_NAME=test1
```

### 6. Run the Migration

Basic usage with a specific site:
```bash
python migrate.py --site "YourSiteName"
```

Other migration options:
```bash
# Run only basic migration (no extended components)
python migrate.py --basic-only

# Run only extended migration components
python migrate.py --extended-only

# Skip setting up custom fields
python migrate.py --skip-custom-fields

# Use custom configuration file
python migrate.py --config your_config.py
```

## Package Installation (Optional)

Only necessary if you want the tool available system-wide:

```bash
# Install in development mode (editable)
pip install -e .

# Or install normally
pip install .

# Then run using the command
migrate-racktables --site "YourSiteName"
```

## Troubleshooting

### Common Issues

1. **Database Connection Issues**
   
   If you encounter database connection problems, check:
   - Database credentials in `config.py`
   - Network connectivity to the database server
   - Database server is running and accessible
   - Firewall rules allowing connections to the database port
   
   Try connecting with a MySQL client to verify credentials.

2. **NetBox API Connection Issues**
   
   If you have problems connecting to NetBox:
   - Verify the API token is valid and has appropriate permissions
   - Check network connectivity to the NetBox server
   - Ensure the API is enabled in NetBox settings
   - Confirm your NetBox version is 4.2.6 or higher
   
   Test with a simple API call:
   ```bash
   curl -H "Authorization: Token YOUR_TOKEN" http://your-netbox-host:port/api/
   ```

3. **Memory or Performance Issues**
   
   If the script runs out of memory or is too slow:
   - Try running parts of the migration by adjusting the boolean flags in `config.py`
   - Increase your Python process memory limit if possible
   - Run the script on a machine with more resources
   - Consider filtering by site with the `--site` parameter

## Post-Migration Verification

After migration completes, verify:

1. Device counts match between Racktables and NetBox
2. VLANs and IP prefixes are correctly defined
3. Interfaces are properly connected
4. IP addresses are correctly assigned
5. Parent-child relationships are maintained
6. Custom fields are populated with the right data

## Setup Script Details

The included `setup_dev.sh` script provides several useful features:

### Setting up NetBox (`--netbox`)

When run with the `--netbox` option, the script:
- Generates secure credentials for NetBox and PostgreSQL
- Clones the NetBox Docker repository
- Creates a Docker Compose override with proper settings
- Sets MAX_PAGE_SIZE=0 required for migration
- Creates admin user and API token
- Configures the migration tool to use the local NetBox

### Basic Setup (`--gitclone`)

This is the default mode and sets up:
- Python virtual environment
- Required dependencies
- Symlinks for development
- Package in development mode

### Packaging (`--package`) 

Sets up the environment for creating distributable packages:
- Builds Python package
- Creates necessary packaging files
- Prepares for distribution via PyPI

## Getting Help

If you encounter issues not covered in this guide:

1. Check the error logs in the `errors` file created during migration
2. Examine the NetBox logs for API-related issues
3. Run the migration with increased verbosity
4. Open an issue on the GitHub repository with details about your problem

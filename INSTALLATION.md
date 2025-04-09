# Installation and Setup Guide

This guide covers the detailed installation and setup process for the Racktables to NetBox migration tool.

## Prerequisites

Before starting, ensure you have:

1. Python 3.6 or higher installed
2. Access to your Racktables MySQL/MariaDB database
3. A running NetBox instance (version 4.2.6 or higher) with API access
4. Administrative privileges on the NetBox instance to add custom fields

## Installation Steps

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

If using a virtual environment (Option A):

```bash
pip install -r requirements.txt
```

If using pipx (Option B), the dependencies are already installed from the previous step.

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

### 5. Configure NetBox Custom Fields

The migration tool requires specific custom fields to be added to your NetBox instance. Use the provided script to automatically create all required fields:

```bash
# Edit the script to set your API token and URL
nano scripts/set_custom_fields.py

# Run the script
python scripts/set_custom_fields.py
```

Alternatively, you can add custom fields manually using NetBox's UI according to the definitions in `scripts/set_custom_fields.py`.

### 6. Configure Database and API Connection

Edit `config.py` to set your connection parameters:

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

### 7. Test Database Connection

Before running the full migration, test your database connection:

```python
import pymysql
from racktables_netbox_migration.config import DB_CONFIG

connection = pymysql.connect(**DB_CONFIG)
print("Connection successful!")
connection.close()
```

### 8. Run the Migration

Run the wrapper script to perform the migration:

If using a virtual environment:
```bash
python migrate_wrapper.py
```

If you want to restrict migration to a specific site:
```bash
python migrate_wrapper.py --site "YourSiteName"
```

After the base migration completes, run the extended migration for additional data:
```bash
python extended_migrate.py
```

## Troubleshooting

### Common Issues

1. **Externally Managed Environment Error**
   
   If you see an error like:
   ```
   error: externally-managed-environment
   This environment is externally managed
   ```
   
   This means you need to use a virtual environment or pipx as described in the installation steps.

2. **Database Connection Issues**
   
   If you encounter database connection problems, check:
   - Database credentials in `config.py`
   - Network connectivity to the database server
   - Database server is running and accessible
   - Firewall rules allowing connections to the database port
   
   Try connecting with a MySQL client to verify credentials.

3. **NetBox API Connection Issues**
   
   If you have problems connecting to NetBox:
   - Verify the API token is valid and has appropriate permissions
   - Check network connectivity to the NetBox server
   - Ensure the API is enabled in NetBox settings
   - Confirm your NetBox version is 4.2.6 or higher
   - Check if you can access the API in a browser or with curl
   
   Test with a simple API call:
   ```bash
   curl -H "Authorization: Token YOUR_TOKEN" http://your-netbox-host:port/api/
   ```

4. **Missing Custom Fields**
   
   If data isn't being correctly migrated because of missing custom fields:
   - Check if custom fields were properly added to NetBox
   - Verify field names match those expected in the script
   - Restart NetBox after adding custom fields
   - Check the output of the set_custom_fields.py script for errors
   - Verify permissions for the API token include custom field management

5. **Memory or Performance Issues**
   
   If the script runs out of memory or is too slow:
   - Try running parts of the migration by adjusting the boolean flags in `config.py`
   - Increase your Python process memory limit if possible
   - Run the script on a machine with more resources
   - Consider filtering by site with the `--site` parameter
   - Break the migration into smaller batches using the config flags

6. **Import Errors**
   
   If you see import errors:
   - Make sure you're running the scripts from the repository root directory
   - Verify the virtual environment is activated
   - Check that all dependencies are installed
   - Try reinstalling the package with `pip install -e .`

## Post-Migration Verification

After migration completes, verify:

1. Device counts match between Racktables and NetBox
2. VLANs and IP prefixes are correctly defined
3. Interfaces are properly connected
4. IP addresses are correctly assigned
5. Parent-child relationships are maintained
6. Custom fields are populated with the right data

To check for missing data, you can use the NetBox UI or API to browse the migrated data and compare with your Racktables instance.

For IP networks and addresses, you can use the provided scripts in the `scripts/` directory to analyze the migrated data.

## Additional Information

### Extending the Migration

If you need to customize the migration process:

1. Edit `config.py` to adjust migration flags for specific components
2. Create custom scripts based on the examples in the `scripts/` directory
3. Modify the core modules in `racktables_netbox_migration/` directory

### Getting Help

If you encounter issues not covered in this guide:

1. Check the error logs in the `errors` file created during migration
2. Examine the NetBox logs for API-related issues
3. Run the migration with increased verbosity
4. Open an issue on the GitHub repository with details about your problem

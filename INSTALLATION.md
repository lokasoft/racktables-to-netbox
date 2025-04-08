# Installation and Setup Guide

This guide covers the detailed installation and setup process for the Racktables to NetBox migration tool.

## Prerequisites

Before starting, ensure you have:

1. Python 3.6 or higher installed
2. Access to your Racktables MySQL/MariaDB database
3. A running NetBox instance with API access
4. Administrative privileges on the NetBox instance to add custom fields

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/username/racktables-to-netbox.git
cd racktables-to-netbox
```

### 2. Set Up a Virtual Environment (recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure NetBox Custom Fields

You need to add the custom fields to your NetBox instance. The included `custom_fields.yml` file contains all the necessary field definitions.

There are several ways to add these:

#### Option 1: Using NetBox's UI

Navigate to the NetBox admin interface and add each field manually according to the definitions in `custom_fields.yml`.

#### Option 2: Using NetBox's Configuration

If you're using NetBox with Docker or a similar setup:

1. Copy `custom_fields.yml` to your NetBox's configuration directory:
   ```
   cp custom_fields.yml /path/to/netbox/initializers/
   ```

2. Restart NetBox to apply the configuration:
   ```
   docker-compose restart netbox
   ```

### 5. Configure Database and API Connection

Edit `migrate.py` to set your connection parameters:

```python
# Racktables database settings
rt_host = '127.0.0.1'  # Your Racktables database host
rt_port = 3306         # Database port
rt_user = 'root'       # Database username
rt_db = 'test1'        # Database name

# NetBox API settings
nb_host = '10.248.48.4'  # Your NetBox host
nb_port = 8001           # NetBox API port
nb_token = '0123456789abcdef0123456789abcdef01234567'  # Your API token
```

### 6. Adjust NetBox Settings

Set `MAX_PAGE_SIZE=0` in your NetBox's `env/netbox.env` configuration file to allow retrieving all objects in a single request.

```
MAX_PAGE_SIZE=0
```

After making this change, restart your NetBox instance for the setting to take effect.

### 7. Test Database Connection

Before running the full migration, test your database connection:

```python
import pymysql
connection = pymysql.connect(
    host='your_host',
    port=3306,
    user='your_user',
    db='your_db'
)
print("Connection successful!")
connection.close()
```

### 8. Run the Migration

Run the wrapper script to perform the migration:

```bash
python migrate_wrapper.py
```

## Troubleshooting

### Common Issues

1. **Database Connection Issues**
   
   If you encounter database connection problems, check:
   - Database credentials in `migrate.py`
   - Network connectivity to the database server
   - Database server is running and accessible
   
   Try connecting with a MySQL client to verify credentials.

2. **NetBox API Connection Issues**
   
   If you have problems connecting to NetBox:
   - Verify the API token is valid
   - Check network connectivity to the NetBox server
   - Ensure the API is enabled in NetBox settings

3. **Missing Custom Fields**
   
   If data isn't being correctly migrated because of missing custom fields:
   - Check if custom fields were properly added to NetBox
   - Verify field names match those expected in the script
   - Restart NetBox after adding custom fields

4. **Memory or Performance Issues**
   
   If the script runs out of memory or is too slow:
   - Try running parts of the migration by adjusting the boolean flags
   - Increase your Python process memory limit if possible
   - Run the script on a machine with more resources

## Post-Migration Verification

After migration completes, verify:

1. Device counts match between Racktables and NetBox
2. VLANs and IP prefixes are correctly defined
3. Interfaces are properly connected
4. IP addresses are correctly assigned
5. Parent-child relationships are maintained

Use the NetBox UI to browse the migrated data and check for any anomalies.

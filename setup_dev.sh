#!/bin/bash
# Setup script for development environment with all components from scratch

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Sets up the development environment for Racktables to NetBox migration tool"
    echo ""
    echo "Options:"
    echo "  --netbox       Set up NetBox Docker environment with proper configuration"
    echo "  --gitclone     Setup minimal requirements after a git clone"
    echo "  --package      Set up for package distribution"
    echo "  --help         Display this help message"
    echo ""
    echo "Without options, runs standard development environment setup"
}

# Parse arguments
SETUP_NETBOX=false
SETUP_GITCLONE=false
SETUP_PACKAGE=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --netbox) SETUP_NETBOX=true ;;
        --gitclone) SETUP_GITCLONE=true ;;
        --package) SETUP_PACKAGE=true ;;
        --help) print_usage; exit 0 ;;
        *) echo "Unknown parameter: $1"; print_usage; exit 1 ;;
    esac
    shift
done

# If no options provided, run standard setup
if [[ "$SETUP_NETBOX" == "false" && "$SETUP_GITCLONE" == "false" && "$SETUP_PACKAGE" == "false" ]]; then
    echo "Running standard development setup..."
    SETUP_GITCLONE=true
fi

# Function to set up NetBox Docker
setup_netbox() {
    echo "Setting up NetBox environment..."
    
    # Generate secure credentials
    echo "Generating secure credentials..."
    SECRET_KEY=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c 64)
    API_TOKEN=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c 40)
    POSTGRES_PASSWORD="postgres123"
    
    # Check for required system packages
    echo "Checking for required system packages..."
    if ! command -v python3 &> /dev/null; then
        echo "Error: Python 3 is not installed. Installing required packages..."
        sudo apt update
        sudo apt install -y python3 python3-pip python3-venv python3-dev build-essential libxml2-dev libxslt1-dev libffi-dev libpq-dev libssl-dev zlib1g-dev git
    fi
    
    # Check Python version
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [[ "$PYTHON_MAJOR" -lt 3 || ("$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10) ]]; then
        echo "Warning: Python 3.10 or later is recommended (found $PYTHON_VERSION)"
        echo "NetBox 4.x requires Python 3.10+"
    fi
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        echo "Error: Docker is not installed. Please install Docker first."
        return 1
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker compose &> /dev/null; then
        echo "Error: Docker Compose is not installed. Please install Docker Compose first."
        return 1
    fi
    
    # Clone NetBox Docker repository
    if [ ! -d "netbox-docker" ]; then
        echo "Cloning NetBox Docker repository..."
        git clone -b release https://github.com/netbox-community/netbox-docker.git
        cd netbox-docker || return 1
    else
        echo "NetBox Docker directory already exists, updating..."
        cd netbox-docker || return 1
        git pull
    fi
    
    # Create override with admin credentials and port mapping
    echo "Creating docker-compose.override.yml with credentials..."
    tee docker-compose.override.yml <<EOF
services:
  netbox:
    ports:
      - 8000:8080
    environment:
      SUPERUSER_NAME: admin
      SUPERUSER_EMAIL: admin@example.com
      SUPERUSER_PASSWORD: admin123
      SUPERUSER_API_TOKEN: ${API_TOKEN}
      ALLOWED_HOSTS: '*'
      SECRET_KEY: '${SECRET_KEY}'
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_DB: netbox
      POSTGRES_USER: netbox
      POSTGRES_PASSWORD: '${POSTGRES_PASSWORD}'
      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_PASSWORD: ''
      REDIS_CACHE_DATABASE: 1
      REDIS_TASK_DATABASE: 0
      MAX_PAGE_SIZE: 0
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  postgres:
    environment:
      POSTGRES_USER: netbox
      POSTGRES_PASSWORD: '${POSTGRES_PASSWORD}'
      POSTGRES_DB: netbox
    volumes:
      - netbox-postgres-data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U netbox"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  netbox-postgres-data:
EOF
    
    # Start NetBox
    echo "Starting NetBox Docker..."
    docker compose pull
    docker compose up -d
    
    # Wait for NetBox to be ready
    echo "Waiting for NetBox to initialize..."
    echo "This may take a few minutes on first launch..."
    MAX_RETRIES=30
    RETRY_COUNT=0
    READY=false
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ | grep -q "200\|302"; then
            READY=true
            break
        fi
        echo "Waiting for NetBox to become available... ($(($RETRY_COUNT+1))/$MAX_RETRIES)"
        sleep 10
        RETRY_COUNT=$((RETRY_COUNT+1))
    done
    
    if [ "$READY" = true ]; then
        echo "NetBox is running successfully!"
        
        # Create admin user with reliable password
        echo "Creating admin user with fixed password..."
        docker exec -it netbox-docker-netbox-1 /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py createsuperuser --username=admin --email=admin@example.com --noinput
        docker exec -it netbox-docker-netbox-1 /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell -c "from django.contrib.auth import get_user_model; u=get_user_model().objects.get(username='admin'); u.set_password('admin123'); u.save()"
        
        # Create API token
        echo "Creating API token..."
        docker exec -it netbox-docker-netbox-1 /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell -c "from users.models import Token; from django.contrib.auth import get_user_model; Token.objects.create(user=get_user_model().objects.get(username='admin'), key='${API_TOKEN}', write_enabled=True)"
    else
        echo "NetBox may not be fully initialized yet. Please check logs with:"
        echo "  docker compose -f $(pwd)/docker-compose.yml -f $(pwd)/docker-compose.override.yml logs -f netbox"
    fi
    
    cd ..
    
    # Save credentials for other functions
    echo "NETBOX_HOST=localhost" > .netbox_creds
    echo "NETBOX_PORT=8000" >> .netbox_creds
    echo "NETBOX_TOKEN=$API_TOKEN" >> .netbox_creds
    echo "NETBOX_PASSWORD=admin123" >> .netbox_creds
    echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" >> .netbox_creds
    
    echo "NetBox setup complete."
    echo "Access NetBox at http://localhost:8000"
    echo "Username: admin"
    echo "Password: admin123"
    echo "API Token: $API_TOKEN"
    echo "Postgres Password: $POSTGRES_PASSWORD"
}

# Function to set up after git clone
setup_gitclone() {
    # Check for prerequisites
    echo "Checking for prerequisites..."
    
    if ! command -v git &>/dev/null; then
        echo "Error: Git is required but not installed. Please install git first."
        return 1
    fi
    
    if ! command -v python3 &>/dev/null; then
        echo "Error: Python 3 is required but not installed. Please install Python 3 first."
        return 1
    fi
    
    # Create virtual environment if not already in one
    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
        
        # Activate virtual environment
        echo "Activating virtual environment..."
        source venv/bin/activate
    fi
    
    # Create requirements.txt if it doesn't exist
    if [ ! -f "requirements.txt" ]; then
        echo "Creating requirements.txt..."
        cat > requirements.txt << EOF
pynetbox>=6.6.0
python-slugify>=5.0.0
pymysql>=1.0.0
ipaddress>=1.0.0
requests>=2.25.0
beautifulsoup4>=4.9.0
EOF
    fi
    
    # Install dependencies
    echo "Installing dependencies..."
    pip install -r requirements.txt
    
    # Create necessary directories if they don't exist
    echo "Creating package structure..."
    mkdir -p migration/extended
    mkdir -p migration/const
    
    # Copy files if missing
    if [ ! -f "migration/__init__.py" ]; then
        echo "Creating migration/__init__.py file..."
        echo '"""Racktables to NetBox Migration Tool"""' > migration/__init__.py
        echo '' >> migration/__init__.py
        echo '__version__ = "1.0.0"' >> migration/__init__.py
    fi
    
    if [ ! -f "migration/extended/__init__.py" ]; then
        echo "Creating extended package __init__.py file..."
        echo '"""Extended migration components for additional Racktables data"""' > migration/extended/__init__.py
    fi
    
    # Create const modules
    if [ ! -f "migration/const/__init__.py" ]; then
        echo "Creating const package structure..."
        echo '"""Constants for migration tool"""' > migration/const/__init__.py
    fi
    
    # Create flags.py
    cat > migration/const/flags.py << EOF
"""Migration flags constants"""

class MigrationFlags:
    """Constants for migration flags"""
    CREATE_VLAN_GROUPS = "CREATE_VLAN_GROUPS"
    CREATE_VLANS = "CREATE_VLANS"
    CREATE_MOUNTED_VMS = "CREATE_MOUNTED_VMS"
    CREATE_UNMOUNTED_VMS = "CREATE_UNMOUNTED_VMS"
    CREATE_RACKED_DEVICES = "CREATE_RACKED_DEVICES"
    CREATE_NON_RACKED_DEVICES = "CREATE_NON_RACKED_DEVICES"
    CREATE_INTERFACES = "CREATE_INTERFACES"
    CREATE_INTERFACE_CONNECTIONS = "CREATE_INTERFACE_CONNECTIONS"
    CREATE_IPV4 = "CREATE_IPV4"
    CREATE_IPV6 = "CREATE_IPV6"
    CREATE_IP_NETWORKS = "CREATE_IP_NETWORKS"
    CREATE_IP_ALLOCATED = "CREATE_IP_ALLOCATED"
    CREATE_IP_NOT_ALLOCATED = "CREATE_IP_NOT_ALLOCATED"
    CREATE_PATCH_CABLES = "CREATE_PATCH_CABLES"
    CREATE_FILES = "CREATE_FILES"
    CREATE_VIRTUAL_SERVICES = "CREATE_VIRTUAL_SERVICES"
    CREATE_NAT_MAPPINGS = "CREATE_NAT_MAPPINGS"
    CREATE_LOAD_BALANCING = "CREATE_LOAD_BALANCING"
    CREATE_MONITORING_DATA = "CREATE_MONITORING_DATA"
    CREATE_AVAILABLE_SUBNETS = "CREATE_AVAILABLE_SUBNETS"
EOF
    
    # Create global_config.py
    cat > migration/const/global_config.py << EOF
"""Global configuration constants"""

class NetBoxConfig:
    """Constants for NetBox configuration"""
    HOST_ENV_VAR = "NETBOX_HOST"
    PORT_ENV_VAR = "NETBOX_PORT"
    TOKEN_ENV_VAR = "NETBOX_TOKEN"
    SSL_ENV_VAR = "NETBOX_USE_SSL"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 8000
    DEFAULT_TOKEN = "0123456789abcdef0123456789abcdef01234567"
    DEFAULT_SSL = False

class DatabaseConfig:
    """Constants for database configuration"""
    HOST_ENV_VAR = "RACKTABLES_DB_HOST"
    PORT_ENV_VAR = "RACKTABLES_DB_PORT"
    USER_ENV_VAR = "RACKTABLES_DB_USER"
    PASSWORD_ENV_VAR = "RACKTABLES_DB_PASSWORD"
    NAME_ENV_VAR = "RACKTABLES_DB_NAME"
    DEFAULT_PORT = 3306
    DEFAULT_CHARSET = "utf8mb4"

class TagConfig:
    """Constants for tag configuration"""
    IPV4_TAG = "IPv4"
    IPV6_TAG = "IPv6"
EOF
    
    # Create config.py from template if it doesn't exist
    if [ ! -f "migration/config.py" ]; then
        echo "Creating config.py with NetBox credentials..."
        
        # Check if NetBox credentials file exists
        NB_HOST="localhost"
        NB_PORT="8000"
        NB_TOKEN="0123456789abcdef0123456789abcdef01234567"
        
        if [ -f ".netbox_creds" ]; then
            echo "Using NetBox credentials from setup"
            source .netbox_creds
            NB_HOST="${NETBOX_HOST}"
            NB_PORT="${NETBOX_PORT}"
            NB_TOKEN="${NETBOX_TOKEN}"
        fi
        
        cat > migration/config.py << EOF
"""
Global configuration settings for the Racktables to NetBox migration tool
"""
from pymysql.cursors import DictCursor
import os
import ipaddress
from migration.const.flags import MigrationFlags
from migration.const.global_config import NetBoxConfig, DatabaseConfig, TagConfig

# Migration flags - control which components are processed
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

# Extended migration flags
CREATE_PATCH_CABLES =          True
CREATE_FILES =                 True
CREATE_VIRTUAL_SERVICES =      True
CREATE_NAT_MAPPINGS =          True
CREATE_LOAD_BALANCING =        True
CREATE_MONITORING_DATA =       True
CREATE_AVAILABLE_SUBNETS =     True

# Site filtering - set to None to process all sites, or specify a site name to restrict migration
TARGET_SITE = None  # This can be set via command line args
TARGET_SITE_ID = None  # Store the numeric ID of the target site

# Whether to store cached data with pickle
STORE_DATA = True

# NetBox API connection settings - can be overridden with environment variables
NB_HOST = os.environ.get('NETBOX_HOST', '${NB_HOST}')
NB_PORT = int(os.environ.get('NETBOX_PORT', '${NB_PORT}'))
NB_TOKEN = os.environ.get('NETBOX_TOKEN', '${NB_TOKEN}')
NB_USE_SSL = os.environ.get('NETBOX_USE_SSL', 'False').lower() in ('true', '1', 'yes')

# Database connection parameters - can be overridden with environment variables
DB_CONFIG = {
    'host': os.environ.get('RACKTABLES_DB_HOST', ''),  # Add your DB host here
    'port': int(os.environ.get('RACKTABLES_DB_PORT', '3306')),
    'user': os.environ.get('RACKTABLES_DB_USER', ''),  # Add your DB user here
    'password': os.environ.get('RACKTABLES_DB_PASSWORD', ''),  # Add your DB password here
    'db': os.environ.get('RACKTABLES_DB_NAME', ''),  # Add your DB name here
    'charset': 'utf8mb4',
    'cursorclass': DictCursor
}

# Common tags
IPV4_TAG = TagConfig.IPV4_TAG
IPV6_TAG = TagConfig.IPV6_TAG
EOF
        
        echo "Created config.py with NetBox connection details"
        echo "Please update database connection settings in migration/config.py"
    fi
    
    echo "Git clone setup complete!"
    echo "You can now run migrate.py:"
    echo "python migration/migrate.py [--site SITE_NAME]"
}

# Function to set up for package distribution
setup_package() {
    echo "Setting up for package distribution..."
    
    # Check if we're in a virtual environment
    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo "Creating virtual environment for package building..."
        python3 -m venv venv-build
        source venv-build/bin/activate
    fi
    
    # Install build dependencies
    echo "Installing build dependencies..."
    pip install build twine wheel setuptools
    
    # Update version in setup.py if needed
    if [ -f "migration/__init__.py" ]; then
        VERSION=$(grep -o '__version__ = "[^"]*"' migration/__init__.py | cut -d'"' -f2)
        if [ -n "$VERSION" ]; then
            echo "Detected version: $VERSION"
            sed -i "s/version=\"[^\"]*\"/version=\"$VERSION\"/g" setup.py 2>/dev/null || true
        fi
    fi
    
    # Create necessary files for distribution
    if [ ! -f "setup.py" ]; then
        echo "Creating setup.py..."
        cat > setup.py << EOF
#!/usr/bin/env python3
"""
Setup script for the Racktables to NetBox migration tool
"""
from setuptools import setup, find_packages

setup(
    name="racktables-netbox-migration",
    version="1.0.0",
    description="Tool to migrate data from Racktables to NetBox",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/racktables-netbox-migration",
    packages=find_packages(),
    install_requires=[
        "pynetbox>=6.6.0",
        "python-slugify>=5.0.0",
        "pymysql>=1.0.0",
        "ipaddress>=1.0.0",
        "requests>=2.25.0"
    ],
    entry_points={
        "console_scripts": [
            "migrate-racktables=migration.migrate:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.6",
)
EOF
    fi
    
    if [ ! -f "pyproject.toml" ]; then
        echo "Creating pyproject.toml..."
        cat > pyproject.toml << EOF
[build-system]
requires = ["setuptools>=42", "wheel"]
build-backend = "setuptools.build_meta"
EOF
    fi
    
    # Build the package
    echo "Building package..."
    python -m build
    
    echo "Package setup complete!"
    echo "To publish to PyPI: python -m twine upload dist/*"
    echo "To install locally: pip install dist/*.whl"
}

# Run the selected functions
if [[ "$SETUP_NETBOX" == "true" ]]; then
    setup_netbox
fi

if [[ "$SETUP_GITCLONE" == "true" ]]; then
    setup_gitclone
fi

if [[ "$SETUP_PACKAGE" == "true" ]]; then
    setup_package
fi

echo "Setup completed successfully!"

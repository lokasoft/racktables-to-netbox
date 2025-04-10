#!/bin/bash
# Enhanced setup script for development environment with all components from scratch

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
    API_TOKEN=$(cat /dev/urandom | tr -dc 'a-z0-9' | head -c 40)
    SUPERUSER_PASSWORD=$(cat /dev/urandom |  tr -dc 'a-zA-Z0-9' | head -c 8)
    POSTGRES_PASSWORD=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c 24)
    
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
      SUPERUSER_PASSWORD: ${SUPERUSER_PASSWORD}
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
        docker exec -it netbox-docker-netbox-1 /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell -c "from django.contrib.auth import get_user_model; u=get_user_model().objects.get(username='admin'); u.set_password('${SUPERUSER_PASSWORD}'); u.save()"
        
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
    echo "NETBOX_PASSWORD=$SUPERUSER_PASSWORD" >> .netbox_creds
    echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" >> .netbox_creds
    
    echo "NetBox setup complete."
    echo "Access NetBox at http://localhost:8000"
    echo "Username: admin"
    echo "Password: $SUPERUSER_PASSWORD"
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
    
    # Create temporary directory and clone there if current dir isn't empty
    if [ "$(ls -A | grep -v 'venv\|netbox-docker\|setup-dev.sh\|requirements.txt\|.netbox_creds')" ]; then
        TEMP_DIR="racktables-migration"
        mkdir -p $TEMP_DIR
        echo "Current directory not empty, cloning to $TEMP_DIR..."
        git clone https://github.com/enoch85/racktables-to-netbox.git $TEMP_DIR
        echo "Moving files from $TEMP_DIR to current directory..."
        mv $TEMP_DIR/* $TEMP_DIR/.* . 2>/dev/null || true
        rmdir $TEMP_DIR
    else
        # Current directory is empty or only contains expected files
        echo "Cloning the repository to current directory..."
        git clone https://github.com/enoch85/racktables-to-netbox.git .
    fi
    
    # Create virtual environment if not already in one
    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
        
        # Activate virtual environment
        echo "Activating virtual environment..."
        source venv/bin/activate
    fi
    
    # Install dependencies and development mode
    echo "Installing dependencies..."
    pip install --upgrade pip
    
    # Install all requirements
    pip install -r requirements.txt --no-cache-dir
    
    # Force install each package from requirements.txt
    while read package; do
        # Skip empty lines and comments
        [[ -z "$package" || "$package" =~ ^# ]] && continue
        
        # Extract package name without version specifiers
        pkg_name=$(echo "$package" | sed -E 's/([a-zA-Z0-9_.-]+).*/\1/')
        
        echo "Force installing $pkg_name..."
        pip install --force-reinstall "$pkg_name"
        
    done < requirements.txt
    
    echo "Installing package in development mode..."
    pip install -e .
    
    # Get NetBox credentials if available
    NB_HOST="localhost"
    NB_PORT="8000"
    NB_TOKEN="0123456789abcdef0123456789abcdef01234567"
    
    if [ -f ".netbox_creds" ]; then
        echo "Using NetBox credentials from setup"
        source .netbox_creds
        NB_HOST="${NETBOX_HOST}"
        NB_PORT="${NETBOX_PORT}"
        NB_TOKEN="${NETBOX_TOKEN}"
        
        # Update config.py with correct API token
        if [ -f "migration/config.py" ]; then
            sed -i "s/NB_TOKEN = os.environ.get('NETBOX_TOKEN', '[^']*')/NB_TOKEN = os.environ.get('NETBOX_TOKEN', '${NB_TOKEN}')/" migration/config.py
            sed -i "s/NB_HOST = os.environ.get('NETBOX_HOST', '[^']*')/NB_HOST = os.environ.get('NETBOX_HOST', '${NB_HOST}')/" migration/config.py
            sed -i "s/NB_PORT = int(os.environ.get('NETBOX_PORT', '[^']*'))/NB_PORT = int(os.environ.get('NETBOX_PORT', '${NB_PORT}'))/" migration/config.py
            echo "Updated config.py with NetBox credentials"
        fi
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

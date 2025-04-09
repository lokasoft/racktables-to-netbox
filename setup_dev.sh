#!/bin/bash
# Setup script for development environment

echo "Setting up development environment for Racktables to NetBox migration tool"

# Check if we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Please activate the virtual environment with 'source venv/bin/activate' and run this script again"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create necessary directories
echo "Creating package structure..."
mkdir -p racktables_netbox_migration/extended

# Copy files if missing
if [ ! -f "racktables_netbox_migration/__init__.py" ]; then
    echo "Creating package __init__.py file..."
    cp __init__.py racktables_netbox_migration/
fi

if [ ! -d "racktables_netbox_migration/extended/__init__.py" ]; then
    echo "Creating extended package __init__.py file..."
    mkdir -p racktables_netbox_migration/extended
    echo '"""Extended migration components"""' > racktables_netbox_migration/extended/__init__.py
fi

# Install package locally
pip install -e .

# Goto package dir
cd racktables_netbox_migration

echo "Development environment setup complete!"
echo "You can now run migrate_wrapper.py directly:"
echo "python migrate_wrapper.py [--site SITE_NAME]"

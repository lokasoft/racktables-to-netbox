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

# Create necessary directories if they don't exist
echo "Creating package structure..."
mkdir -p migration/extended

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

# Install package locally
echo "Installing package in development mode..."
pip install -e .

echo "Development environment setup complete!"
echo "You can now run migrate.py:"
echo "python migration/migrate.py [--site SITE_NAME]"

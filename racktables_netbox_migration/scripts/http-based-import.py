#!/usr/bin/env python3
"""
Network prefix import script using direct HTTP API calls
No reliance on pynetbox library for maximum compatibility
"""
import re
import sys
import time
import json
import requests
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# NetBox connection details - UPDATE THESE
NETBOX_URL = "http://localhost:8000"
API_TOKEN = "YOUR API TOKEN HERE"  # Your token here
INPUT_FILE = "paste.txt"  # File containing network data which is basically just a copy paste from CTRL+A and CTRL+V from this tab: https://racktables.yourdomain.come/index.php?page=ipv4space&tab=default&eid=ALL

# Constants
VERIFY_SSL = False  # Set to True if using valid SSL certificate
BATCH_SIZE = 10     # Number of prefixes to process at once
DELAY = 0.5         # Delay between batches in seconds

def test_api_connection():
    """Test basic connection to NetBox API"""
    # Create session with standard headers
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Token {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    })
    session.verify = VERIFY_SSL
    
    try:
        # Check if we can connect to the API
        response = session.get(f"{NETBOX_URL}/api/status/")
        if response.status_code == 200:
            data = response.json()
            version = data.get("netbox-version", "unknown")
            print(f"✅ Connected to NetBox {version}")
            
            # Test authentication by trying to access an authenticated endpoint
            auth_response = session.get(f"{NETBOX_URL}/api/users/users/")
            if auth_response.status_code == 200:
                print(f"✅ Authentication successful")
                return session
            elif auth_response.status_code == 403:
                print(f"❌ Authentication failed: Permission denied")
                print(f"Your token might not have the required permissions")
                return None
            else:
                print(f"❌ Authentication failed: {auth_response.status_code}")
                print(f"Response: {auth_response.text}")
                return None
        else:
            print(f"❌ Connection failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Connection error: {str(e)}")
        return None

def read_prefixes_from_file(filename):
    """Read network prefixes from a file"""
    try:
        with open(filename, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {filename}: {str(e)}")
        return []

    # Extract network prefixes using regex
    pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})\s+([^\t]+)\t+(\d+)'
    matches = re.findall(pattern, content)
    
    # Convert matches to a list of dicts with the data we need
    prefixes = []
    for prefix, name, capacity in matches:
        name = name.strip()
        if name == "[Here be dragons.] [create network here]":
            name = f"Unused network - {prefix}"
        
        prefixes.append({
            "prefix": prefix,
            "description": name,
            "status": "active"
        })
    
    return prefixes

def create_test_prefix(session):
    """Test creating a single prefix"""
    test_prefix = "192.168.254.0/24"
    test_data = {
        "prefix": test_prefix,
        "description": "Test Prefix - Delete Me",
        "status": "active"
    }
    
    print(f"Testing prefix creation with {test_prefix}...")
    
    # Check if the prefix already exists
    check_url = f"{NETBOX_URL}/api/ipam/prefixes/?prefix={test_prefix}"
    try:
        response = session.get(check_url)
        exists = False
        
        if response.status_code == 200:
            data = response.json()
            if data["count"] > 0:
                exists = True
                existing_id = data["results"][0]["id"]
                print(f"Test prefix already exists (ID: {existing_id})")
                
                # Try to delete it
                delete_response = session.delete(f"{NETBOX_URL}/api/ipam/prefixes/{existing_id}/")
                if delete_response.status_code == 204:
                    print(f"Successfully deleted existing test prefix")
                else:
                    print(f"Could not delete existing prefix: HTTP {delete_response.status_code}")
                    print(f"Response: {delete_response.text}")
        else:
            print(f"Error checking for existing prefix: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error checking for existing prefix: {str(e)}")
        return False
    
    # Create the test prefix
    try:
        response = session.post(
            f"{NETBOX_URL}/api/ipam/prefixes/",
            data=json.dumps(test_data)
        )
        
        if response.status_code == 201:
            data = response.json()
            prefix_id = data.get("id")
            print(f"✅ Test prefix created successfully (ID: {prefix_id})")
            
            # Try to delete it
            delete_response = session.delete(f"{NETBOX_URL}/api/ipam/prefixes/{prefix_id}/")
            if delete_response.status_code == 204:
                print(f"✅ Test prefix deleted successfully")
            else:
                print(f"⚠️ Could not delete test prefix: HTTP {delete_response.status_code}")
            
            return True
        else:
            print(f"❌ Error creating test prefix: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error creating test prefix: {str(e)}")
        return False

def import_prefixes(session, prefixes):
    """Import prefixes into NetBox"""
    success_count = 0
    error_count = 0
    skip_count = 0
    
    # Process prefixes in batches
    total_batches = (len(prefixes) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for batch_index in range(total_batches):
        start_idx = batch_index * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(prefixes))
        batch = prefixes[start_idx:end_idx]
        
        print(f"\nProcessing batch {batch_index + 1}/{total_batches} ({len(batch)} prefixes)")
        
        for prefix_data in batch:
            prefix = prefix_data["prefix"]
            
            # Check if prefix already exists
            check_url = f"{NETBOX_URL}/api/ipam/prefixes/?prefix={prefix}"
            try:
                response = session.get(check_url)
                
                if response.status_code == 200:
                    data = response.json()
                    if data["count"] > 0:
                        print(f"  Skipping existing prefix: {prefix}")
                        skip_count += 1
                        continue
                else:
                    print(f"  Warning: Error checking for existing prefix: HTTP {response.status_code}")
            except Exception as e:
                print(f"  Warning: Error checking for existing prefix: {str(e)}")
            
            # Create the prefix
            try:
                response = session.post(
                    f"{NETBOX_URL}/api/ipam/prefixes/",
                    data=json.dumps(prefix_data)
                )
                
                if response.status_code == 201:
                    data = response.json()
                    prefix_id = data.get("id")
                    print(f"  Created: {prefix} - {prefix_data['description']} (ID: {prefix_id})")
                    success_count += 1
                else:
                    print(f"  Error creating {prefix}: HTTP {response.status_code}")
                    print(f"  Response: {response.text}")
                    error_count += 1
            except Exception as e:
                print(f"  Error creating {prefix}: {str(e)}")
                error_count += 1
        
        # Delay between batches to avoid overwhelming the API
        if batch_index < total_batches - 1:
            time.sleep(DELAY)
    
    return success_count, skip_count, error_count

def main():
    """Main function to run the import"""
    print(f"Direct API Network Import Script")
    print(f"-------------------------------")
    
    # Check connection to NetBox
    print("\n1. Testing API connection and authentication...")
    session = test_api_connection()
    if not session:
        print("Aborting due to connection or authentication issues.")
        return 1
    
    # Test prefix creation
    print("\n2. Testing prefix creation capability...")
    if not create_test_prefix(session):
        print("Your token doesn't have permission to create prefixes.")
        print("Please update your token permissions and try again.")
        return 1
    
    # Read prefixes from file
    print("\n3. Reading prefixes from file...")
    prefixes = read_prefixes_from_file(INPUT_FILE)
    if not prefixes:
        print(f"No prefixes found in {INPUT_FILE}. Aborting.")
        return 1
    
    print(f"Found {len(prefixes)} prefixes to import")
    
    # Confirm before proceeding
    confirm = input("\nContinue with import? (y/n): ")
    if confirm.lower() != 'y':
        print("Import cancelled.")
        return 0
    
    # Import prefixes
    print("\n4. Importing prefixes...")
    start_time = time.time()
    success, skipped, errors = import_prefixes(session, prefixes)
    elapsed = time.time() - start_time
    
    # Print summary
    print(f"\nImport completed in {elapsed:.1f} seconds")
    print(f"Summary:")
    print(f"- Prefixes created: {success}")
    print(f"- Prefixes skipped (already exist): {skipped}")
    print(f"- Errors: {errors}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

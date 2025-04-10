#!/usr/bin/env python3
"""
Extended custom fields script for Racktables to NetBox migration
Includes support for additional Racktables tables not covered in original migration
"""

import requests
import json
import time
import sys
import os

# Define BASE_DIR
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Import configuration from config.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from migration.config import NB_HOST, NB_PORT, NB_TOKEN, NB_USE_SSL

# Construct API URL and token from config.py
API_URL = f"{'https' if NB_USE_SSL else 'http'}://{NB_HOST}"
if NB_PORT:
    API_URL = f"{API_URL}:{NB_PORT}"
API_TOKEN = NB_TOKEN

# Prepare headers for API requests
HEADERS = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# Check if config appears to be default values
def check_config():
    default_token = "0123456789abcdef0123456789abcdef01234567"
    if NB_TOKEN == default_token:
        print("ERROR: Default API token detected in config.py.")
        print("Please update migration/config.py with your actual NetBox configuration.")
        print("You need to set NB_TOKEN to your actual NetBox API token.")
        return False
    
    if NB_HOST == "localhost" and NB_PORT == 8000:
        print("WARNING: Using default NetBox connection settings (localhost:8000).")
        print("If this is not your actual NetBox server, update migration/config.py.")
    
    return True

# Function to create a custom field
def create_custom_field(name, field_type, object_types, description="", required=False, weight=0, label=None):
    """Create a custom field using the NetBox API with correct format for 4.2.6"""
    
    # Convert single string to list if needed
    if isinstance(object_types, str):
        object_types = [object_types]
    
    # Prepare the payload
    payload = {
        "name": name,
        "type": field_type,
        "object_types": object_types,
        "description": description,
        "required": required,
        "weight": weight
    }
    
    # Add label if provided
    if label:
        payload["label"] = label
    
    # Send the request
    print(f"Creating custom field: {name} for {', '.join(object_types)}")
    try:
        response = requests.post(
            f"{API_URL}/api/extras/custom-fields/",
            headers=HEADERS,
            data=json.dumps(payload),
            timeout=10
        )
        
        # Check the response
        if response.status_code in (201, 200):
            print(f"✓ Created custom field: {name}")
            return True
        else:
            print(f"✗ Failed to create custom field: {name}")
            print(f"  Status code: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Connection error: {str(e)}")
        return False

# Original custom fields (keeping these)
original_custom_fields = [
    # VLAN Group custom fields
    {"name": "VLAN_Domain_ID", "type": "text", "object_types": ["ipam.vlangroup"], 
     "description": "ID for VLAN Domain", "required": True},
    
    # Prefix custom fields
    {"name": "Prefix_Name", "type": "text", "object_types": ["ipam.prefix"], 
     "description": "Name for prefix"},
    
    # Device custom fields
    {"name": "Device_Label", "type": "text", "object_types": ["dcim.device"], 
     "description": "Label for device"},
    
    # VM custom fields
    {"name": "VM_Asset_No", "type": "text", "object_types": ["virtualization.virtualmachine"], 
     "description": "Asset number for VMs"},
    {"name": "VM_Label", "type": "text", "object_types": ["virtualization.virtualmachine"], 
     "description": "Label for VMs"},
    
    # VM Interface custom fields
    {"name": "VM_Interface_Type", "type": "text", "object_types": ["virtualization.vminterface"], 
     "description": "Enter type for VM interface", "required": True, "label": "Custom type for VM interfaces"},
    
    # Device Interface custom fields
    {"name": "Device_Interface_Type", "type": "text", "object_types": ["dcim.interface"], 
     "description": "Enter type for interface", "required": True, "label": "Custom type for interfaces"},
    
    # IP Address custom fields
    {"name": "IP_Type", "type": "text", "object_types": ["ipam.ipaddress"], 
     "description": "Type of ip", "label": "Type"},
    {"name": "IP_Name", "type": "text", "object_types": ["ipam.ipaddress"], 
     "description": "Name of ip", "label": "Name"},
    {"name": "Interface_Name", "type": "text", "object_types": ["ipam.ipaddress"], 
     "description": "Name of interface for this IP", "label": "Interface Name"},
    
    # Additional device custom fields
    {"name": "OEM_SN_1", "type": "text", "object_types": ["dcim.device"]},
    {"name": "HW_type", "type": "text", "object_types": ["dcim.device"]},
    {"name": "FQDN", "type": "text", "object_types": ["dcim.device"]},
    {"name": "SW_type", "type": "text", "object_types": ["dcim.device"]},
    {"name": "SW_version", "type": "text", "object_types": ["dcim.device"]},
    {"name": "number_of_ports", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "max_current_Ampers", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "power_load_percents", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "max_power_Watts", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "contact_person", "type": "text", "object_types": ["dcim.device"]},
    {"name": "flash_memory_MB", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "DRAM_MB", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "CPU_MHz", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "OEM_SN_2", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Support_Contract_Expiration", "type": "text", "object_types": ["dcim.device"]},
    {"name": "HW_warranty_expiration", "type": "text", "object_types": ["dcim.device"]},
    {"name": "SW_warranty_expiration", "type": "text", "object_types": ["dcim.device"]},
    {"name": "UUID", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Hypervisor", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Height_units", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "Slot_number", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Sort_order", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "Mgmt_type", "type": "text", "object_types": ["dcim.device"]},
    {"name": "base_MAC_address", "type": "text", "object_types": ["dcim.device"]},
    {"name": "RAM_MB", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "Processor", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Total_Disk_GB", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "Processor_Count", "type": "integer", "object_types": ["dcim.device"]},
    {"name": "Service_Tag", "type": "text", "object_types": ["dcim.device"]},
    {"name": "PDU", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Circuit", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Contract_Number", "type": "text", "object_types": ["dcim.device"]},
    {"name": "DSP_Slot_1_Serial", "type": "text", "object_types": ["dcim.device"]},
    {"name": "DSP_Slot_2_Serial", "type": "text", "object_types": ["dcim.device"]},
    {"name": "DSP_Slot_3_Serial", "type": "text", "object_types": ["dcim.device"]},
    {"name": "DSP_Slot_4_Serial", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Chassis_Serial", "type": "text", "object_types": ["dcim.device"]},
    {"name": "SBC_PO", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Chassis_Model", "type": "text", "object_types": ["dcim.device"]},
    {"name": "Application_SW_Version", "type": "text", "object_types": ["dcim.device"]},
    {"name": "RHVM_URL", "type": "text", "object_types": ["dcim.device"]},
    {"name": "TIPC_NETID", "type": "text", "object_types": ["dcim.device"]},
    {"name": "CE_IP_Active", "type": "text", "object_types": ["dcim.device"]},
    {"name": "CE_IP_Standby", "type": "text", "object_types": ["dcim.device"]},
    {"name": "GPU_Serial_Number_1", "type": "text", "object_types": ["dcim.device"]},
    {"name": "GPU_Serial_Number_2", "type": "text", "object_types": ["dcim.device"]},
]

# New custom fields for additional tables
new_custom_fields = [
    # Cable Management custom fields for dcim.cable
    {"name": "Patch_Cable_Type", "type": "text", "object_types": ["dcim.cable"], 
     "description": "Type of patch cable from Racktables"},
    {"name": "Patch_Cable_Connector_A", "type": "text", "object_types": ["dcim.cable"], 
     "description": "A-side connector type"},
    {"name": "Patch_Cable_Connector_B", "type": "text", "object_types": ["dcim.cable"], 
     "description": "B-side connector type"},
    {"name": "Cable_Color", "type": "text", "object_types": ["dcim.cable"], 
     "description": "Color of the cable"},
    {"name": "Cable_Length", "type": "text", "object_types": ["dcim.cable"], 
     "description": "Length of the cable"},
    
    # Virtual Services custom fields
    {"name": "VS_Enabled", "type": "boolean", "object_types": ["ipam.service"], 
     "description": "Virtual service is enabled"},
    {"name": "VS_Type", "type": "text", "object_types": ["ipam.service"], 
     "description": "Type of virtual service"},
    {"name": "VS_Protocol", "type": "text", "object_types": ["ipam.service"], 
     "description": "Protocol used by virtual service"},
    
    # NAT & Load Balancing custom fields for IP Addresses
    {"name": "NAT_Type", "type": "text", "object_types": ["ipam.ipaddress"], 
     "description": "Type of NAT (SNAT, DNAT, etc.)"},
    {"name": "NAT_Match_IP", "type": "text", "object_types": ["ipam.ipaddress"], 
     "description": "Matching IP for NAT relationship"},
    {"name": "LB_Config", "type": "text", "object_types": ["ipam.ipaddress"], 
     "description": "Load balancer configuration"},
    {"name": "LB_Pool", "type": "text", "object_types": ["ipam.ipaddress"], 
     "description": "Load balancer pool membership"},
    {"name": "RS_Pool", "type": "text", "object_types": ["ipam.ipaddress"], 
     "description": "Real server pool"},
    
    # Monitoring custom fields for devices
    {"name": "Cacti_Server", "type": "text", "object_types": ["dcim.device", "virtualization.virtualmachine"],
     "description": "Cacti server monitoring this device"},
    {"name": "Cacti_Graph_ID", "type": "text", "object_types": ["dcim.device", "virtualization.virtualmachine"], 
     "description": "ID of Cacti graph for this device"},
    {"name": "Monitoring_URL", "type": "text", "object_types": ["dcim.device", "virtualization.virtualmachine"], 
     "description": "URL to monitoring system for this device"},
    
    # Attachment custom fields 
    {"name": "File_References", "type": "text", "object_types": ["dcim.device", "virtualization.virtualmachine"], 
     "description": "References to attached files from Racktables"},
    {"name": "File_Description", "type": "text", "object_types": ["extras.objectchange"], 
     "description": "Description of attached file"}
]

def main():
    """Main function to create custom fields"""
    # Verify configuration
    if not check_config():
        return False
    
    # Combine all custom fields
    all_custom_fields = original_custom_fields + new_custom_fields
    
    print(f"Creating {len(all_custom_fields)} custom fields in NetBox...")
    
    success_count = 0
    failure_count = 0
    
    for field in all_custom_fields:
        success = create_custom_field(
            field["name"],
            field["type"],
            field["object_types"],
            field.get("description", ""),
            field.get("required", False),
            field.get("weight", 0),
            field.get("label")
        )
        
        if success:
            success_count += 1
        else:
            failure_count += 1
        
        # Add a short delay to avoid rate limiting
        time.sleep(0.5)
    
    print(f"\nSummary:")
    print(f"- Successfully created: {success_count}")
    print(f"- Failed to create: {failure_count}")
    
    # Check MAX_PAGE_SIZE setting
    print("\nChecking MAX_PAGE_SIZE setting...")
    try:
        response = requests.get(f"{API_URL}/api/users/config/", headers=HEADERS)
        if response.status_code == 200:
            config = response.json()
            if 'MAX_PAGE_SIZE' in config and config['MAX_PAGE_SIZE'] == 0:
                print("✓ MAX_PAGE_SIZE is already set to 0")
            else:
                print("i MAX_PAGE_SIZE needs to be set to 0 manually")
                print("  Edit the netbox.env file and add: MAX_PAGE_SIZE=0")
                print("  Then restart NetBox: docker-compose restart netbox")
        else:
            print(f"✗ Failed to check MAX_PAGE_SIZE setting")
            print(f"  Status code: {response.status_code}")
            if response.text:
                print(f"  Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to check MAX_PAGE_SIZE setting: {str(e)}")
        
if __name__ == "__main__":
    main()

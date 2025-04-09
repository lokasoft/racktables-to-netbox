"""
Global configuration settings for the Racktables to NetBox migration tool
"""
from pymysql.cursors import DictCursor
import ipaddress
import os

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
TARGET_SITE = None  # This can be set by migrate_wrapper.py via command line args
TARGET_SITE_ID = None  # Store the numeric ID of the target site

# Whether to store cached data with pickle
STORE_DATA = False

# The length to exceed for a site to be considered a location (like an address) not a site
SITE_NAME_LENGTH_THRESHOLD = 10

# First character for separating identical devices in different spots in same rack
FIRST_ASCII_CHARACTER = " "

# Common tags
IPV4_TAG = "IPv4"
IPV6_TAG = "IPv6"

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

# Maps racktables object type IDs to names
OBJTYPE_ID_NAMES = {
    1: "BlackBox",
    2: "PDU",
    3: "Shelf",
    4: "Server",
    5: "DiskArray",
    7: "Router",
    8: "Network Switch",
    9: "Patch Panel",
    10: "CableOrganizer",
    11: "spacer",
    12: "UPS",
    13: "Modem",
    15: "console",
    447: "multiplexer",
    798: "Network Security",
    1502: "Server Chassis",
    1398: "Power supply",
    1503: "Network chassis",
    1644: "serial console server",
    1787: "Management interface",
    50003: "Circuit",
    50013: "SAN",
    50044: "SBC",
    50064: "GSX",
    50065: "EMS",
    50066: "PSX",
    50067: "SGX",
    50083: "SBC SWE",
    # Don't create these with the unracked devices
    # 1504: "VM",
    # 1505: "VM Cluster",
    # 1560: "Rack",
    # 1561: "Row",
    # 1562: "Location",
}

# Manufacturer strings from Racktables
RACKTABLES_MANUFACTURERS = {
    'Generic', 'Dell', 'MicroSoft', 'F5', 'ExtremeXOS', 'Netapp', 'Open Solaris', 'EMC', 
    'SlackWare', 'RH', 'FreeBSD', 'Edge-Core', 'SMC', 'Force10', 'Cyclades', 'IBM', 
    'Linksys', 'IronWare', 'Red', 'Promise', 'Extreme', 'QLogic', 'Marvell', 'SonicWall', 
    'Foundry', 'Juniper', 'APC', 'Raritan', 'Xen', 'NEC', 'Palo', 'OpenSUSE', 'Sun', 
    'noname/unknown', 'NetApp', 'VMware', 'Moxa', 'Tainet', 'SGI', 'Mellanox', 'Vyatta', 
    'Raisecom', 'Gentoo', 'Brocade', 'Enterasys', 'Dell/EMC', 'VMWare', 'Infortrend', 
    'OpenGear', 'Arista', 'Lantronix', 'Huawei', 'Avocent', 'SUSE', 'ALT_Linux', 'OpenBSD', 
    'Nortel', 'Univention', 'JunOS', 'MikroTik', 'NetBSD', 'Cronyx', 'Aten', 'Intel', 
    'PROXMOX', 'Ubuntu', 'Motorola', 'SciLin', 'Fujitsu', 'Fiberstore', '3Com', 'D-Link', 
    'Allied', 'Fortigate', 'Debian', 'HP', 'NETGEAR', 'Pica8', 'TPLink', 'Fortinet', 'RAD', 
    'NS-OS', 'Cisco', 'Alcatel-Lucent', 'CentOS', 'Hitachi'
}

# Pairs of parent objtype_id, then child objtype_id
PARENT_CHILD_OBJTYPE_ID_PAIRS = (
    (1502, 4),  # Server inside a Server Chassis
    (9, 9),     # Patch Panel inside a Patch Panel
)

# Interface name mappings for cleanup
INTERFACE_NAME_MAPPINGS = {
    "Eth": "Ethernet",
    "eth": "Ethernet",
    "ethernet": "Ethernet",
    "Po": "Port-Channel",
    "Port-channel": "Port-Channel",
    "BE": "Bundle-Ether",
    "Lo": "Loopback",
    "Loop": "Loopback",
    "Vl": "VLAN",
    "Vlan": "VLAN",
    "Mg": "MgmtEth",
    "Se": "Serial",
    "Gi": "GigabitEthernet",
    "Te": "TenGigE",
    "Tw": "TwentyFiveGigE",
    "Fo": "FortyGigE",
    "Hu": "HundredGigE",
}

# Global data collections
PARENT_OBJTYPE_IDS = [pair[0] for pair in PARENT_CHILD_OBJTYPE_ID_PAIRS]

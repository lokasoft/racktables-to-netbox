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
            "migrate-racktables=migrate_wrapper:main",
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
    ],
    python_requires=">=3.6",
)

#!/bin/bash
# Script to check or modify MAX_PAGE_SIZE in NetBox Docker environment

# Path to your NetBox Docker installation - MODIFY THIS
NETBOX_DOCKER_PATH="/path/to/netbox-docker"
NETBOX_ENV_FILE="$NETBOX_DOCKER_PATH/env/netbox.env"

# Check if netbox.env exists
if [ ! -f "$NETBOX_ENV_FILE" ]; then
    echo "⚠️ NetBox environment file not found at: $NETBOX_ENV_FILE"
    echo "Please update the NETBOX_DOCKER_PATH variable in this script."
    exit 1
fi

# Check if MAX_PAGE_SIZE setting exists
if grep -q "^MAX_PAGE_SIZE=" "$NETBOX_ENV_FILE"; then
    # Get current value
    current_value=$(grep "^MAX_PAGE_SIZE=" "$NETBOX_ENV_FILE" | cut -d= -f2)
    echo "Current MAX_PAGE_SIZE setting: $current_value"
    
    # Check if it's already set to 0
    if [ "$current_value" == "0" ]; then
        echo "✅ MAX_PAGE_SIZE is already set to 0"
    else
        # Ask if user wants to change it
        read -p "Do you want to change MAX_PAGE_SIZE to 0? (y/n): " change_it
        if [[ $change_it == "y" || $change_it == "Y" ]]; then
            # Replace existing setting
            sed -i 's/^MAX_PAGE_SIZE=.*/MAX_PAGE_SIZE=0/' "$NETBOX_ENV_FILE"
            echo "✅ Updated MAX_PAGE_SIZE to 0"
            echo "You need to restart NetBox for this change to take effect."
            read -p "Do you want to restart NetBox now? (y/n): " restart_now
            if [[ $restart_now == "y" || $restart_now == "Y" ]]; then
                echo "Restarting NetBox..."
                cd "$NETBOX_DOCKER_PATH" && docker-compose restart netbox
                echo "✅ NetBox has been restarted"
            else
                echo "⚠️ Remember to restart NetBox manually:"
                echo "cd $NETBOX_DOCKER_PATH && docker-compose restart netbox"
            fi
        else
            echo "MAX_PAGE_SIZE left unchanged at: $current_value"
        fi
    fi
else
    # Setting doesn't exist, ask to add it
    echo "MAX_PAGE_SIZE setting not found in netbox.env"
    read -p "Do you want to add MAX_PAGE_SIZE=0 to netbox.env? (y/n): " add_it
    if [[ $add_it == "y" || $add_it == "Y" ]]; then
        # Add the setting
        echo "MAX_PAGE_SIZE=0" >> "$NETBOX_ENV_FILE"
        echo "✅ Added MAX_PAGE_SIZE=0 to netbox.env"
        echo "You need to restart NetBox for this change to take effect."
        read -p "Do you want to restart NetBox now? (y/n): " restart_now
        if [[ $restart_now == "y" || $restart_now == "Y" ]]; then
            echo "Restarting NetBox..."
            cd "$NETBOX_DOCKER_PATH" && docker-compose restart netbox
            echo "✅ NetBox has been restarted"
        else
            echo "⚠️ Remember to restart NetBox manually:"
            echo "cd $NETBOX_DOCKER_PATH && docker-compose restart netbox"
        fi
    else
        echo "MAX_PAGE_SIZE setting not added"
    fi
fi

echo ""
echo "Note: MAX_PAGE_SIZE=0 is required for the Racktables to NetBox migration tool"
echo "to properly fetch all objects in a single request."

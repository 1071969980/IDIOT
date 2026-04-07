#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Available volume directories
VOLUMES=(
    "postgres"
    "juicefs-minio"
    "juicefs-postgres"
    "api"
    "redis"
    "minio"
    "prometheus"
)

# Test environment volumes (nested under test/)
TEST_VOLUMES=(
    "test/postgres"
    "test/juicefs-minio"
    "test/juicefs-postgres"
    "test/api"
    "test/redis"
    "test/minio"
    "test/neo4j"
    "test/prometheus"
)

echo -e "${BLUE}=== K8s Volumes Cleaner ===${NC}"
echo -e "${YELLOW}This script will clean the contents of K8s volumes.${NC}"
echo

# Function to display available volumes
show_volumes() {
    echo -e "${BLUE}Available volumes:${NC}"
    for i in "${!VOLUMES[@]}"; do
        local volume="${VOLUMES[$i]}"
        local path="./volumes/$volume"
        if [ -d "$path" ]; then
            echo -e "  ${GREEN}$((i+1)).${NC} $volume ($path)"
        else
            echo -e "  ${RED}$((i+1)).${NC} $volume ($path) - ${RED}Not found${NC}"
        fi
    done
    echo
    echo -e "${BLUE}Test environment volumes:${NC}"
    local offset=${#VOLUMES[@]}
    for i in "${!TEST_VOLUMES[@]}"; do
        local volume="${TEST_VOLUMES[$i]}"
        local path="./volumes/$volume"
        local display_name="${volume//test\//}  (test)"
        if [ -d "$path" ]; then
            echo -e "  ${GREEN}$((offset+i+1)).${NC} $display_name ($path)"
        else
            echo -e "  ${RED}$((offset+i+1)).${NC} $display_name ($path) - ${RED}Not found${NC}"
        fi
    done
    echo
}

# Function to clean a single volume
clean_volume() {
    local volume=$1
    local path="./volumes/$volume"

    if [ ! -d "$path" ]; then
        echo -e "${RED}Volume directory $path does not exist.${NC}"
        return 1
    fi

    # Check if directory is empty (including hidden files)
    if [ -z "$(sudo ls -A "$path" 2>/dev/null)" ]; then
        echo -e "${YELLOW}Volume $volume is already empty.${NC}"
        return 0
    fi

    echo -e "${YELLOW}Cleaning volume: $volume${NC}"
    echo -e "Path: $path"

    # Use sudo to clean since files are owned by root (from containers)
    # Remove both regular files/folders and hidden files/folders (starting with .)
    if sudo rm -rf "$path"/* "$path"/.[!.]* "$path"/..?* 2>/dev/null; then
        echo -e "${GREEN}✓ Successfully cleaned $volume${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to clean $volume${NC}"
        return 1
    fi
}

# Function to clean all volumes
clean_all() {
    echo -e "${YELLOW}Cleaning all volumes...${NC}"
    echo

    local failed_count=0
    for volume in "${VOLUMES[@]}"; do
        clean_volume "$volume" || ((failed_count++))
        echo
    done

    if [ $failed_count -eq 0 ]; then
        echo -e "${GREEN}All volumes cleaned successfully!${NC}"
    else
        echo -e "${RED}$failed_count volume(s) failed to clean.${NC}"
    fi
}

# Function to clean all test environment volumes
clean_all_test() {
    echo -e "${YELLOW}Cleaning all test environment volumes...${NC}"
    echo

    local failed_count=0
    for volume in "${TEST_VOLUMES[@]}"; do
        clean_volume "$volume" || ((failed_count++))
        echo
    done

    if [ $failed_count -eq 0 ]; then
        echo -e "${GREEN}All test volumes cleaned successfully!${NC}"
    else
        echo -e "${RED}$failed_count test volume(s) failed to clean.${NC}"
    fi
}

# Function to clean selected volumes
clean_selected() {
    # Merge both lists for indexed access
    local ALL_VOLUMES=("${VOLUMES[@]}" "${TEST_VOLUMES[@]}")
    local total=${#ALL_VOLUMES[@]}

    echo -e "${BLUE}Enter volume numbers to clean (e.g., 1,3,5 or 1-5):${NC}"
    read -p "> " selection

    # Parse selection
    local volumes_to_clean=()
    IFS=',' read -ra selections <<< "$selection"

    for sel in "${selections[@]}"; do
        if [[ "$sel" =~ ^[0-9]+-[0-9]+$ ]]; then
            # Handle range (e.g., 1-5)
            IFS='-' read -ra range <<< "$sel"
            local start=${range[0]}
            local end=${range[1]}
            for ((i=start; i<=end && i<=total; i++)); do
                volumes_to_clean+=("${ALL_VOLUMES[$((i-1))]}")
            done
        elif [[ "$sel" =~ ^[0-9]+$ ]]; then
            # Handle single number
            local idx=$((sel-1))
            if [ $idx -ge 0 ] && [ $idx -lt $total ]; then
                volumes_to_clean+=("${ALL_VOLUMES[$idx]}")
            else
                echo -e "${RED}Invalid volume number: $sel${NC}"
            fi
        else
            echo -e "${RED}Invalid selection: $sel${NC}"
        fi
    done

    if [ ${#volumes_to_clean[@]} -eq 0 ]; then
        echo -e "${RED}No valid volumes selected.${NC}"
        return 1
    fi

    echo
    echo -e "${YELLOW}Selected volumes to clean:${NC}"
    for volume in "${volumes_to_clean[@]}"; do
        echo -e "  - $volume"
    done
    echo

    read -p "Continue? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        local failed_count=0
        for volume in "${volumes_to_clean[@]}"; do
            clean_volume "$volume" || ((failed_count++))
            echo
        done

        if [ $failed_count -eq 0 ]; then
            echo -e "${GREEN}All selected volumes cleaned successfully!${NC}"
        else
            echo -e "${RED}$failed_count volume(s) failed to clean.${NC}"
        fi
    else
        echo -e "${YELLOW}Operation cancelled.${NC}"
    fi
}

# Function to show individual volume contents
show_volume_contents() {
    local volume=$1
    local path="./volumes/$volume"

    if [ ! -d "$path" ]; then
        echo -e "${RED}Volume directory $path does not exist.${NC}"
        return 1
    fi

    echo -e "${BLUE}Contents of $volume:${NC}"
    echo -e "Path: $path"

    if [ -z "$(sudo ls -A "$path" 2>/dev/null)" ]; then
        echo -e "${YELLOW}  (empty)${NC}"
    else
        echo -e "${BLUE}  Contents (including hidden files):${NC}"
        sudo ls -la "$path" 2>/dev/null || echo -e "${RED}  (permission denied)${NC}"
    fi
}

# Main menu
main_menu() {
    while true; do
        show_volumes
        echo -e "${BLUE}Options:${NC}"
        echo "1. Clean all volumes"
        echo "2. Clean all test environment volumes"
        echo "3. Clean selected volumes"
        echo "4. Show contents of a volume"
        echo "5. Exit"
        echo
        read -p "Choose an option (1-5): " choice

        case $choice in
            1)
                echo
                read -p "Are you sure you want to clean ALL volumes? (y/N): " confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    echo
                    clean_all
                else
                    echo -e "${YELLOW}Operation cancelled.${NC}"
                fi
                echo
                ;;
            2)
                echo
                read -p "Are you sure you want to clean ALL test environment volumes? (y/N): " confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    echo
                    clean_all_test
                else
                    echo -e "${YELLOW}Operation cancelled.${NC}"
                fi
                echo
                ;;
            3)
                echo
                clean_selected
                echo
                ;;
            4)
                echo
                local ALL_VOLUMES=("${VOLUMES[@]}" "${TEST_VOLUMES[@]}")
                echo -e "${BLUE}Enter volume number to inspect:${NC}"
                read -p "> " vol_num
                if [[ "$vol_num" =~ ^[0-9]+$ ]] && [ $vol_num -ge 1 ] && [ $vol_num -le ${#ALL_VOLUMES[@]} ]; then
                    echo
                    show_volume_contents "${ALL_VOLUMES[$((vol_num-1))]}"
                else
                    echo -e "${RED}Invalid volume number.${NC}"
                fi
                echo
                ;;
            5)
                echo -e "${GREEN}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option. Please choose 1-5.${NC}"
                echo
                ;;
        esac
    done
}

# Check if running from k8s directory
if [ ! -d "./volumes" ]; then
    echo -e "${RED}Error: volumes directory not found.${NC}"
    echo -e "${RED}Please run this script from the k8s directory.${NC}"
    exit 1
fi

# Check if sudo is available
if ! sudo -n true 2>/dev/null; then
    echo -e "${YELLOW}This script requires sudo privileges to clean volume files.${NC}"
    echo -e "${YELLOW}You may be prompted for your password.${NC}"
    echo
fi

# Start the interactive menu
main_menu

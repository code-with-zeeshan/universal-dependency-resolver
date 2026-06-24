#!/bin/bash
# Shared utilities for scripts/ — source this file with: source "$(dirname "$0")/common.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
print_success() { echo -e "${GREEN}[OK]${NC}    $*"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
print_error()   { echo -e "${RED}[FAIL]${NC}  $*"; }

check_root_dir() {
    if [ ! -f "docker-compose.yml" ]; then
        print_error "Please run this script from the project root directory"
        exit 1
    fi
}

check_dependency() {
    if ! command -v "$1" &>/dev/null; then
        print_error "$1 is not installed. Please install $1 first."
        exit 1
    fi
}

upload_to_cloud() {
    local file="$1" prefix="${2:-udr-backups}"
    [ -z "$BACKUP_STORAGE" ] && return 0
    case "$BACKUP_STORAGE" in
        cloudflare-r2) rclone copy "$file" "cloudflare-r2:$prefix/" ;;
        gdrive)        rclone copy "$file" "gdrive:$prefix/" ;;
        backblaze)     rclone copy "$file" "b2:$prefix/" ;;
        github)
            local size
            size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null)
            if [ "$size" -lt 104857600 ]; then
                git add "$file"
                git commit -m "Automated backup $(date +%Y%m%d_%H%M%S)"
                git push
            else
                print_warning "File too large for GitHub (>100MB)"
            fi
            ;;
    esac
}

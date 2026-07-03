#!/usr/bin/env bash
set -euo pipefail

# Universal Dependency Resolver — One-command install
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/code-with-zeeshan/universal-dependency-resolver/main/install.sh)

APP="UDR (Universal Dependency Resolver)"
COLOR_CYAN="\033[0;36m"
COLOR_GREEN="\033[0;32m"
COLOR_YELLOW="\033[1;33m"
COLOR_RED="\033[0;31m"
COLOR_RESET="\033[0m"

info()  { echo -e "${COLOR_CYAN}[INFO]${COLOR_RESET} $*"; }
ok()    { echo -e "${COLOR_GREEN}[OK]${COLOR_RESET}   $*"; }
warn()  { echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"; }
fail()  { echo -e "${COLOR_RED}[FAIL]${COLOR_RESET} $*"; exit 1; }

get_version() {
  if command -v udr &>/dev/null; then
    udr --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' || echo "unknown"
  elif [[ -f pyproject.toml ]]; then
    grep -m1 '^version' pyproject.toml | sed 's/version = "\(.*\)"/\1/' || echo "unknown"
  else
    echo "unknown"
  fi
}

install_from_source() {
  VERSION=$(get_version)
  info "Installing from source (v$VERSION)..."
  python3 -m venv venv
  source venv/bin/activate
  pip install --quiet -e "."
  ok "Backend installed"
  echo
  ok "$APP v$VERSION installed!"
  echo
  echo "Usage:"
  echo "  source venv/bin/activate"
  echo "  udr resolve numpy pandas --json"
  echo "  udr check --deps requirements.txt"
  echo "  udr --help"
}

main() {
  VERSION=$(get_version)
  echo
  echo "========================================"
  echo "  $APP v$VERSION"
  echo "  Universal cross-ecosystem dependency resolver"
  echo "========================================"
  echo

  if ! command -v python3 &>/dev/null; then
    fail "Python 3.11+ is required. Install it first: https://www.python.org/downloads/"
  fi

  # Quick install via pip
  if [[ ! -f pyproject.toml ]]; then
    info "Installing from PyPI..."
    pip install ud-resolver
    VERSION=$(get_version)
    ok "$APP v$VERSION installed!"
    ok "Run 'udr --help' to get started."
    exit 0
  fi

  # Source install for contributors
  install_from_source
}

main "$@"

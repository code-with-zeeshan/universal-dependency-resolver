#!/usr/bin/env bash
set -euo pipefail

# Universal Dependency Resolver — One-command install
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/code-with-zeeshan/universal-dependency-resolver/main/install.sh)

APP="UDR (Universal Dependency Resolver)"
VERSION="1.1.0"
COLOR_CYAN="\033[0;36m"
COLOR_GREEN="\033[0;32m"
COLOR_YELLOW="\033[1;33m"
COLOR_RED="\033[0;31m"
COLOR_RESET="\033[0m"

info()  { echo -e "${COLOR_CYAN}[INFO]${COLOR_RESET} $*"; }
ok()    { echo -e "${COLOR_GREEN}[OK]${COLOR_RESET}   $*"; }
warn()  { echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"; }
fail()  { echo -e "${COLOR_RED}[FAIL]${COLOR_RESET} $*"; exit 1; }

detect_package_manager() {
  if command -v brew &>/dev/null; then echo "brew"
  elif command -v apt-get &>/dev/null; then echo "apt"
  elif command -v dnf &>/dev/null; then echo "dnf"
  elif command -v yum &>/dev/null; then echo "yum"
  elif command -v pacman &>/dev/null; then echo "pacman"
  elif command -v choco &>/dev/null; then echo "choco"
  else echo "unknown"; fi
}

install_system_deps() {
  local pm=$(detect_package_manager)
  case "$pm" in
    brew)
      brew install python@3.12 node postgresql redis 2>/dev/null || true
      ;;
    apt)
      sudo apt-get update -qq
      sudo apt-get install -y -qq python3.12 python3.12-venv python3-pip nodejs npm postgresql postgresql-client redis-server 2>/dev/null || true
      ;;
    dnf|yum)
      sudo "$pm" install -y python3.12 python3-pip nodejs npm postgresql redis 2>/dev/null || true
      ;;
    pacman)
      sudo pacman -S --noconfirm python python-pip nodejs npm postgresql redis 2>/dev/null || true
      ;;
    choco)
      choco install python nodejs postgresql redis-64 -y 2>/dev/null || true
      ;;
    *)
      warn "No package manager detected. Please install Python 3.11+, Node.js 18+, PostgreSQL 15+, and Redis 7+ manually."
      ;;
  esac
}

install_docker() {
  if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
    return 0
  fi
  warn "Docker not found."
  read -rp "Install Docker? (y/N): " ans
  if [[ "$ans" =~ ^[Yy] ]]; then
    curl -fsSL https://get.docker.com | sh
    ok "Docker installed"
  fi
}

setup_docker() {
  echo
  info "Starting $APP via Docker Compose..."
  docker compose up -d --build
  docker compose exec backend alembic upgrade head 2>/dev/null || warn "Migration skipped (DB may not be ready yet)"
  echo
  ok "$APP is running!"
  echo "  Frontend: http://localhost:8080"
  echo "  API:      http://localhost:8000/api/v1/docs"
  echo
  echo "Run 'docker compose logs -f' to follow logs."
  echo "Run 'docker compose down' to stop."
}

setup_manual() {
  echo
  info "Setting up $APP manually..."

  # Backend
  info "Installing Python backend..."
  python3 -m venv venv
  source venv/bin/activate
  pip install --quiet -e ".[all]" 2>/dev/null || pip install --quiet -r backend/requirements.txt
  ok "Backend installed"

  # Frontend
  info "Installing Node.js frontend..."
  cd frontend
  npm install --silent 2>/dev/null
  npm run build 2>/dev/null
  cd ..
  ok "Frontend built"

  # Database
  info "Setting up database..."
  if command -v createdb &>/dev/null; then
    createdb udr 2>/dev/null || warn "Database 'udr' may already exist"
  fi
  alembic upgrade head 2>/dev/null || warn "Migration skipped"

  echo
  ok "$APP installed!"
  echo
  echo "To start:"
  echo "  1. Start PostgreSQL and Redis"
  echo "  2. source venv/bin/activate"
  echo "  3. uvicorn backend.api.main:app --port 8000 &"
  echo "  4. cd frontend && npm run serve"
  echo
  echo "Or use 'docker compose up' instead."
}

main() {
  echo
  echo "========================================"
  echo "  $APP v$VERSION"
  echo "  Universal cross-ecosystem dependency resolver"
  echo "========================================"
  echo

  # Check git repo
  if [ ! -f "pyproject.toml" ] && [ ! -f "backend/cli.py" ]; then
    warn "Not in the project directory. Cloning..."
    git clone https://github.com/code-with-zeeshan/universal-dependency-resolver.git
    cd universal-dependency-resolver
  fi

  # Detect available tools
  HAS_PYTHON=$(command -v python3 &>/dev/null && echo 1 || echo 0)
  HAS_NODE=$(command -v node &>/dev/null && echo 1 || echo 0)
  HAS_DOCKER=$(command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1 && echo 1 || echo 0)
  HAS_NPM=$(command -v npm &>/dev/null && echo 1 || echo 0)

  echo "Detected: Python=$HAS_PYTHON Node=$HAS_NODE NPM=$HAS_NPM Docker=$HAS_DOCKER"
  echo

  # Choose install method
  if [ "$HAS_DOCKER" = "1" ]; then
    info "Docker Compose available — this is the easiest path."
    read -rp "Install via Docker? (Y/n): " ans
    if [[ ! "$ans" =~ ^[Nn] ]]; then
      setup_docker
      exit 0
    fi
  fi

  if [ "$HAS_PYTHON" = "0" ] || [ "$HAS_NODE" = "0" ]; then
    warn "Missing Python or Node.js. Attempting to install system dependencies..."
    install_system_deps
  fi

  if command -v python3 &>/dev/null && command -v node &>/dev/null; then
    setup_manual
  else
    fail "Could not install dependencies. Please install Python 3.11+ and Node.js 18+ manually."
  fi
}

main "$@"

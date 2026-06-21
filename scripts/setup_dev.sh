#!/bin/bash
set -e

echo "🚀 Setting up Universal Dependency Resolver development environment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running from project root
if [ ! -f "docker-compose.yml" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

# Check dependencies
print_status "Checking dependencies..."

# Check Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.9+ first."
    exit 1
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    print_error "Node.js is not installed. Please install Node.js 16+ first."
    exit 1
fi

print_success "All dependencies found!"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    print_status "Creating .env file from template..."
    cp .env.example .env
    print_warning "Please update .env file with your configuration"
fi

# Setup backend
print_status "Setting up backend environment..."
cd backend

# Create virtual environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-asyncio pytest-cov black flake8 mypy safety bandit pre-commit

print_success "Backend environment setup complete!"

# Setup frontend
cd ../frontend
print_status "Setting up frontend environment..."

# Install dependencies
npm install

# Install development dependencies
npm install --save-dev eslint prettier @vue/cli-service

print_success "Frontend environment setup complete!"

# Go back to project root
cd ..

# Setup pre-commit hooks
print_status "Setting up pre-commit hooks..."
cd backend
source venv/bin/activate
pre-commit install
cd ..

# Setup database
print_status "Setting up database..."
docker-compose up -d db redis

# Wait for database to be ready
print_status "Waiting for database to be ready..."
sleep 10

# Run migrations
print_status "Running database migrations..."
cd backend
source venv/bin/activate
alembic upgrade head
cd ..

print_success "Database setup complete!"

# Create initial test data (optional)
read -p "Do you want to create initial test data? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Creating initial test data..."
    cd backend
    source venv/bin/activate
    python scripts/create_test_data.py
    cd ..
    print_success "Test data created!"
fi

# Build and start all services
print_status "Building and starting all services..."
docker-compose up -d --build

# Wait for services to be ready
print_status "Waiting for services to start..."
sleep 30

# Check if services are running
if curl -f http://localhost:8000/api/v1/health &> /dev/null; then
    print_success "Backend is running at http://localhost:8000"
else
    print_warning "Backend may not be ready yet. Check docker-compose logs backend"
fi

if curl -f http://localhost:8080 &> /dev/null; then
    print_success "Frontend is running at http://localhost:8080"
else
    print_warning "Frontend may not be ready yet. Check docker-compose logs frontend"
fi

print_success "🎉 Development environment setup complete!"
echo
echo "Quick start commands:"
echo "  - Start services: docker-compose up -d"
echo "  - Stop services: docker-compose down"
echo "  - View logs: docker-compose logs -f"
echo "  - Run tests: ./scripts/run_tests.sh"
echo "  - Backend URL: http://localhost:8000"
echo "  - Frontend URL: http://localhost:8080"
echo "  - API Docs: http://localhost:8000/api/v1/docs"
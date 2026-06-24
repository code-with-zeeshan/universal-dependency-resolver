#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"

echo "🚀 Setting up Universal Dependency Resolver development environment..."

check_root_dir
check_dependency docker
check_dependency python3
check_dependency node
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

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov black flake8 mypy safety bandit pre-commit
print_success "Backend environment setup complete!"

# Setup frontend
cd ../frontend
print_status "Setting up frontend environment..."
npm install
npm install --save-dev eslint prettier @vue/cli-service
print_success "Frontend environment setup complete!"

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
print_status "Waiting for database to be ready..."
sleep 10

print_status "Running database migrations..."
cd backend
source venv/bin/activate
alembic upgrade head
cd ..
print_success "Database setup complete!"

# Build and start all services
print_status "Building and starting all services..."
docker-compose up -d --build
print_status "Waiting for services to start..."
sleep 30

if curl -f http://localhost:8000/api/v1/health &>/dev/null; then
    print_success "Backend is running at http://localhost:8000"
else
    print_warning "Backend may not be ready yet. Check docker-compose logs backend"
fi

if curl -f http://localhost:8080 &>/dev/null; then
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

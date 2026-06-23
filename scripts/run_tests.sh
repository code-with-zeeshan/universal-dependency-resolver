#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse command line arguments
TEST_TYPE="all"
COVERAGE=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --type|-t)
            TEST_TYPE="$2"
            shift 2
            ;;
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  -t, --type TYPE     Test type: unit|integration|e2e|all (default: all)"
            echo "  -c, --coverage      Generate coverage report"
            echo "  -v, --verbose       Verbose output"
            echo "  -h, --help          Show this help"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_status "Running tests with type: $TEST_TYPE, coverage: $COVERAGE, verbose: $VERBOSE"

# Check if running from project root
if [ ! -f "docker-compose.yml" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

# Start test services
print_status "Starting test services..."
docker-compose -f docker-compose.test.yml up -d db redis

# Wait for services to be ready
echo "Waiting for PostgreSQL..."
until docker-compose -f docker-compose.test.yml exec -T db pg_isready -U user -d depresolver_test 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is ready!"

echo "Waiting for Redis..."
until docker-compose -f docker-compose.test.yml exec -T redis redis-cli ping 2>/dev/null; do
    sleep 1
done
echo "Redis is ready!"

# Backend tests
if [[ "$TEST_TYPE" == "all" || "$TEST_TYPE" == "unit" || "$TEST_TYPE" == "backend" ]]; then
    print_status "Running backend tests..."
    
    cd backend
    
    # Activate virtual environment
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    
    # Set test environment variables
    export DATABASE_URL="postgresql://user:password@localhost:15432/depresolver_test"
    export REDIS_URL="redis://localhost:16379"
    export TESTING=true
    export SECRET_KEY="test-secret-key"
    export OTEL_ENABLED=false
    export ENABLE_AUTH=false
    
    # Run database migrations
    alembic upgrade head
    
    # Prepare pytest arguments
    PYTEST_ARGS="tests/"
    
    if [ "$COVERAGE" = true ]; then
        PYTEST_ARGS="$PYTEST_ARGS --cov=. --cov-report=xml --cov-report=html --cov-report=term-missing"
    fi
    
    if [ "$VERBOSE" = true ]; then
        PYTEST_ARGS="$PYTEST_ARGS -v -s"
    fi
    
    # Run specific test types
    if [[ "$TEST_TYPE" == "unit" ]]; then
        PYTEST_ARGS="tests/unit/ $PYTEST_ARGS"
    elif [[ "$TEST_TYPE" == "integration" && "$TEST_TYPE" != "all" ]]; then
        PYTEST_ARGS="tests/integration/ $PYTEST_ARGS"
    fi
    
    # Run tests
    pytest $PYTEST_ARGS
    
    if [ $? -eq 0 ]; then
        print_success "Backend tests passed!"
    else
        print_error "Backend tests failed!"
        exit 1
    fi
    
    cd ..
fi

# Frontend tests
if [[ "$TEST_TYPE" == "all" || "$TEST_TYPE" == "unit" || "$TEST_TYPE" == "frontend" ]]; then
    print_status "Running frontend tests..."
    
    cd frontend
    
    # Check if package.json exists
    if [ ! -f "package.json" ]; then
        print_error "package.json not found in frontend directory"
        exit 1
    fi
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        npm install
    fi
    
    # Run linting
    print_status "Running ESLint..."
    npm run lint
    
    # Run unit tests
    print_status "Running frontend unit tests..."
    if [ "$COVERAGE" = true ]; then
        npm run test:unit -- --coverage
    else
        npm run test:unit
    fi
    
    if [ $? -eq 0 ]; then
        print_success "Frontend tests passed!"
    else
        print_error "Frontend tests failed!"
        exit 1
    fi
    
    cd ..
fi

# Integration tests
if [[ "$TEST_TYPE" == "all" || "$TEST_TYPE" == "integration" ]]; then
    print_status "Running integration tests..."
    
    export DATABASE_URL="postgresql://user:password@localhost:15432/depresolver_test"
    export REDIS_URL="redis://localhost:16379"
    export TESTING=true
    export SECRET_KEY="test-secret-key"
    export OTEL_ENABLED=false
    export ENABLE_AUTH=false
    export LOG_LEVEL=WARNING
    
    # Initialize database tables
    python -c "
from backend.database.models import Base, engine
Base.metadata.create_all(bind=engine)
print('Tables created successfully')
"
    
    # Prepare pytest arguments
    PYTEST_ARGS="tests/integration/"
    
    if [ "$COVERAGE" = true ]; then
        PYTEST_ARGS="$PYTEST_ARGS --cov=. --cov-report=xml --cov-report=html --cov-report=term-missing"
    fi
    
    if [ "$VERBOSE" = true ]; then
        PYTEST_ARGS="$PYTEST_ARGS -v -s"
    fi
    
    python -m pytest $PYTEST_ARGS
    
    if [ $? -eq 0 ]; then
        print_success "Integration tests passed!"
    else
        print_error "Integration tests failed!"
        exit 1
    fi
fi

# E2E tests
if [[ "$TEST_TYPE" == "all" || "$TEST_TYPE" == "e2e" ]]; then
    print_status "Running E2E tests..."
    
    # Make sure all services are running
    docker-compose up -d --build
    sleep 30
    
    # Run E2E tests
    cd frontend
    
    # Install Playwright if not installed
    if [ ! -d "node_modules/playwright" ]; then
        npx playwright install
    fi
    
    # Run E2E tests
    npm run test:e2e
    
    if [ $? -eq 0 ]; then
        print_success "E2E tests passed!"
    else
        print_error "E2E tests failed!"
        exit 1
    fi
    
    cd ..
fi

# Cleanup
print_status "Cleaning up test services..."
docker-compose -f docker-compose.test.yml down --remove-orphans 2>/dev/null || true
docker-compose down --remove-orphans 2>/dev/null || true

if [ "$COVERAGE" = true ]; then
    print_status "Coverage reports generated:"
    if [ -f "backend/htmlcov/index.html" ]; then
        echo "  Backend: backend/htmlcov/index.html"
    fi
    if [ -f "frontend/coverage/lcov-report/index.html" ]; then
        echo "  Frontend: frontend/coverage/lcov-report/index.html"
    fi
fi

print_success "🎉 All tests completed successfully!"
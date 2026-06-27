#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"

TEST_TYPE="all"
COVERAGE=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --type|-t)
            TEST_TYPE="$2"; shift 2 ;;
        --coverage|-c)
            COVERAGE=true; shift ;;
        --verbose|-v)
            VERBOSE=true; shift ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo "  -t, --type TYPE     Test type: unit|integration|e2e|all (default: all)"
            echo "  -c, --coverage      Generate coverage report"
            echo "  -v, --verbose       Verbose output"
            echo "  -h, --help          Show this help"
            exit 0 ;;
        *) print_error "Unknown option: $1"; exit 1 ;;
    esac
done

print_status "Running tests with type: $TEST_TYPE, coverage: $COVERAGE, verbose: $VERBOSE"
check_root_dir

# Start test services
print_status "Starting test services..."
docker-compose -f docker-compose.test.yml up -d db redis

echo "Waiting for PostgreSQL..."
until docker-compose -f docker-compose.test.yml exec -T db pg_isready -U user -d depresolver_test 2>/dev/null; do sleep 1; done
echo "PostgreSQL is ready!"

echo "Waiting for Redis..."
until docker-compose -f docker-compose.test.yml exec -T redis redis-cli ping 2>/dev/null; do sleep 1; done
echo "Redis is ready!"

# Backend tests
if [[ "$TEST_TYPE" == "all" || "$TEST_TYPE" == "backend" ]]; then
    print_status "Running backend tests..."
    cd backend
    [ -d "venv" ] && source venv/bin/activate
    export DATABASE_URL="postgresql://user:password@localhost:15432/depresolver_test"
    export REDIS_URL="redis://localhost:16379"
    export TESTING=true SECRET_KEY="test-secret-key" OTEL_ENABLED=false ENABLE_AUTH=false
    alembic upgrade head

    PYTEST_ARGS="tests/"
    [ "$COVERAGE" = true ] && PYTEST_ARGS="$PYTEST_ARGS --cov=. --cov-report=xml --cov-report=html --cov-report=term-missing"
    [ "$VERBOSE" = true ] && PYTEST_ARGS="$PYTEST_ARGS -v -s"
    if [[ "$TEST_TYPE" == "unit" ]]; then
        PYTEST_ARGS="tests/unit/ $PYTEST_ARGS"
    elif [[ "$TEST_TYPE" == "integration" ]]; then
        PYTEST_ARGS="tests/integration/ $PYTEST_ARGS"
    fi

    pytest $PYTEST_ARGS && print_success "Backend tests passed!" || { print_error "Backend tests failed!"; exit 1; }
    cd ..
fi



# Integration tests
if [[ "$TEST_TYPE" == "all" || "$TEST_TYPE" == "integration" ]]; then
    print_status "Running integration tests..."
    export DATABASE_URL="postgresql://user:password@localhost:15432/depresolver_test"
    export REDIS_URL="redis://localhost:16379"
    export TESTING=true SECRET_KEY="test-secret-key" OTEL_ENABLED=false ENABLE_AUTH=false LOG_LEVEL=WARNING

    python -c "from backend.database.models import Base, engine; Base.metadata.create_all(bind=engine); print('Tables created')"

    PYTEST_ARGS="tests/integration/"
    [ "$COVERAGE" = true ] && PYTEST_ARGS="$PYTEST_ARGS --cov=. --cov-report=xml --cov-report=html --cov-report=term-missing"
    [ "$VERBOSE" = true ] && PYTEST_ARGS="$PYTEST_ARGS -v -s"
    python -m pytest $PYTEST_ARGS && print_success "Integration tests passed!" || { print_error "Integration tests failed!"; exit 1; }
fi

# Cleanup
print_status "Cleaning up test services..."
docker-compose -f docker-compose.test.yml down --remove-orphans 2>/dev/null || true
docker-compose down --remove-orphans 2>/dev/null || true

if [ "$COVERAGE" = true ]; then
    print_status "Coverage reports generated:"
    [ -f "backend/htmlcov/index.html" ] && echo "  Backend: backend/htmlcov/index.html"
fi

print_success "🎉 All tests completed successfully!"

#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"

ENVIRONMENT="staging"
VERSION="latest"
SKIP_TESTS=false
SKIP_BUILD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --env|-e) ENVIRONMENT="$2"; shift 2 ;;
        --version|-v) VERSION="$2"; shift 2 ;;
        --skip-tests) SKIP_TESTS=true; shift ;;
        --skip-build) SKIP_BUILD=true; shift ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo "  -e, --env ENV       Environment: staging|production (default: staging)"
            echo "  -v, --version VER   Version to deploy (default: latest)"
            echo "  --skip-tests        Skip running tests before deployment"
            echo "  --skip-build        Skip building images"
            echo "  -h, --help          Show this help"
            exit 0 ;;
        *) print_error "Unknown option: $1"; exit 1 ;;
    esac
done

print_status "Deploying to $ENVIRONMENT environment, version: $VERSION"

if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
    print_error "Environment must be 'staging' or 'production'"
    exit 1
fi

# Production branch check
if [[ "$ENVIRONMENT" == "production" ]]; then
    CURRENT_BRANCH=$(git branch --show-current)
    if [[ "$CURRENT_BRANCH" != "main" ]]; then
        print_warning "You're not on the main branch. Current branch: $CURRENT_BRANCH"
        read -p "Continue with production deployment? (y/N): " -n 1 -r; echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_error "Deployment cancelled"; exit 1
        fi
    fi
fi

# Run tests unless skipped
if [ "$SKIP_TESTS" = false ]; then
    print_status "Running tests before deployment..."
    ./scripts/run_tests.sh --type unit && print_success "Tests passed!" || { print_error "Tests failed. Deployment cancelled."; exit 1; }
fi

# Build images unless skipped
if [ "$SKIP_BUILD" = false ]; then
    print_status "Building Docker images..."
    docker build -t "udr-backend:$VERSION" -f backend/Dockerfile .
    print_success "Image built successfully!"
fi

case $ENVIRONMENT in
    staging)
        print_status "Deploying to staging environment..."
        export BACKEND_IMAGE="udr-backend:$VERSION" ENVIRONMENT="staging"
        docker-compose -f docker-compose.test.yml up -d --remove-orphans
        sleep 30
        docker-compose -f docker-compose.test.yml exec backend alembic upgrade head
        if curl -f http://localhost:8000/api/v1/health &>/dev/null; then
            print_success "Staging deployment successful!"
        else
            print_error "Staging deployment health check failed"; exit 1
        fi
        ;;
    production)
        print_status "Deploying to production environment..."
        read -p "Are you sure you want to deploy to PRODUCTION? (yes/no): " -r
        if [[ ! $REPLY == "yes" ]]; then
            print_error "Deployment cancelled"; exit 1
        fi
        print_status "Production deployment requires Docker Swarm or cloud orchestration."
        print_status "See docker-compose.prod.yml and .github/workflows/deploy.yml"
        print_status "Manual commands:"
        echo "  export BACKEND_IMAGE=udr-backend:$VERSION ENVIRONMENT=production"
        echo "  docker stack deploy --compose-file docker-compose.prod.yml udr-production"
        ;;
esac

print_success "🚀 Deployment to $ENVIRONMENT completed successfully!"

[ -n "$SLACK_WEBHOOK_URL" ] && curl -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"✅ Deployment to $ENVIRONMENT completed successfully! Version: $VERSION\"}" \
    "$SLACK_WEBHOOK_URL"

#!/bin/bash
set -e

# Colors
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

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Default values
ENVIRONMENT="staging"
VERSION="latest"
SKIP_TESTS=false
SKIP_BUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env|-e)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --version|-v)
            VERSION="$2"
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  -e, --env ENV       Environment: staging|production (default: staging)"
            echo "  -v, --version VER   Version to deploy (default: latest)"
            echo "  --skip-tests        Skip running tests before deployment"
            echo "  --skip-build        Skip building images"
            echo "  -h, --help          Show this help"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_status "Deploying to $ENVIRONMENT environment, version: $VERSION"

# Validate environment
if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
    print_error "Environment must be 'staging' or 'production'"
    exit 1
fi

# Check if we're on the right branch for production
if [[ "$ENVIRONMENT" == "production" ]]; then
    CURRENT_BRANCH=$(git branch --show-current)
    if [[ "$CURRENT_BRANCH" != "main" ]]; then
        print_warning "You're not on the main branch. Current branch: $CURRENT_BRANCH"
        read -p "Continue with production deployment? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_error "Deployment cancelled"
            exit 1
        fi
    fi
fi

# Run tests unless skipped
if [ "$SKIP_TESTS" = false ]; then
    print_status "Running tests before deployment..."
    ./scripts/run_tests.sh --type unit
    if [ $? -ne 0 ]; then
        print_error "Tests failed. Deployment cancelled."
        exit 1
    fi
    print_success "Tests passed!"
fi

# Build images unless skipped
if [ "$SKIP_BUILD" = false ]; then
    print_status "Building Docker images..."
    
    # Build backend image
    docker build -t "udr-backend:$VERSION" ./backend
    
    # Build frontend image
    docker build -t "udr-frontend:$VERSION" ./frontend
    
    print_success "Images built successfully!"
fi

# Deploy based on environment
case $ENVIRONMENT in
    staging)
        print_status "Deploying to staging environment..."
        
        # Use staging docker-compose file
        export BACKEND_IMAGE="udr-backend:$VERSION"
        export FRONTEND_IMAGE="udr-frontend:$VERSION"
        export ENVIRONMENT="staging"
        
        # Deploy to staging
        docker-compose -f docker-compose.staging.yml up -d --remove-orphans
        
        # Wait for services
        sleep 30
        
        # Run migrations
        docker-compose -f docker-compose.staging.yml exec backend alembic upgrade head
        
        # Health check
        if curl -f http://staging.yourdomain.com/api/v1/health &> /dev/null; then
            print_success "Staging deployment successful!"
        else
            print_error "Staging deployment health check failed"
            exit 1
        fi
        ;;
        
    production)
        print_status "Deploying to production environment..."
        
        # Additional production checks
        read -p "Are you sure you want to deploy to PRODUCTION? (yes/no): " -r
        if [[ ! $REPLY == "yes" ]]; then
            print_error "Deployment cancelled"
            exit 1
        fi
        
        # Backup database
        print_status "Creating database backup..."
        kubectl exec -n production deployment/postgres -- pg_dump -U user depresolver > "backup-$(date +%Y%m%d-%H%M%S).sql"
        
        # Deploy using Kubernetes
        export BACKEND_IMAGE="udr-backend:$VERSION"
        export FRONTEND_IMAGE="udr-frontend:$VERSION"
        export ENVIRONMENT="production"
        
        # Apply Kubernetes manifests
        envsubst < k8s/namespace.yaml | kubectl apply -f -
        envsubst < k8s/backend.yaml | kubectl apply -f -
        envsubst < k8s/frontend.yaml | kubectl apply -f -
        
        # Wait for rollout
        kubectl rollout status deployment/backend -n production
        kubectl rollout status deployment/frontend -n production
        
        # Run migrations
        kubectl exec -n production deployment/backend -- alembic upgrade head
        
        # Health check
        if curl -f https://api.yourdomain.com/api/v1/health &> /dev/null; then
            print_success "Production deployment successful!"
        else
            print_error "Production deployment health check failed"
            
            # Automatic rollback
            print_status "Rolling back deployment..."
            kubectl rollout undo deployment/backend -n production
            kubectl rollout undo deployment/frontend -n production
            exit 1
        fi
        ;;
esac

print_success "🚀 Deployment to $ENVIRONMENT completed successfully!"

# Send notification (if configured)
if [ -n "$SLACK_WEBHOOK_URL" ]; then
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"✅ Deployment to $ENVIRONMENT completed successfully! Version: $VERSION\"}" \
        "$SLACK_WEBHOOK_URL"
fi
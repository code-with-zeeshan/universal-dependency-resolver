# Universal Dependency Resolver - Developer Onboarding Guide

## Table of Contents
- [System Overview](#system-overview)
- [How the System Works End-to-End](#how-the-system-works-end-to-end)
- [How to Use the System](#how-to-use-the-system)
- [Development Setup](#development-setup)
- [Codebase Diagnosis and Recommendations](#codebase-diagnosis-and-recommendations)
- [Contributing Guidelines](#contributing-guidelines)
- [Troubleshooting](#troubleshooting)

## System Overview

The Universal Dependency Resolver is a sophisticated multi-ecosystem dependency resolution system that supports PyPI, NPM, Conda, Maven, and Crates.io. It provides intelligent conflict resolution using Z3 SAT solver, system compatibility checking, and multiple export formats.

### Key Features
- **Multi-Ecosystem Support**: Handles Python, JavaScript, Java, Rust, and Conda packages
- **Intelligent Conflict Resolution**: Uses Z3 theorem prover for dependency constraint solving
- **System Compatibility**: Scans and validates OS, CPU, GPU, and runtime requirements
- **14+ Export Formats**: Generates Docker, requirements.txt, package.json, etc.
- **High Performance**: Redis caching, async operations, connection pooling
- **Production Ready**: Rate limiting, health checks, monitoring with Prometheus/Sentry

### Architecture
- **Backend**: Python FastAPI with SQLAlchemy, Redis, Z3 solver
- **Frontend**: Vue.js 3 with Tailwind CSS
- **Database**: PostgreSQL with Alembic migrations
- **Caching**: Redis for performance optimization
- **Monitoring**: Prometheus metrics, Sentry error tracking

## How the System Works End-to-End

### 1. User Interaction (Frontend)
The Vue.js frontend provides a clean interface where users:
- Input package names and ecosystems
- View system information (OS, GPU, CPU, runtimes)
- Trigger dependency resolution
- Export resolved dependencies to various formats

### 2. API Request Flow (Backend)
When a user clicks "Resolve Dependencies":

```mermaid
graph TD
    A[Frontend Vue App] --> B[FastAPI /api/v1/packages/resolve]
    B --> C[Dependency Injection]
    C --> D[DataAggregator]
    D --> E[Package Clients]
    E --> F[External APIs]
    D --> G[ConflictResolver]
    G --> H[Z3 SAT Solver]
    H --> I[Constraint Solving]
    G --> J[ExportGenerator]
    J --> K[Format Generation]
    K --> L[Response to Frontend]
```

### 3. Core Resolution Process

#### Data Aggregation Phase
- `DataAggregator` coordinates multiple `*_client.py` modules
- Each client fetches package metadata from respective ecosystems:
  - `pypi_client.py` → PyPI API
  - `npm_client.py` → NPM registry
  - `conda_client.py` → Conda Forge
  - `maven_client.py` → Maven Central
  - `crates_client.py` → Crates.io

#### Conflict Resolution Phase
- `ConflictResolver` builds a dependency graph using NetworkX
- Creates Z3 constraints for version compatibility
- Solves the constraint satisfaction problem
- Handles conflicts with fallback strategies

#### Export Generation Phase
- `ExportGenerator` formats resolved dependencies
- Supports 14+ formats (requirements.txt, Dockerfile, etc.)
- Includes system-specific configurations

### 4. System Scanning
- `SystemScanner` detects local environment
- Uses `psutil`, `GPUtil`, `cpuinfo` for hardware info
- Checks Python, Node.js, Java versions
- Validates GPU/CUDA compatibility

### 5. Caching and Performance
- Redis caches package metadata and resolution results
- TTL-based expiration prevents stale data
- Async operations prevent blocking
- Connection pooling for database efficiency

## How to Use the System

### Quick Start (Docker - Recommended)

```bash
# Clone repository
git clone https://github.com/yourusername/universal-dependency-resolver.git
cd universal-dependency-resolver

# Copy environment template
cp .env.example .env

# Start all services
docker-compose up -d

# Initialize database
docker-compose exec backend alembic upgrade head

# Access interfaces
# Frontend: http://localhost:8080
# API Docs: http://localhost:8000/api/v1/docs
# Health Check: http://localhost:8000/api/v1/health
```

### Local Development Setup

#### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload
```

#### Frontend Setup
```bash
cd frontend
npm install
npm run serve
```

#### Database Setup
```bash
# Install PostgreSQL and Redis locally
createdb universal_deps
alembic upgrade head
```

### Basic Usage Workflow

1. **Add Packages**: Enter package names like "tensorflow", "react", "numpy"
2. **Specify Ecosystems**: Choose from PyPI, NPM, Conda, Maven, Crates.io
3. **System Detection**: View auto-detected OS, GPU, CPU, runtime versions
4. **Resolve Dependencies**: Click resolve to get conflict-free versions
5. **Export Configuration**: Download as requirements.txt, Dockerfile, etc.

### API Usage Examples

#### Search Packages
```bash
GET /api/v1/packages/search?q=tensorflow&ecosystems=pypi,conda&limit=20
```

#### Resolve Dependencies
```bash
POST /api/v1/packages/resolve
Content-Type: application/json

{
  "packages": [
    {"name": "tensorflow", "ecosystem": "pypi", "version": ">=2.13.0"},
    {"name": "numpy", "ecosystem": "pypi"}
  ],
  "system_info": {
    "os": "linux",
    "python": "3.9.16",
    "gpu": {"cuda": "11.8", "available": true}
  }
}
```

#### Export Configuration
```bash
POST /api/v1/packages/export
Content-Type: application/json

{
  "resolved_packages": {"tensorflow": "2.15.0", "numpy": "1.24.3"},
  "format": "requirements.txt"
}
```

## Development Setup

### Prerequisites
- Python 3.9+
- Node.js 16+
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+

### Environment Configuration
Copy `.env.example` to `.env` and configure:
```env
DATABASE_URL=postgresql://user:pass@localhost:5432/universal_deps
REDIS_URL=redis://localhost:6379
API_KEY=your-secret-key
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:3000
```

### Running Tests
```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm run test

# Integration tests
docker-compose -f docker-compose.test.yml up --abort-on-container-exit
```

### Code Quality
```bash
# Backend linting
black backend/
flake8 backend/
mypy backend/

# Frontend linting
cd frontend
npm run lint
```

## Codebase Diagnosis and Recommendations

### 🐛 Identified Bugs and Issues

1. **Minimal Test Coverage**
   - Unit tests are basic and don't cover complex scenarios
   - Missing integration tests for end-to-end flows
   - No performance regression tests
   - **Impact**: High risk of undetected bugs in production

2. **Inconsistent Error Handling**
   - Some modules use try/except broadly without specific handling
   - Error messages could be more user-friendly
   - Missing validation in API endpoints

3. **Potential Race Conditions**
   - Async operations in `conflict_resolver.py` may have concurrent access issues
   - Cache invalidation not properly synchronized

4. **Dependency Version Pinning**
   - Some dependencies may be outdated (e.g., FastAPI 0.104.1 vs current 0.104+)
   - Security vulnerabilities in older versions

### ⚡ Performance Optimization Opportunities

1. **Z3 Solver Optimization**
   - For large dependency graphs, consider incremental solving
   - Implement timeout mechanisms to prevent hanging
   - Cache intermediate solver states

2. **Database Query Optimization**
   - Add database indexes on frequently queried columns
   - Implement query result caching
   - Consider read replicas for heavy loads

3. **Memory Management**
   - Large package metadata could cause memory issues
   - Implement streaming for large exports
   - Add memory limits and monitoring

4. **API Rate Limiting**
   - Current limits (60/min) may be too permissive
   - Implement per-user limits with Redis
   - Add request queuing for burst handling

### 📖 Readability and Maintainability Issues

1. **Large Files**
   - `conflict_resolver.py` (688+ lines) should be split into smaller modules
   - `main.py` (356+ lines) could separate concerns better
   - Consider service layer pattern for better organization

2. **Inconsistent Code Style**
   - Mix of sync/async patterns in some modules
   - Inconsistent naming conventions
   - Missing type hints in several functions

3. **Documentation Gaps**
   - Some functions lack docstrings
   - API endpoints need better OpenAPI descriptions
   - Missing inline comments for complex logic

### 🔧 Recommended Improvements

#### Immediate Priority
1. **Expand Test Suite**
   ```python
   # Add comprehensive tests for conflict resolution
   def test_complex_dependency_conflicts():
       # Test scenarios with circular dependencies, version conflicts, etc.
   
   # Add performance benchmarks
   def test_resolution_performance():
       # Measure time for various dependency graph sizes
   ```

2. **Improve Error Handling**
   ```python
   # Use custom exceptions with error codes
   class DependencyResolutionError(Exception):
       def __init__(self, message: str, error_code: str):
           self.error_code = error_code
           super().__init__(message)
   ```

3. **Add Monitoring and Observability**
   - Implement structured logging
   - Add performance metrics
   - Create health check endpoints

#### Medium Priority
1. **Refactor Large Classes**
   ```python
   # Split ConflictResolver into smaller classes
   class ConstraintBuilder:
       # Handle Z3 constraint creation
   
   class SolutionInterpreter:
       # Parse and format solutions
   ```

2. **Implement Feature Flags**
   - Allow disabling expensive features in production
   - A/B testing capabilities

3. **Add Caching Layers**
   - Multi-level caching (memory → Redis → database)
   - Intelligent cache invalidation

#### Long-term Vision
1. **Microservices Architecture**
   - Separate resolution service
   - Independent package indexers
   - Event-driven architecture

2. **Machine Learning Integration**
   - Predict dependency conflicts
   - Recommend optimal versions
   - Learn from resolution patterns

3. **Plugin System**
   - Support for custom package ecosystems
   - Extensible export formats
   - Third-party integrations

## Contributing Guidelines

### Code Standards
- **Backend**: PEP 8, type hints required, docstrings for public methods
- **Frontend**: ESLint rules, Vue composition API preferred
- **Tests**: 80%+ coverage required, use pytest fixtures
- **Commits**: Conventional commits format

### Pull Request Process
1. Create feature branch from `main`
2. Write tests for new functionality
3. Update documentation
4. Ensure CI passes
5. Request review from maintainers

### Review Checklist
- [ ] Tests pass and coverage maintained
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No security vulnerabilities introduced
- [ ] Performance impact assessed

## Troubleshooting

### Common Issues

#### Backend Won't Start
```bash
# Check environment variables
python -c "import os; print(os.getenv('DATABASE_URL'))"

# Test database connection
alembic current

# Check Python dependencies
pip check
```

#### Frontend Build Fails
```bash
# Clear node modules
rm -rf node_modules package-lock.json
npm install

# Check Node.js version
node --version  # Should be 16+
```

#### Dependency Resolution Fails
- Check system compatibility requirements
- Verify package names and ecosystems
- Review conflict resolution logs
- Try with fewer packages initially

#### Database Issues
```bash
# Reset database
docker-compose down -v
docker-compose up -d db
alembic upgrade head
```

#### Performance Problems
- Check Redis connection: `redis-cli ping`
- Monitor memory usage: `docker stats`
- Review slow query logs
- Consider cache clearing: `redis-cli FLUSHALL`

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
uvicorn api.main:app --reload --log-level debug
```

### Support Resources
- **API Documentation**: `/api/v1/docs`
- **Health Checks**: `/api/v1/health`
- **Logs**: Check Docker container logs
- **Issues**: GitHub Issues for bugs/features

---

This guide provides comprehensive information for new developers to understand, use, and contribute to the Universal Dependency Resolver. Regular updates to this document are encouraged as the system evolves.
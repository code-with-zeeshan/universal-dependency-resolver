# Universal Dependency Resolver - Complete Architecture Documentation `docs/ARCHITECTURE.md`

## Dependency Flow Tree

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend Layer                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  App.vue                                                │    │
│  │    ├── components/PackageSearch.vue                     │    │
│  │    │     └── services/packageService.js ─────────────┐  │    │
│  │    ├── components/SystemInfo.vue                     │  │    │
│  │    │     └── services/systemService.js ──────────┐   │  │    │
│  │    └── services/auth.js ──────────────────────┐  │   │  │    │
│  │                                                │  │   │  │    │
│  │    utils/validators.js ◄─── used by ───────────┴──┴───┘  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  api/main.py                                            │    │
│  │    ├── api/schemas.py                                   │    │
│  │    ├── api/dependencies.py                              │    │
│  │    ├── api/middleware.py                                │    │
│  │    ├── api/auth.py                                      │    │
│  │    ├── api/exceptions.py                                │    │
│  │    ├── api/routes/packages.py ◄─────────────────────────┤    │
│  │    └── api/routes/system.py ◄───────────────────────────┤    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Core Logic                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  core/conflict_resolver.py  ◄── uses ──┐                │    │
│  │  core/data_aggregator.py  ◄─── uses ───┤                │    │
│  │  core/export_generator.py              │                │    │
│  │  core/system_scanner.py                │                │    │
│  │  core/cache.py ◄──────── used by all ──┤                │    │
│  │  core/utils.py◄────────── used by all ─┘                │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
┌─────────────────────────────┐ ┌─────────────────────────────────┐
│      Data Sources           │ │         Database                │
│  ┌─────────────────────┐    │ │  ┌─────────────────────────┐    │
│  │ base_client.py      │    │ │  │ database/models.py      │    │
│  │ pypi_client.py      │    │ │  │ database/models.py      │    │
│  │ npm_client.py       │    │ │  │database/compatibility_db│    │
│  │ conda_client.py     │    │ │  └─────────────────────────┘    │
│  │ maven_client.py     │    │ │            ▲                    │
│  │ crates_client.py    │    │ │            │                    │
│  │documentation_scraper│    │ │  ┌─────────────────────────┐    │
│  └─────────────────────┘    │ │  │ alembic/env.py          │    │
└─────────────────────────────┘ └─────────────────────────────────┘
```

## File Interconnection Matrix

| File | Imports/Uses | Imported By | Purpose | External Dependencies |
|------|--------------|-------------|---------|----------------------|
| **Frontend** | | | | |
| `App.vue` | PackageSearch, SystemInfo | - | Main Vue app component | Vue framework |
| `components/PackageSearch.vue` | packageService | App.vue | Package search UI | Vue |
| `components/SystemInfo.vue` | systemService | App.vue | System info display | Vue |
| `services/packageService.js` | axios, auth, validators | PackageSearch.vue | API client for packages | axios |
| `services/systemService.js` | axios, auth, validators | SystemInfo.vue | API client for system info | axios |
| `services/auth.js` | axios | packageService, systemService | Authentication utilities | axios |
| `utils/validators.js` | - | All services | Input validation helpers | - |
| **Backend API** | | | | |
| `api/schemas.py` | - | main, dependencies | Pydantic request/response schemas | pydantic |
| `api/dependencies.py` | schemas, database | main | FastAPI dependency injection | FastAPI |
| `api/main.py` | schemas, dependencies, routes/packages, routes/system, middleware, auth, exceptions, settings | - | FastAPI app entry point | FastAPI, uvicorn |
| `api/middleware.py` | exceptions | main.py | Request/response middleware | FastAPI |
| `api/auth.py` | settings | main.py, routes | Authentication logic | FastAPI, JWT |
| `api/exceptions.py` | - | middleware, routes | Custom exception handlers | FastAPI |
| `api/routes/packages.py` | core/data_aggregator, core/conflict_resolver, core/export_generator, database/models, auth | main.py | Package-related endpoints | FastAPI |
| `api/routes/system.py` | core/system_scanner, database/models, auth | main.py | System scan endpoints | FastAPI |
| `settings.py` | - | All backend modules | Configuration management | os.getenv |
| **Core Logic** | | | | |
| `core/conflict_resolver.py` | utils, cache, database/models, database/compatibility_db | routes/packages | Resolves version conflicts | - |
| `core/data_aggregator.py` | All data_sources/*, utils, cache | routes/packages | Aggregates package data | - |
| `core/export_generator.py` | utils | routes/packages | Generates export files | - |
| `core/system_scanner.py` | utils | routes/system | Scans system packages | subprocess, pathlib |
| `core/cache.py` | - | All core modules | Caching layer | Redis/in-memory |
| `core/utils.py` | - | All core modules | Shared utilities | - |
| **Data Sources** | | | | |
| `data_sources/base_client.py` | utils, settings | data_sources/*_client | Base HTTP client with rate limiting | httpx |
| `data_sources/pypi_client.py` | utils, settings, base_client | data_aggregator | PyPI API integration | requests, aiohttp |
| `data_sources/npm_client.py` | utils, settings | data_aggregator | NPM API integration | requests, aiohttp |
| `data_sources/conda_client.py` | utils, settings | data_aggregator | Conda Forge integration | requests, aiohttp |
| `data_sources/maven_client.py` | utils, settings | data_aggregator | Maven Central integration | requests, aiohttp |
| `data_sources/crates_client.py` | utils, settings | data_aggregator | Crates.io integration | requests, aiohttp |
| `data_sources/documentation_scraper.py` | utils | data_aggregator | Scrapes package docs | beautifulsoup4 |
| **Database** | | | | |
| `database/models.py` | - | All modules needing DB | SQLAlchemy models | SQLAlchemy |
| `database/compatibility_db.py` | models | conflict_resolver | Compatibility matrix ops | SQLAlchemy |
| **Infrastructure** | | | | |
| `alembic/env.py` | database/models | - | Database migrations | Alembic |
| `docker-compose.yml` | - | - | Container orchestration | Docker |
| `backend/Dockerfile` | - | - | Backend container config | Docker |
| `frontend/Dockerfile` | - | - | Frontend container config | Docker |
| `nginx.conf` | - | frontend/Dockerfile | Web server config | Nginx |
| `.github/workflows/ci.yml` | - | - | CI pipeline | GitHub Actions |
| `.github/workflows/deploy.yml` | - | - | Deployment pipeline | GitHub Actions |

## Key Integration Points

| Integration Point | Components | Data Flow | Protocol |
|------------------|-------------|-----------|----------|
| Frontend → Backend | Vue services → FastAPI routes | HTTP requests with auth headers | REST API + JWT |
| API Middleware | All routes ← middleware → responses | Request validation, error handling | FastAPI middleware |
| Authentication | Frontend auth.js ↔ Backend auth.py | JWT token exchange | Bearer tokens |
| API → Core Logic | Routes → Core modules | Function calls with caching | Python imports |
| Core → Data Sources | data_aggregator → *_client modules | Async calls with caching | Python async/await |
| Core → Database | All core modules → models/compatibility_db | CRUD operations | SQLAlchemy ORM |
| Core Caching | All core modules → cache.py | In-memory/Redis caching | Cache abstraction |
| Database Migration | Alembic → database/models | Schema updates and versioning | Alembic migrations |
| Container Network | Frontend Nginx → Backend API | Reverse proxy | Docker network |
| CI/CD Pipeline | GitHub → Docker → Deployment | Automated testing & deployment | GitHub Actions |

## Module Dependencies Graph

```
                    .env.example
                         │
settings.py ─────────────┴─────────┐
     │                             │
     ├──────────────┐              │
     ▼              ▼              ▼
utils.py        cache.py      database/
     │              │         models.py
     ▼              ▼              │
data_sources/*  (used by)          │
     │              │              │
     ▼              ▼              ▼
data_aggregator ────────► compatibility_db
     │                             │
     ├─────────────┐               │
     ▼             ▼               ▼
conflict_resolver  export_generator  system_scanner
     │                   │              │
     └─────────┬─────────┴──────────────┘
                 ▼
            dependencies.py
                 │
          ┌──────┴──────┐
          ▼              ▼
     schemas.py     database/
      │              models.py
      │                 │
      ├── auth.py ──────┘
      │       │
      ▼       ▼
routes/packages   routes/system
     │               │
     └───────┬───────┘
             │
     exceptions.py  middleware.py
             │         │
             └────┬────┘
                  ▼
             api/main.py
                  │
                  ▼
         Frontend Services
         (auth.js wraps all)
                  │
     ┌────────────┴────────────┐
     ▼                         ▼
packageService.js       systemService.js
     │                         │
     ▼                         ▼
PackageSearch.vue       SystemInfo.vue
     │                         │
     └───────────┬─────────────┘
                 ▼
              App.vue
          (directly)
```

## Frontend Component Hierarchy
```
App.vue
├── PackageSearch.vue
│   └── services/packageService.js
└── SystemInfo.vue
    └── services/systemService.js
```

## Service Layer Flow
```
Frontend Services:
validators.js → used by all services
auth.js → provides auth headers
    ├── packageService.js → /api/packages/*
    └── systemService.js → /api/system/*
```

## Configuration and Environment Setup

### Environment Variables Flow
```
.env.example
     │
     ├── Backend Settings
     │   ├── DATABASE_URL
     │   ├── REDIS_URL
     │   ├── JWT_SECRET
     │   ├── API_RATE_LIMIT
     │   └── CACHE_TTL
     │
     ├── Data Source API Keys
     │   ├── PYPI_API_KEY
     │   ├── NPM_API_KEY
     │   ├── MAVEN_API_KEY
     │   └── GITHUB_TOKEN
     │
     └── Frontend Settings
         ├── VUE_APP_API_URL
         ├── VUE_APP_AUTH_ENABLED
         └── VUE_APP_TIMEOUT
```

## Docker Container Architecture
```
┌────────────────────────────────────────────────────────────────┐
│                     docker-compose.yml                         │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │   Frontend      │  │    Backend       │  │   Database    │  │
│  │  Container      │  │   Container      │  │  Container    │  │
│  │                 │  │                  │  │               │  │
│  │ nginx:alpine    │  │ python:3.11-slim │  │ postgres:15   │  │
│  │ ├─ Dockerfile   │  │ ├─ Dockerfile    │  │               │  │
│  │ ├─ nginx.conf   │  │ ├─ requirements  │  │               │  │
│  │ └─ Vue build    │  │ └─ FastAPI app   │  │               │  │
│  │                 │  │                  │  │               │  │
│  │ Port: 80  ──────┼──┼─► Port: 8000     │  │ Port: 5432    │  │
│  └─────────────────┘  │      │           │  │     ▲         │  │
│                       │      └───────────┼──┼─────┘         │  │
│                       │                  │  │               │  │
│  ┌─────────────────┐  │                  │  └───────────────┘  │
│  │    Redis        │  │                  │                     │
│  │   Container     │  │                  │                     │
│  │                 │◄─┘                  │                     │
│  │ redis:7-alpine  │                     │                     │
│  │                 │                     │                     │
│  │ Port: 6379      │                     │                     │
│  └─────────────────┘                     │                     │
│                                          │                     │
└──────────────────────────────────────────┴─────────────────────┘
```

## API Documentation Structure (docs/API.md)
```
API Endpoints:
├── Authentication
│   ├── POST /api/auth/login
│   ├── POST /api/auth/refresh
│   └── POST /api/auth/logout
│
├── Package Operations
│   ├── GET  /api/packages/search
│   ├── GET  /api/packages/{package_id}
│   ├── POST /api/packages/compare
│   ├── POST /api/packages/resolve-conflicts
│   └── POST /api/packages/export
│
└── System Operations
    ├── GET  /api/system/scan
    ├── GET  /api/system/info
    └── POST /api/system/analyze
```

## Deployment Pipeline (docs/DEPLOYMENT.md)
```
Deployment Pipeline:
├── Local Development
│   └── docker-compose up
│
├── CI/CD Pipeline
│   ├── GitHub Actions CI
│   │   ├── Run tests
│   │   ├── Lint code
│   │   └── Build images
│   │
│   └── GitHub Actions Deploy
│       ├── Push to registry
│       ├── Update K8s manifests
│       └── Deploy to cluster
│
└── Production Setup
    ├── Kubernetes configs
    ├── Ingress rules
    └── SSL certificates
```

## Database Schema Relationships
```
┌─────────────────────────────────────────────────────────────────┐
│                      Database Models                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐      ┌────────────────────┐               │
│  │    Packages      │      │   PackageVersions  │               │
│  ├──────────────────┤      ├────────────────────┤               │
│  │ id (PK)          │──────│ id (PK)            │               │
│  │ name             │  1:N │ package_id (FK)    │               │
│  │ ecosystem        │      │ version            │               │
│  │ description      │      │ release_date       │               │
│  │ repository_url   │      │ dependencies       │               │
│  │ created_at       │      │ metadata           │               │
│  └──────────────────┘      └────────────────────┘               │
│           │                          │                          │
│           │                          │                          │
│           │         ┌────────────────┴─────────────┐            │
│           │         ▼                              ▼            │
│  ┌────────┴──────────────┐      ┌──────────────────────┐        │
│  │  CompatibilityMatrix  │      │   DependencyGraph    │        │
│  ├───────────────────────┤      ├──────────────────────┤        │
│  │ id (PK)               │      │ id (PK)              │        │
│  │ package_a_id (FK)     │      │ version_id (FK)      │        │
│  │ package_b_id (FK)     │      │ dependency_id (FK)   │        │
│  │ compatible            │      │ constraint           │        │
│  │ conflict_reason       │      │ optional             │        │
│  │ updated_at            │      │ dev_dependency       │        │
│  └───────────────────────┘      └──────────────────────┘        │
│                                                                 │
│  ┌───────────────────┐          ┌──────────────────────┐        │
│  │   SystemScans     │          │    CacheEntries      │        │
│  ├───────────────────┤          ├──────────────────────┤        │
│  │ id (PK)           │          │ key (PK)             │        │
│  │ scan_date         │          │ value                │        │
│  │ system_info       │          │ expiry               │        │
│  │ packages_found    │          │ created_at           │        │
│  │ conflicts         │          └──────────────────────┘        │
│  └───────────────────┘                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Error Handling Flow
```
Frontend Error Handling:
┌──────────────────┐
│  validators.js   │ ← Input validation
├──────────────────┤
│  Service layer   │ ← API error handling
│  - auth.js       │   └─► Retry logic
│  - *Service.js   │   └─► Error formatting
└──────────────────┘

Backend Error Handling:
┌──────────────────┐
│  exceptions.py   │ ← Custom exceptions
├──────────────────┤
│  middleware.py   │ ← Global error handler
├──────────────────┤
│  Route handlers  │ ← Try/except blocks
├──────────────────┤
│  Core modules    │ ← Raise exceptions
└──────────────────┘
```

## Caching Strategy
```
Multi-Level Cache:
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend Cache                              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Browser Cache    │  Service Workers  │  Vue Store      │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Response Cache   │  Rate Limiting    │  CDN Cache      │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend Cache (cache.py)                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Redis Cache      │  In-Memory Cache  │  DB Query Cache │    │
│  │  - Package data   │  - Hot data       │  - ORM cache    │    │
│  │  - API responses  │  - Calculations   │  - Relationships│    │
│  │  - Session data   │  - Temp results   │                 │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Testing Structure (Implied)
```
Testing Hierarchy:
├── Frontend Tests
│   ├── Unit Tests
│   │   ├── Component tests
│   │   ├── Service tests
│   │   └── Utility tests
│   │
│   └── E2E Tests
│       └── User flow tests
│
└── Backend Tests
    ├── Unit Tests
    │   ├── Core module tests
    │   ├── Data source tests
    │   └── Database tests
    │
    ├── Integration Tests
    │   ├── API endpoint tests
    │   └── Database integration
    │
    └── Performance Tests
        ├── Load testing
        └── Cache efficiency
```

## Security Layers
```
Security Implementation:
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend Security                            │
│  - Input validation (validators.js)                             │
│  - XSS protection                                               │
│  - CSRF tokens                                                  │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Transport Security                           │
│  - HTTPS/TLS                                                    │
│  - CORS configuration                                           │
│  - Rate limiting                                                │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    API Security (auth.py)                       │
│  - JWT authentication                                           │
│  - Role-based access                                            │
│  - API key validation                                           │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Backend Security                             │
│  - SQL injection protection (ORM)                               │
│  - Environment variable encryption                              │
│  - Secure password hashing                                      │
└─────────────────────────────────────────────────────────────────┘
```

## Infrastructure Pipeline
```
GitHub Push → CI Workflow → Tests → Build Images → Deploy Workflow → Production
                │                        │
                └── Docker Build ────────┘
                    (Frontend + Backend)
```

## Project Directory

```bash
universal-dependency-resolver/
│
├── .env.example                    # Environment variables template
├── .env.development               # Development environment config (new)
├── .env.staging                   # Staging environment config (new)
├── .env.production               # Production environment config (new)
├── .dockerignore                 # Docker ignore file
├── .gitignore                    # Git ignore file
├── docker-compose.yml            # Docker compose configuration
├── docker-compose.prod.yml       # Production Docker compose config (new)
├── README.md                     # Project documentation
├── CONTRIBUTING.md               # Contribution guidelines
├── CHANGELOG.md                  # Version history and changes (new)
├── LICENSE                       # Project license (new)
│
├── .github/                      # GitHub configuration
│   ├── PULL_REQUEST_TEMPLATE.md  # PR template (new)
│   ├── ISSUE_TEMPLATE/           # Issue templates (new)
│   │   ├── bug_report.md        # Bug report template
│   │   ├── feature_request.md   # Feature request template
│   │   └── question.md          # Question template
│   └── workflows/
│       ├── ci.yml               # CI pipeline
│       ├── deploy.yml           # Deployment pipeline
│       └── integration-test.yml # Integration test workflow (new)
│
├── alembic/                     # Database migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/                # Migration files
│       └── 001_initial_schema.py # Initial database schema (new)
│
├── backend/                     # Backend application
│   ├── Dockerfile               # Backend Docker configuration
│   ├── requirements.txt         # Python dependencies
│   ├── settings.py              # Application settings (os.getenv)
│   ├── __init__.py
│   │
│   ├── api/                     # API layer
│   │   ├── __init__.py         # API package init
│   │   ├── auth.py             # Authentication logic
│   │   ├── dependencies.py     # FastAPI dependency injection
│   │   ├── exceptions.py       # Custom exceptions
│   │   ├── main.py             # FastAPI application
│   │   ├── middleware.py       # Middleware components
│   │   ├── schemas.py          # Pydantic request/response schemas
│   │   │
│   │   └── routes/             # API endpoints
│   │       ├── __init__.py
│   │       ├── packages.py     # Package-related endpoints
│   │       └── system.py       # System-related endpoints
│   │
│   ├── core/                   # Business logic
│   │   ├── __init__.py        # Core package init
│   │   ├── cache.py           # Cache manager
│   │   ├── conflict_resolver.py # Dependency conflict resolution
│   │   ├── data_aggregator.py  # Data aggregation logic
│   │   ├── export_generator.py # Export format generation
│   │   ├── system_scanner.py   # System information scanner
│   │   └── utils.py           # Utility functions
│   │
│   ├── data_sources/          # Package ecosystem clients
│   │   ├── __init__.py       # Data sources init
│   │   ├── base_client.py    # Base HTTP client with rate limiting
│   │   ├── pypi_client.py    # PyPI client
│   │   ├── npm_client.py     # NPM client
│   │   ├── conda_client.py   # Conda client
│   │   ├── maven_client.py   # Maven client
│   │   ├── crates_client.py  # Crates.io client
│   │   └── documentation_scraper.py # Documentation scraper
│   │
│   └── database/              # Database models and operations
│       ├── __init__.py       # Database package init
│       ├── models.py         # SQLAlchemy models
│       └── compatibility_db.py # Compatibility database operations
│
├── frontend/                  # Frontend application
│   ├── Dockerfile            # Frontend Docker configuration
│   ├── nginx.conf           # Nginx configuration
│   ├── package.json         # Node.js dependencies
│   │
│   └── src/                 # Vue.js source code
│       ├── App.vue          # Main Vue component
│       │
│       ├── components/      # Vue components
│       │   ├── DependencyList.vue
│       │   ├── PackageSearch.vue
│       │   ├── ResultsPanel.vue
│       │   └── SystemInfo.vue
│       │
│       ├── services/       # API services
│       │   ├── auth.js
│       │   ├── packageService.js
│       │   └── systemService.js
│       │
│       └── utils/         # Utility functions
│           └── validators.js
│
├── docs/                  # Documentation
│   ├── API.md            # API documentation
│   ├── DEPLOYMENT.md     # Deployment guide
│   ├── SDK_ROADMAP.md    # document outlines our SDK
│   └── ARCHITECTURE.md   # Architecture documentation
│
├── scripts/              # Utility scripts
│   ├── setup_dev.sh      # Development setup script
│   ├── run_tests.sh      # Test runner script
│   ├── deploy.sh         # Deployment script
│   ├── backup_database.sh
│   ├── restore_database.sh
│   ├── full_backup.sh
│   ├── check_data_flow.py
│   └── verify_imports.py
│
├── k8s/                          # Kubernetes manifests
│   ├── namespace.yaml            # Namespace definition
│   ├── configmap.yaml            # Non-sensitive env config
│   ├── secrets.yaml              # Secret definitions (placeholder)
│   ├── backend.yaml              # Backend Deployment + Service
│   ├── frontend.yaml             # Frontend Deployment + Service
│   ├── postgres.yaml             # PostgreSQL StatefulSet + PVC
│   ├── redis.yaml                # Redis Deployment + PVC
│   ├── ingress.yaml              # TLS Ingress rules
│   └── README.md
│
├── monitoring/                      # Monitoring stack
│   ├── setup_monitoring.sh          # Setup script
│   ├── alert_rules.yml              # Prometheus alert rules
│   ├── prometheus.yml               # Prometheus config (self-hosted)
│   ├── prometheus-free.yml          # Prometheus config (Grafana Cloud)
│   └── grafana/
│       ├── datasources/
│       │   └── prometheus.yml       # Auto-provisioned datasource
│       └── dashboards/
│           ├── dashboards.yml       # Dashboard provisioning config
│           └── udr-overview.json    # UDR overview dashboard 
│
└── tests/                # Test suite (7 files, see tests/ directory)
    ├── conftest.py
    ├── unit/
    │   ├── test_api/
    │   │   └── test_auth.py
    │   └── test_core/
    │       ├── test_conflict_resolver.py
    │       ├── test_data_aggregator.py
    │       ├── test_export_generator.py
    │       └── test_system_scanner.py
    └── integration/
        └── test_database_integration.py

```

---

It covers all aspects of my universal dependency resolver project architecture including:

1. **Dependency Flow Tree** - Visual representation of component dependencies
2. **File Interconnection Matrix** - Detailed import/export relationships
3. **Key Integration Points** - How different layers communicate
4. **Module Dependencies Graph** - Visual flow of module dependencies
5. **Component Hierarchies** - Frontend component structure
6. **Configuration Setup** - Environment variables and Docker architecture
7. **API/Deployment Documentation** - Endpoint and deployment structure
8. **Database Schema** - Entity relationships
9. **Error Handling** - Frontend and backend error flows
10. **Caching Strategy** - Multi-level caching approach
11. **Testing Structure** - Implied test organization
12. **Security Layers** - Security implementation at each level

This provides a comprehensive overview of my entire application architecture and how all the pieces fit together.
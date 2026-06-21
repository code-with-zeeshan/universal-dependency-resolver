# Universal Dependency Resolver

A sophisticated multi-ecosystem dependency resolution system supporting PyPI, NPM, Conda, Maven, and Crates.io with advanced conflict resolution and system compatibility checking.

## 🌟 Features

- **🔍 Multi-Ecosystem Support**: Search and analyze packages across PyPI, NPM, Conda, Maven, Crates.io, and more
- **🧠 Intelligent Conflict Resolution**: Advanced SAT-solver based dependency conflict resolution using Z3 with parallel processing
- **🖥️ System Compatibility**: Comprehensive system scanning for OS, CPU, GPU, and runtime detection
- **📊 Compatibility Matrix**: Generate and analyze compatibility matrices for complex dependencies
- **📦 Export Formats**: 14+ export formats including Docker, requirements.txt, package.json, and more
- **🏗️ Community Reports**: Crowdsourced compatibility reporting system
- **⚡ High Performance**: Redis caching with TTL, async batch operations, connection pooling, and optimized queries
- **🔒 Security First**: Input validation, distributed rate limiting, vulnerability scanning, and comprehensive error handling
- **📈 Scalable Architecture**: Async processing, database health checks, monitoring with Prometheus/Sentry
- **🔧 Production Ready**: Rate limiting, detailed health checks, structured logging, and monitoring

## 🚀 Coming Soon

We're actively working on these features for upcoming releases:

### Official SDKs & Tools
- **Python SDK** - Native Python client with async support
- **JavaScript/TypeScript SDK** - For Node.js and browser environments  
- **CLI Tool** - Command-line interface for CI/CD integration
- **More Client Support** - For All applications

### Enhanced Functionality
- **WebSocket Support** - Real-time progress updates
- **Dependency Vulnerability Scanning** - Security analysis
- **Visual Dependency Graphs** - Interactive visualization
- **Plugin System** - Add custom package ecosystems

Want to help? Check our [Contributing Guidelines](CONTRIBUTING.md) or vote for features in [Discussions](https://github.com/yourusername/universal-dependency-resolver/discussions).

## 📋 Prerequisites

- Docker & Docker Compose (recommended)
- Python 3.9+ (for local development)
- Node.js 16+ (for frontend development)
- PostgreSQL 15+ (if not using Docker)
- Redis 7+ (if not using Docker)

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/universal-dependency-resolver.git
cd universal-dependency-resolver

# Copy environment template
cp .env.example .env

# Start all services
docker-compose up -d

# Initialize database
docker-compose exec backend alembic upgrade head

# Access the application
# Frontend: http://localhost:8080
# API Docs: http://localhost:8000/api/v1/docs
# Health Check: http://localhost:8000/api/v1/health

## 📚 API Documentation

### Base URL
http://localhost:8000/api/v1

### Authentication
Currently, the API is open. Authentication can be enabled by setting `ENABLE_AUTH=true` in your environment.

### Rate Limiting
- Default: 60 requests per minute per IP
- Resolve endpoint: 10 requests per minute
- Export endpoint: 20 requests per minute
- Benchmarks: 5 requests per minute

### Core Endpoints

#### 1. Search Packages
Search for packages across multiple ecosystems.

```bash
GET /packages/search?q=tensorflow&ecosystems=pypi,conda&limit=20
```

# Parameters:
# - q: Search query (required)
# - ecosystems: Comma-separated list of ecosystems (optional)
# - limit: Results per ecosystem (default: 20, max: 100)
# - sort_by: relevance|downloads|name|updated (default: relevance)
# - python_version: Filter by Python version (optional)

# Response:
{
  "status": "success",
  "query": "tensorflow",
  "total_count": 42,
  "results": {
    "pypi": [
      {
        "name": "tensorflow",
        "version": "2.15.0",
        "description": "TensorFlow is an open source machine learning framework",
        "downloads": 50000000
      }
    ],
    "conda": [...]
  }
}

#### 2. Get Package Information
Get detailed information about a specific package.

GET /packages/{ecosystem}/{package_name}

# Example:
GET /packages/pypi/tensorflow?include_metrics=true

# Response:
{
  "status": "success",
  "data": {
    "name": "tensorflow",
    "ecosystem": "pypi",
    "description": "TensorFlow is an open source machine learning framework",
    "latest_version": "2.15.0",
    "homepage": "https://www.tensorflow.org/",
    "license": "Apache 2.0",
    "maintainers": ["Google Inc."],
    "versions": [...],
    "system_requirements": {
      "python": {"min": "3.8", "max": "3.11"},
      "gpu": {"cuda": "11.8", "cudnn": "8.6"}
    }
  }
}

#### 3. Get Package Versions
List all available versions with compatibility information.

GET /packages/{ecosystem}/{package_name}/versions

# Parameters:
# - compatible_with: System spec string (e.g., "os=linux,python=3.9,cuda=11.8")
# - include_yanked: Include yanked versions (default: false)
# - include_prerelease: Include pre-release versions (default: false)

# Example:
GET /packages/pypi/tensorflow/versions?compatible_with=os=linux,python=3.9

# Response:
{
  "status": "success",
  "package": "tensorflow",
  "ecosystem": "pypi",
  "total_versions": 150,
  "filtered_count": 45,
  "versions": [
    {
      "version": "2.15.0",
      "release_date": "2023-11-15",
      "python_requires": ">=3.8,<3.12",
      "compatible": true,
      "compatibility_notes": []
    }
  ]
}

#### 4. Resolve Dependencies
Resolve dependencies with conflict resolution.

POST /packages/resolve
Content-Type: application/json

{
  "packages": [
    {"name": "tensorflow", "ecosystem": "pypi", "version": ">=2.13.0"},
    {"name": "numpy", "ecosystem": "pypi", "version": ">=1.24.0"}
  ],
  "system_info": {
    "os": "linux",
    "python": "3.9.16",
    "gpu": {"cuda": "11.8", "available": true}
  },
  "auto_detect_system": true,
  "prefer_compatibility": true
}

# Response:
{
  "status": "success",
  "data": {
    "resolved": {
      "tensorflow": "2.15.0",
      "numpy": "1.24.3",
      "protobuf": "3.20.3"
    },
    "conflicts_resolved": [
      {
        "package": "protobuf",
        "conflict": "tensorflow requires <4.0, tensorboard requires >=3.20",
        "resolution": "3.20.3"
      }
    ],
    "dependency_graph": {...},
    "warnings": []
  }
}

#### 5. Export Configuration
Export resolved dependencies to various formats.

POST /packages/export
Content-Type: application/json

{
  "resolved_packages": {
    "tensorflow": "2.15.0",
    "numpy": "1.24.3"
  },
  "format": "requirements.txt",
  "system_info": {
    "python": "3.9"
  },
  "options": {
    "include_comments": true,
    "pin_versions": true
  }
}

# Response:
{
  "status": "success",
  "format": "requirements.txt",
  "content": "# Generated by Universal Dependency Resolver\n# Python: 3.9\n\ntensorflow==2.15.0\nnumpy==1.24.3\n"
}

#### 6. Get Export Formats
List all available export formats.

GET /packages/export-formats

# Response:
{
  "status": "success",
  "formats": [
    {"format": "requirements.txt", "ecosystem": "python", "description": "Python pip requirements file"},
    {"format": "package.json", "ecosystem": "node", "description": "Node.js package configuration"},
    {"format": "Dockerfile", "ecosystem": "multi", "description": "Docker container definition"},
    ...
  ]
}

#### 7. System Information
Get current system information.

GET /system/info?detailed=true

# Response:
{
  "status": "success",
  "data": {
    "os": {
      "system": "Linux",
      "release": "5.15.0",
      "version": "#1 SMP",
      "machine": "x86_64"
    },
    "cpu": {
      "brand": "Intel Core i7-9750H",
      "physical_cores": 6,
      "logical_cores": 12
    },
    "gpu": {
      "available": true,
      "devices": [
        {
          "name": "NVIDIA GeForce RTX 2060",
          "memory_mb": 6144
        }
      ],
      "cuda": "11.8",
      "cudnn": "8.6.0"
    },
    "runtime_versions": {
      "python": {"version": "3.9.16", "location": "/usr/bin/python3"},
      "node": {"version": "18.17.0"},
      "java": {"version": "17.0.8"}
    }
  }
}

#### 8. Check System Compatibility
Check if system meets requirements.

POST /system/check-compatibility
Content-Type: application/json

{
  "requirements": [
    {
      "type": "gpu",
      "minimum": {"cuda": "11.0", "memory_gb": 4},
      "required": true
    },
    {
      "type": "python",
      "minimum": {"version": "3.8"},
      "required": true
    }
  ],
  "packages": ["tensorflow", "pytorch"]
}

# Response:
{
  "status": "success",
  "results": {
    "compatible": true,
    "checks": [
      {
        "type": "gpu",
        "status": "pass",
        "message": "GPU meets requirements"
      }
    ],
    "warnings": [],
    "errors": []
  }
}

#### 9. Analyze Environment File
Analyze uploaded environment files.

POST /system/analyze-environment
Content-Type: multipart/form-data

# Form data:
# - file: requirements.txt or package.json etc.

# Response:
{
  "status": "success",
  "analysis": {
    "filename": "requirements.txt",
    "type": "python",
    "packages": [
      {"name": "tensorflow", "version": ">=2.13.0"},
      {"name": "numpy", "version": ">=1.24.0"}
    ],
    "system_requirements": {
      "python": {"min": "3.8"},
      "gpu": {"required": true}
    },
    "potential_conflicts": [],
    "estimated_size": 2500
  }
}

#### 10. Health Check
Check API and service health with detailed component status.

GET /health

# Response:
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "checks": {
    "database": {
      "status": "healthy",
      "pool_size": 10,
      "checked_in": 8,
      "checked_out": 2,
      "overflow": 0,
      "invalid": 0,
      "message": "Database connection is healthy"
    },
    "redis": {"status": "healthy"},
    "external_apis": {"status": "healthy"}
  }
}

#### Error Responses
All endpoints return consistent error responses:

{
  "error": {
    "message": "Package tensorflow not found in npm",
    "type": "not_found",
    "status_code": 404,
    "timestamp": "2024-01-15T10:30:00Z"
  }
}

#### Common Status Codes
* 200: Success
* 400: Bad Request (invalid parameters)
* 404: Resource not found
* 429: Rate limit exceeded
* 500: Internal server error

#### Pagination
For endpoints that return lists:

GET /packages/search?q=django&page=2&limit=20

# Response includes:
{
  "pagination": {
    "page": 2,
    "limit": 20,
    "total": 150,
    "pages": 8
  }
}

### 🔧 Configuration
See .env.example for all available configuration options. Key settings:

* DATABASE_URL: PostgreSQL connection string
* REDIS_URL: Redis connection string
* ALLOWED_ORIGINS: CORS allowed origins
* RATE_LIMIT_PER_MINUTE: API rate limiting
* ENABLE_AUTH: Enable authentication
* LOG_LEVEL: Logging verbosity

### 🧪 Testing

# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm run test

# Integration tests
docker-compose -f docker-compose.test.yml up --abort-on-container-exit

## 🚢 Deployment
See docs/DEPLOYMENT.md for detailed deployment instructions.

## 🤝 Contributing
See CONTRIBUTING.md for contribution guidelines.

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
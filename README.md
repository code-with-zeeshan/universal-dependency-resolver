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

See [docs/API.md](docs/API.md) for complete API reference.

### Base URL
http://localhost:8000/api/v1

### Quick Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/packages/search` | GET | Search packages across ecosystems |
| `/packages/{ecosystem}/{name}` | GET | Get package information |
| `/packages/{ecosystem}/{name}/versions` | GET | List package versions |
| `/packages/resolve` | POST | Resolve dependencies with conflict resolution |
| `/packages/export` | POST | Export resolved dependencies |
| `/packages/export-formats` | GET | List available export formats |
| `/system/info` | GET | Get system information |
| `/system/check-compatibility` | POST | Check system compatibility |
| `/system/analyze-environment` | POST | Analyze environment files |
| `/health` | GET | Health check |

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

# Integration tests (Docker)
docker-compose up -d
docker-compose exec backend pytest

## 🚢 Deployment
See docs/DEPLOYMENT.md for detailed deployment instructions.

## 🤝 Contributing
See CONTRIBUTING.md for contribution guidelines.

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.
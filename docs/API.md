# 📚 API Documentation

Comprehensive API documentation for the Universal Dependency Resolver.

> **Note**: The auto-generated OpenAPI/Swagger docs at `http://localhost:8000/docs` are the authoritative reference. This document provides a conceptual overview and usage examples.

## 📋 Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Response Format](#response-format)
- [Error Handling](#error-handling)
- [Package Endpoints](#package-endpoints)
- [System Endpoints](#system-endpoints)
- [Utility Endpoints](#utility-endpoints)
- [WebSocket / SocketIO API](#websocket--socketio-api)

## 🔍 Overview

The Universal Dependency Resolver API provides a unified interface for package management across multiple ecosystems.

### Base Information

| Property | Value |
|----------|-------|
| **Base URL** | `http://localhost:8000/api/v1` |
| **Protocol** | HTTP (HTTPS in production) |
| **Format** | JSON |
| **Versioning** | URL-based (`/api/v1/`) |

All endpoint paths in this document assume the `/api/v1` prefix unless otherwise noted.
| **Documentation** | OpenAPI 3.0 at `/docs` |

### Supported Ecosystems

| Ecosystem | Identifier | Package Count | Search | Dependencies |
|-----------|------------|---------------|--------|--------------|
| 🐍 **PyPI** | `pypi` | 400K+ | ✅ | ✅ |
| 📦 **NPM** | `npm` | 2M+ | ✅ | ✅ |
| 🐨 **Conda** | `conda` | 20K+ | ✅ | ✅ |
| ☕ **Maven** | `maven` | 400K+ | ✅ | ✅ |
| 🦀 **Crates** | `crates` | 100K+ | ✅ | ✅ |

## 🔐 Authentication

### API Keys

API keys provide programmatic access to the API:

```bash
# Include API key in header
curl -H "X-API-Key: your-api-key" \
     https://api.yourdomain.com/api/v1/packages/search?q=flask
```

### JWT Tokens

#### For user-based authentication:

```bash
# 1. Login to get token
curl -X POST https://api.yourdomain.com/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "user", "password": "pass"}'

# 2. Use token in subsequent requests
curl -H "Authorization: Bearer your-jwt-token" \
     https://api.yourdomain.com/api/v1/packages/search?q=flask
``` 

### Scopes

#### Different operations require different scopes:

Scope	                   Description	                    Operations
read:packages	           Read package information	        Search, get package details
read:system	             Read system information	        System scanning, compatibility
write:reports	           Submit compatibility reports	    Report compatibility issues
admin:all	               Administrative access	          All operations

## 🚦 Rate Limiting

### Rate limits are applied per API key or IP address:

Endpoint Category	                 Rate Limit	               Window
Search	                           60 requests	             1 minute
Package Info	                     100 requests	             1 minute
Dependencies	                     30 requests	             1 minute
Resolution	                       10 requests	             1 minute
System Info	                       30 requests	             1 minute
Export	                           20 requests	             1 minute

### Rate Limit Headers

```bash
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1609459200
Retry-After: 30
```

### Handling Rate Limits

```bash
import time
import requests

def make_request_with_retry(url, headers=None, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            continue
            
        return response
    
    raise Exception("Max retries exceeded")
```

## 📄 Response Format

### Successful Response

```bash
{
  "status": "success",
  "data": {
    // Response data
  },
  "metadata": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_123456789",
    "version": "1.0.0"
  }
}
```

### Error Response

```bash
{
  "error": {
    "type": "package_not_found",
    "message": "Package 'invalid-package' not found in pypi",
    "status_code": 404,
    "details": {
      "package": "invalid-package",
      "ecosystem": "pypi"
    },
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_123456789"
  }
}
```

### Pagination

#### For endpoints that return lists:

```bash
{
  "status": "success",
  "data": {
    "items": [...],
    "pagination": {
      "page": 1,
      "limit": 20,
      "total": 150,
      "pages": 8,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

## ❌ Error Handling

### HTTP Status Codes

Code	Status	Description
200	OK	Request successful
201	Created	Resource created
400	Bad Request	Invalid request parameters
401	Unauthorized	Authentication required
403	Forbidden	Insufficient permissions
404	Not Found	Resource not found
409	Conflict	Resource conflict
422	Unprocessable Entity	Validation errors
429	Too Many Requests	Rate limit exceeded
500	Internal Server Error	Server error
502	Bad Gateway	External service error
503	Service Unavailable	Service temporarily unavailable

### Error Types

Type	Description	Typical Code
validation_error	Request validation failed	422
package_not_found	Package doesn't exist	404
ecosystem_not_supported	Unsupported ecosystem	400
rate_limit_exceeded	Too many requests	429
dependency_resolution_failed	Resolution conflicts	422
external_api_error	External service issue	502
authentication_error	Auth failed	401
authorization_error	Insufficient permissions	403

## 📦 Package Endpoints

### Search Packages

#### Search for packages across multiple ecosystems.

```bash
GET /packages/search
```

### Parameters:

Parameter	Type	Required	Description
q	string	✅	Search query
ecosystems	string	❌	Comma-separated ecosystems
limit	integer	❌	Results per ecosystem (1-100, default: 20)
sort_by	string	❌	Sort order: relevance, downloads, name, updated
python_version	string	❌	Filter by Python version compatibility
include_prerelease	boolean	❌	Include pre-release versions

### Example:

```bash
curl "https://api.yourdomain.com/api/v1/packages/search?q=web+framework&ecosystems=pypi,npm&limit=10&sort_by=downloads"
```

### Response:

```bash
{
  "status": "success",
  "data": {
    "query": "web framework",
    "total_count": 1250,
    "results": {
      "pypi": [
        {
          "name": "flask",
          "version": "2.3.3",
          "description": "A simple framework for building complex web applications",
          "downloads": 50000000,
          "homepage": "https://flask.palletsprojects.com/",
          "license": "BSD-3-Clause",
          "last_updated": "2023-08-17T10:30:00Z"
        }
      ],
      "npm": [
        {
          "name": "express",
          "version": "4.18.2",
          "description": "Fast, unopinionated, minimalist web framework",
          "downloads": 25000000,
          "homepage": "https://expressjs.com/",
          "license": "MIT",
          "last_updated": "2023-08-12T15:45:00Z"
        }
      ]
    },
    "filters_applied": {
      "ecosystems": ["pypi", "npm"],
      "sort_by": "downloads",
      "limit": 10
    }
  }
}
```

### Get Package Details

#### Get detailed information about a specific package.

```bash
GET /packages/{ecosystem}/{name}
```

### Parameters:

Parameter	Type	Required	Description
ecosystem	string	✅	Package ecosystem
name	string	✅	Package name
include_metrics	boolean	❌	Include download metrics
include_dependencies	boolean	❌	Include dependency info

### Example:

```bash
curl "https://api.yourdomain.com/api/v1/packages/pypi/flask?include_metrics=true"
```

### Response:

```bash
{
  "status": "success",
  "data": {
    "name": "flask",
    "ecosystem": "pypi",
    "description": "A simple framework for building complex web applications",
    "latest_version": "2.3.3",
    "homepage": "https://flask.palletsprojects.com/",
    "repository": "https://github.com/pallets/flask",
    "license": "BSD-3-Clause",
    "maintainers": ["David Lord", "Phil Jones"],
    "versions": [
      {
        "version": "2.3.3",
        "release_date": "2023-08-17T10:30:00Z",
        "python_requires": ">=3.8",
        "size": 95000,
        "downloads": 1000000,
        "yanked": false
      }
    ],
    "system_requirements": {
      "python": {
        "min_version": "3.8",
        "max_version": null
      },
      "os": {
        "supported": ["linux", "windows", "macos"]
      }
    },
    "metrics": {
      "downloads": {
        "last_day": 100000,
        "last_week": 600000,
        "last_month": 2500000
      },
      "github": {
        "stars": 62000,
        "forks": 15000,
        "issues": 12,
        "last_commit": "2023-08-15T14:20:00Z"
      }
    }
  }
}
```

### Get Package Versions

#### List all available versions of a package.

```bash
GET /packages/{ecosystem}/{name}/versions
```

#### Parameters:

Parameter	Type	Required	Description
compatible_with	string	❌	System compatibility spec
include_yanked	boolean	❌	Include yanked versions
include_prerelease	boolean	❌	Include pre-release versions
limit	integer	❌	Maximum versions to return

#### Example:

```bash
curl "https://api.yourdomain.com/api/v1/packages/pypi/flask/versions?compatible_with=python=3.9,os=linux&limit=5"
```

### Get Package Dependencies

#### Get dependency information for a package version.

```bash
GET /packages/{ecosystem}/{name}/dependencies
```

#### Parameters:

Parameter	Type	Required	Description
version	string	❌	Specific version (default: latest)
recursive	boolean	❌	Get recursive dependencies
max_depth	integer	❌	Maximum recursion depth (1-5)
dev_dependencies	boolean	❌	Include development dependencies

#### Example:

```bash
curl "https://api.yourdomain.com/api/v1/packages/pypi/flask/dependencies?version=2.3.3&recursive=true&max_depth=2"
```

#### Response:

```bash
{
  "status": "success",
  "data": {
    "package": "flask",
    "version": "2.3.3",
    "dependency_tree": {
      "name": "flask",
      "version": "2.3.3",
      "dependencies": {
        "required": {
          "werkzeug": {
            "name": "werkzeug",
            "version": ">=2.3.7",
            "resolved_version": "2.3.7",
            "dependencies": {
              "required": {
                "markupsafe": {
                  "name": "markupsafe",
                  "version": ">=2.1.1",
                  "resolved_version": "2.1.3"
                }
              }
            }
          },
          "jinja2": {
            "name": "jinja2",
            "version": ">=3.1.2",
            "resolved_version": "3.1.2"
          }
        }
      }
    },
    "total_dependencies": {
      "direct": 4,
      "transitive": 8,
      "total": 12
    }
  }
}
```

### Resolve Dependencies

#### Resolve package dependencies with conflict resolution.

```bash
POST /packages/resolve
```

#### Request Body:

```bash
{
  "packages": [
    {
      "name": "flask",
      "ecosystem": "pypi",
      "version": ">=2.0.0"
    },
    {
      "name": "django",
      "ecosystem": "pypi",
      "version": ">=4.0.0"
    }
  ],
  "system_info": {
    "os": "linux",
    "python_version": "3.9.16",
    "architecture": "x86_64"
  },
  "options": {
    "auto_detect_system": true,
    "prefer_compatibility": true,
    "allow_prerelease": false,
    "solver_timeout": 300
  }
}
```

#### Response:

```bash
{
  "status": "success",
  "data": {
    "resolution_id": "res_123456789",
    "resolved": {
      "flask": "2.3.3",
      "django": "4.2.5",
      "werkzeug": "2.3.7",
      "jinja2": "3.1.2",
      "sqlparse": "0.4.4"
    },
    "conflicts_resolved": [
      {
        "package": "markupsafe",
        "conflict": "flask requires >=2.1.1, jinja2 requires >=2.0.0",
        "resolution": "2.1.3",
        "strategy": "highest_compatible"
      }
    ],
    "warnings": [
      {
        "type": "version_constraint",
        "message": "Using older version of setuptools due to compatibility",
        "package": "setuptools",
        "requested": ">=65.0.0",
        "resolved": "64.0.3"
      }
    ],
    "metadata": {
      "solver_time": 2.35,
      "total_packages": 15,
      "conflicts_found": 3,
      "conflicts_resolved": 3
    }
  }
}
```

### Export Configuration

#### Export resolved dependencies to various formats.

```bash
POST /packages/export
```

#### Request Body:

```bash
{
  "resolved_packages": {
    "flask": "2.3.3",
    "django": "4.2.5",
    "numpy": "1.24.3"
  },
  "format": "requirements.txt",
  "options": {
    "include_comments": true,
    "pin_versions": true,
    "include_hashes": false,
    "group_by_ecosystem": false
  },
  "system_info": {
    "python_version": "3.9"
  }
}
```

#### Response:

```bash
{
  "status": "success",
  "data": {
    "format": "requirements.txt",
    "filename": "requirements.txt",
    "content": "# Generated by Universal Dependency Resolver\n# Python: 3.9\n# Generated: 2024-01-15T10:30:00Z\n\nflask==2.3.3\ndjango==4.2.5\nnumpy==1.24.3\nwerkzeug==2.3.7\njinja2==3.1.2\n",
    "size": 156,
    "package_count": 5
  }
}
```

### Get Export Formats

#### List all available export formats.

```bash
GET /packages/export-formats
```

#### Response:

```bash
{
  "status": "success",
  "data": {
    "formats": [
      {
        "format": "requirements.txt",
        "ecosystem": "python",
        "description": "Python pip requirements file",
        "extensions": [".txt"],
        "supports_comments": true,
        "supports_hashes": true
      },
      {
        "format": "package.json",
        "ecosystem": "node",
        "description": "Node.js package configuration",
        "extensions": [".json"],
        "supports_comments": false,
        "supports_hashes": false
      },
      {
        "format": "Dockerfile",
        "ecosystem": "multi",
        "description": "Docker container definition",
        "extensions": [".dockerfile", ""],
        "supports_comments": true,
        "supports_hashes": false
      }
    ]
  }
}
```

### Package Compatibility

#### Get compatibility information for a package.

```bash
GET /packages/{ecosystem}/{name}/compatibility
```

#### Parameters:

Parameter	Type	Required	Description
version	string	❌	Specific version to check
system_spec	string	❌	System specification

#### Example:

```bash
curl "https://api.yourdomain.com/api/v1/packages/pypi/tensorflow/compatibility?version=2.13.0&system_spec=python=3.9,os=linux,cuda=11.8"
```

#### Response:

```bash
{
  "status": "success",
  "data": {
    "package": "tensorflow",
    "version": "2.13.0",
    "compatibility": {
      "compatible": true,
      "system_requirements": {
        "python": {
          "min_version": "3.8",
          "max_version": "3.11"
        },
        "os": {
          "supported": ["linux", "windows", "macos"]
        },
        "gpu": {
          "cuda_versions": ["11.2", "11.8"],
          "cudnn_versions": ["8.1", "8.6"]
        }
      },
      "known_issues": [],
      "community_reports": {
        "total_reports": 150,
        "success_rate": 0.94,
        "common_issues": [
          {
            "issue": "CUDA version mismatch",
            "frequency": 0.15,
            "solution": "Install CUDA 11.8"
          }
        ]
      }
    }
  }
}
```

### Report Package Compatibility

#### Submit a compatibility report for a package.

```bash
POST /packages/{ecosystem}/{name}/compatibility/report
```

#### Request Body:

```bash
{
  "version": "2.13.0",
  "system_info": {
    "os": "linux",
    "python_version": "3.9.16",
    "cuda_version": "11.8",
    "gpu_available": true
  },
  "works": true,
  "installation_method": "pip",
  "notes": "Installed successfully with CUDA support",
  "performance_notes": "Good performance for training models"
}
```

## 🖥️ System Endpoints

### Get System Information

#### Get current system information and capabilities.

```bash
GET /system/info
```

#### Parameters:

Parameter	Type	Required	Description
detailed	boolean	❌	Include detailed hardware info
scan_packages	boolean	❌	Scan for installed packages

#### Example:

```bash
curl "https://api.yourdomain.com/api/v1/system/info?detailed=true&scan_packages=true"
```

#### Response:

```bash
{
  "status": "success",
  "data": {
    "os": {
      "system": "Linux",
      "release": "5.15.0-58-generic",
      "version": "#64-Ubuntu SMP Thu Jan 5 11:43:13 UTC 2023",
      "machine": "x86_64",
      "processor": "x86_64"
    },
    "cpu": {
      "brand": "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz",
      "physical_cores": 6,
      "logical_cores": 12,
      "frequency": 2600,
      "architecture": "x86_64"
    },
    "memory": {
      "total": 17179869184,
      "available": 8589934592,
      "percent_used": 50.0
    },
    "gpu": {
      "available": true,
      "devices": [
        {
          "name": "NVIDIA GeForce RTX 2060",
          "memory_mb": 6144,
          "driver_version": "525.60.11",
          "cuda_version": "12.0"
        }
      ],
      "cuda": "12.0",
      "cudnn": "8.6.0"
    },
    "runtime_versions": {
      "python": {
        "version": "3.9.16",
        "location": "/usr/bin/python3"
      },
      "node": {
        "version": "18.17.0",
        "location": "/usr/bin/node"
      },
      "java": {
        "version": "17.0.8",
        "location": "/usr/bin/java"
      }
    },
    "installed_packages": {
      "pypi": ["flask==2.3.3", "numpy==1.24.3"],
      "npm": ["express@4.18.2", "lodash@4.17.21"],
      "system": ["git", "curl", "docker"]
    }
  }
}
```

### Check System Compatibility

#### Check if the system meets specific requirements.

```bash
POST /system/check-compatibility
```

#### Request Body:

```bash
{
  "requirements": [
    {
      "type": "python",
      "minimum": {"version": "3.8"},
      "recommended": {"version": "3.9"},
      "required": true
    },
    {
      "type": "gpu",
      "minimum": {"cuda": "11.0", "memory_gb": 4},
      "required": false
    },
    {
      "type": "memory",
      "minimum": {"gb": 8},
      "recommended": {"gb": 16},
      "required": true
    }
  ],
  "packages": ["tensorflow", "pytorch"]
}
```

#### Response:

```bash
{
  "status": "success",
  "data": {
    "compatible": true,
    "checks": [
      {
        "type": "python",
        "status": "pass",
        "message": "Python version meets requirements",
        "current": "3.9.16",
        "required": ">=3.8"
      },
      {
        "type": "gpu",
        "status": "pass",
        "message": "GPU meets requirements",
        "current": "NVIDIA RTX 2060 (6GB)",
        "required": ">=4GB VRAM"
      }
    ],
    "warnings": [
      "Consider upgrading to 16GB RAM for better performance"
    ],
    "recommendations": [
      "Update CUDA drivers to version 12.0 for optimal performance"
    ]
  }
}
```

### Analyze Environment File

#### Analyze an environment file for compatibility and issues.

```bash
POST /system/analyze-environment
```

#### Request:

```bash
curl -X POST https://api.yourdomain.com/api/v1/system/analyze-environment \
     -H "Content-Type: multipart/form-data" \
     -F "file=@requirements.txt"
```

#### Response:

```bash
{
  "status": "success",
  "data": {
    "filename": "requirements.txt",
    "type": "python",
    "packages": [
      {
        "name": "flask",
        "version": ">=2.0.0",
        "line": 1
      },
      {
        "name": "numpy",
        "version": ">=1.20.0",
        "line": 2
      }
    ],
    "analysis": {
      "total_packages": 15,
      "direct_packages": 2,
      "estimated_size_mb": 250,
      "python_version_required": ">=3.8",
      "potential_conflicts": [
        {
          "packages": ["tensorflow", "tensorflow-gpu"],
          "reason": "These packages conflict with each other",
          "severity": "error"
        }
      ],
      "security_issues": [
        {
          "package": "pillow",
          "version": "8.0.0",
          "vulnerability": "CVE-2021-34552",
          "severity": "medium"
        }
      ],
      "recommendations": [
        "Pin package versions for reproducible builds",
        "Consider using virtual environments"
      ]
    }
  }
}
```

### Run System Benchmarks

#### Run performance benchmarks on the system.

```bash
GET /system/benchmarks
```

#### Parameters:

Parameter	Type	Required	Description
comprehensive	boolean	❌	Run comprehensive benchmarks
include_gpu	boolean	❌	Include GPU benchmarks

#### Example:

```bash
curl "https://api.yourdomain.com/api/v1/system/benchmarks?comprehensive=true&include_gpu=true"
```

## 🔧 Utility Endpoints

### Health Check

#### Check API health and status.

```bash
GET /health
```

#### Response:

```bash
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "checks": {
    "database": {"status": "healthy", "response_time": 12},
    "redis": {"status": "healthy", "response_time": 3},
    "external_apis": {"status": "healthy", "success_rate": 0.98}
  },
  "uptime": 86400
}
```

### API Information

#### Get API version and endpoint information.

```bash
GET /
```

#### Response:

```bash
{
  "name": "Universal Dependency Resolver API",
  "version": "1.0.0",
  "documentation": {
    "openapi": "/api/v1/docs",
    "redoc": "/api/v1/redoc"
  },
  "endpoints": {
    "health": "/api/v1/health",
    "packages": "/api/v1/packages",
    "system": "/api/v1/system"
  }
}
```

## 🌐 WebSocket / SocketIO API

### For real-time updates during long-running operations, the API uses SocketIO:

#### Connection

```javascript
import { io } from 'socket.io-client';

const socket = io('wss://api.yourdomain.com', {
  path: '/api/v1/ws',
  transports: ['websocket']
});

socket.on('connect', () => {
  console.log('Connected');

  // Subscribe to a resolution job
  socket.emit('subscribe', { resolution_id: 'res_123456789' });
});

socket.on('progress', (data) => {
  console.log(`Progress: ${data.progress}% - ${data.stage}`);
});

socket.on('complete', (data) => {
  console.log('Resolution complete:', data);
});

socket.on('error', (data) => {
  console.error('Error:', data.message);
});
```

#### Events

| Event | Direction | Payload |
|-------|-----------|---------|
| `subscribe` | Client → Server | `{ resolution_id }` |
| `progress` | Server → Client | `{ progress, stage, resolution_id }` |
| `complete` | Server → Client | `{ resolution_id, status, resolved }` |
| `error` | Server → Client | `{ message, code }` |

> **Note**: See `docs/SDK_ROADMAP.md` for the SDK roadmap.

## 📧 Need Help?

* Documentation: https://docs.yourdomain.com
* Support: support@yourdomain.com
* Discord: Join our community
* GitHub: Report issues

🎉 Happy coding with Universal Dependency Resolver!
## 2. `docs/DEPLOYMENT.md` - Deployment Guide

```markdown
# 🚀 Deployment Guide

Complete deployment guide for Universal Dependency Resolver across different environments and platforms.

## 📋 Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Cloud Deployments](#cloud-deployments)
- [Production Checklist](#production-checklist)
- [Monitoring & Logging](#monitoring--logging)
- [Backup & Recovery](#backup--recovery)
- [Troubleshooting](#troubleshooting)
- [Performance Tuning](#performance-tuning)

## 🔍 Overview

The Universal Dependency Resolver supports multiple deployment strategies:

| Method | Complexity | Best For | Scalability |
|--------|------------|----------|-------------|
| 🐳 **Docker Compose** | Low | Development, Small deployments | Limited |
| ☸️ **Kubernetes** | High | Production, Large scale | Excellent |
| ☁️ **Cloud Services** | Medium | Managed infrastructure | Good |
| 🖥️ **Bare Metal** | Medium | Custom requirements | Good |

## ✅ Prerequisites

### System Requirements

**Minimum Requirements:**
- **CPU**: 2 cores
- **RAM**: 4GB
- **Storage**: 20GB SSD
- **Network**: 100 Mbps

**Recommended for Production:**
- **CPU**: 4+ cores
- **RAM**: 8GB+
- **Storage**: 50GB+ SSD
- **Network**: 1 Gbps
- **Load Balancer**: Yes

### Software Dependencies

```bash
# Required
- Docker 20.10+
- Docker Compose 2.0+
- PostgreSQL 15+
- Redis 7+

# For Kubernetes
- kubectl 1.25+
- Helm 3.10+

# For monitoring
- Prometheus
- Grafana
``` 
## ⚙️ Environment Configuration

### Environment Variables

#### Create environment-specific configuration files:

```bash
# .env.production
ENV=production
DEBUG=false

# Database
DATABASE_URL=postgresql://user:password@db-host:5432/depresolver
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30

# Redis
REDIS_URL=redis://redis-host:6379
REDIS_MAX_CONNECTIONS=100

# API Configuration
SECRET_KEY=your-super-secret-key-here
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
API_RATE_LIMIT_PER_MINUTE=120

# Security
ENABLE_AUTH=true
ENABLE_API_KEY_AUTH=true

# Monitoring
PROMETHEUS_ENABLED=true
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# External Services
PYPI_RATE_LIMIT=1000
NPM_RATE_LIMIT=1000
CONDA_RATE_LIMIT=500

# Performance
CACHE_TTL=3600
MAX_PARALLEL_REQUESTS=20
THREAD_POOL_SIZE=30
```

### Configuration Templates

```bash
# Development
cp .env.example .env.development

# Staging  
cp .env.example .env.staging

# Production
cp .env.example .env.production
```

## 🐳 Docker Deployment

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/yourusername/universal-dependency-resolver.git
cd universal-dependency-resolver

# 2. Configure environment
cp .env.example .env.production
# Edit .env.production with your settings

# 3. Deploy with Docker Compose
docker-compose -f docker-compose.prod.yml up -d

# 4. Run database migrations
docker-compose exec backend alembic upgrade head

# 5. Verify deployment
curl http://localhost:8000/api/v1/health
```

### Production Docker Compose

#### Create docker-compose.prod.yml:

```bash
version: '3.8'

services:
  # Reverse Proxy
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./frontend/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./frontend/ssl:/etc/nginx/ssl:ro
      - ./logs/nginx:/var/log/nginx
    depends_on:
      - backend
      - frontend
    restart: unless-stopped
    networks:
      - app-network

  # Backend API
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    env_file:
      - .env.production
    volumes:
      - ./logs/backend:/app/logs
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - app-network
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M

  # Frontend
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    environment:
      - VUE_APP_API_URL=https://yourdomain.com
    restart: unless-stopped
    networks:
      - app-network
    deploy:
      replicas: 2

  # Database
  db:
    image: postgres:15-alpine
    env_file:
      - .env.production
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    restart: unless-stopped
    networks:
      - app-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $POSTGRES_USER -d $POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis Cache
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    restart: unless-stopped
    networks:
      - app-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  # Monitoring
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    restart: unless-stopped
    networks:
      - app-network

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana:/etc/grafana/provisioning
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
      - GF_USERS_ALLOW_SIGN_UP=false
    restart: unless-stopped
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:
```

## ☸️ Kubernetes Deployment

### Namespace Setup

```bash
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: universal-dependency-resolver
  labels:
    app: udr
    environment: production
```

### ConfigMap

```bash
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: udr-config
  namespace: universal-dependency-resolver
data:
  ENV: "production"
  DEBUG: "false"
  LOG_LEVEL: "INFO"
  CACHE_TTL: "3600"
  MAX_PARALLEL_REQUESTS: "20"
  PROMETHEUS_ENABLED: "true"
```

### Secrets

```bash
# k8s/secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: udr-secrets
  namespace: universal-dependency-resolver
type: Opaque
data:
  SECRET_KEY: <base64-encoded-secret>
  DATABASE_URL: <base64-encoded-db-url>
  REDIS_URL: <base64-encoded-redis-url>
  SENTRY_DSN: <base64-encoded-sentry-dsn>
```

### Backend Deployment

```bash
# k8s/backend.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: universal-dependency-resolver
  labels:
    app: udr-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: udr-backend
  template:
    metadata:
      labels:
        app: udr-backend
    spec:
      containers:
      - name: backend
        image: ghcr.io/yourusername/udr-backend:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: udr-config
        - secretRef:
            name: udr-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: backend-service
  namespace: universal-dependency-resolver
spec:
  selector:
    app: udr-backend
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
```

### Database with Persistent Storage

```bash
# k8s/postgres.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: universal-dependency-resolver
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
  storageClassName: fast-ssd
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: universal-dependency-resolver
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        env:
        - name: POSTGRES_DB
          value: "depresolver"
        - name: POSTGRES_USER
          value: "user"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: udr-secrets
              key: POSTGRES_PASSWORD
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: universal-dependency-resolver
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
  type: ClusterIP
```

### Ingress with SSL

```bash
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: udr-ingress
  namespace: universal-dependency-resolver
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
spec:
  tls:
  - hosts:
    - api.yourdomain.com
    - yourdomain.com
    secretName: udr-tls
  rules:
  - host: api.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: backend-service
            port:
              number: 8000
  - host: yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend-service
            port:
              number: 80
```

### Deployment Commands

```bash
# Deploy to Kubernetes
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/frontend.yaml
kubectl apply -f k8s/ingress.yaml

# Run migrations
kubectl exec -it deployment/backend -n universal-dependency-resolver -- alembic upgrade head

# Check deployment status
kubectl get pods -n universal-dependency-resolver
kubectl logs -f deployment/backend -n universal-dependency-resolver
```

## ☁️ Cloud Deployments

### AWS ECS with Fargate

```bash
// ecs-task-definition.json
{
  "family": "udr-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::account:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::account:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "ghcr.io/yourusername/udr-backend:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "ENV", "value": "production"},
        {"name": "DEBUG", "value": "false"}
      ],
      "secrets": [
        {
          "name": "DATABASE_URL",
          "valueFrom": "arn:aws:secretsmanager:region:account:secret:udr/database-url"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/udr-backend",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3
      }
    }
  ]
}
```

### Google Cloud Run

```bash
# cloud-run-backend.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: udr-backend
  annotations:
    run.googleapis.com/ingress: all
    run.googleapis.com/execution-environment: gen2
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/maxScale: "10"
        autoscaling.knative.dev/minScale: "1"
        run.googleapis.com/cpu-throttling: "false"
    spec:
      containerConcurrency: 100
      timeoutSeconds: 300
      containers:
      - image: gcr.io/project-id/udr-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: ENV
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: database-url
              key: url
        resources:
          limits:
            cpu: "2"
            memory: "2Gi"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

### Azure Container Instances

```bash
# azure-container-group.yaml
apiVersion: 2021-03-01
location: eastus
name: udr-container-group
properties:
  containers:
  - name: backend
    properties:
      image: ghcr.io/yourusername/udr-backend:latest
      ports:
      - port: 8000
        protocol: TCP
      environmentVariables:
      - name: ENV
        value: production
      - name: DATABASE_URL
        secureValue: postgresql://...
      resources:
        requests:
          cpu: 1
          memoryInGB: 2
      livenessProbe:
        httpGet:
          path: /api/v1/health
          port: 8000
        initialDelaySeconds: 30
        periodSeconds: 10
  - name: frontend
    properties:
      image: ghcr.io/yourusername/udr-frontend:latest
      ports:
      - port: 80
        protocol: TCP
      resources:
        requests:
          cpu: 0.5
          memoryInGB: 1
  osType: Linux
  ipAddress:
    type: Public
    ports:
    - protocol: TCP
      port: 80
    - protocol: TCP
      port: 8000
  restartPolicy: Always
type: Microsoft.ContainerInstance/containerGroups
```

## ✅ Production Checklist

### Pre-Deployment

#### Environment Configuration

* All environment variables configured
* Secrets properly secured
* Database credentials set up
* SSL certificates obtained

#### Security Setup

* HTTPS enabled
* CORS properly configured
* Rate limiting enabled
* API authentication configured
* Security headers added

#### Database Setup

* Database created and configured
* Migrations applied
* Backup strategy implemented
* Connection pooling configured

#### Infrastructure

* Load balancer configured
* Auto-scaling rules set
* Health checks enabled
* Monitoring tools set up

### Post-Deployment
 
#### Verification

* Health checks passing
* API endpoints responding
* Frontend loading correctly
* Database connectivity confirmed
 
#### Performance

* Response times acceptable
* Memory usage normal
* CPU usage normal
* Database performance optimal
 
#### Monitoring

* Logs flowing correctly
* Metrics being collected
* Alerts configured
* Dashboards set up

#### Backup & Recovery

* Database backups running
* Backup restoration tested
* Disaster recovery plan ready

## 📊 Monitoring & Logging

### Prometheus Configuration

```bash
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

scrape_configs:
  - job_name: 'udr-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### Grafana Dashboards

#### Key metrics to monitor:

##### Application Metrics

* Request rate and response time
* Error rate by endpoint
* Active connections
* Cache hit/miss ratio

##### Infrastructure Metrics

* CPU and memory usage
* Disk I/O and space
* Network traffic
* Container/pod health

##### Database Metrics

* Connection pool usage
* Query performance
* Lock waits
* Replication lag

### Logging Configuration

```python
# Configure logging in backend/settings.py or api/main.py
import logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
```

## 💾 Backup & Recovery

### Database Backup Strategy

```bash
#!/bin/bash
# scripts/backup_database.sh

set -e

# Configuration
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="depresolver"
DB_USER="user"
BACKUP_DIR="/backups"
RETENTION_DAYS=30

# Create backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/postgres_backup_${TIMESTAMP}.sql.gz"

echo "Starting database backup..."

# Create backup with compression
pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME | gzip > $BACKUP_FILE

# Verify backup
if [ -f "$BACKUP_FILE" ]; then
    echo "Backup created successfully: $BACKUP_FILE"
    echo "Backup size: $(du -h $BACKUP_FILE | cut -f1)"
else
    echo "Backup failed!"
    exit 1
fi

# Clean up old backups
find $BACKUP_DIR -name "postgres_backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed and old backups cleaned up."
```

### Automated Backup with Cron

```bash
# Add to crontab
0 2 * * * /path/to/scripts/backup_database.sh

# Backup every 6 hours
0 */6 * * * /path/to/scripts/backup_database.sh

# Weekly full backup
0 3 * * 0 /path/to/scripts/full_backup.sh
```

### Recovery Procedures

```bash
#!/bin/bash
# scripts/restore_database.sh

set -e

BACKUP_FILE=$1
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="depresolver"
DB_USER="user"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

echo "Restoring database from: $BACKUP_FILE"

# Stop application
docker-compose stop backend

# Drop and recreate database
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -c "DROP DATABASE IF EXISTS $DB_NAME;"
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -c "CREATE DATABASE $DB_NAME;"

# Restore from backup
gunzip -c $BACKUP_FILE | psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME

# Start application
docker-compose start backend

echo "Database restoration completed."
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Database Connection Issues

##### Symptoms:

* "Connection refused" errors
* "Too many connections" errors
* Slow database queries

##### Solutions:

```bash
# Check database status
docker-compose exec db pg_isready

# Check connection count
docker-compose exec db psql -U user -d depresolver -c "SELECT count(*) FROM pg_stat_activity;"

# Increase connection pool size
# In .env:
DATABASE_POOL_SIZE=30
DATABASE_MAX_OVERFLOW=50
```

#### 2. Redis Connection Issues

##### Symptoms:

* Cache misses increasing
* "Connection timeout" errors
* High memory usage

##### Solutions:

```bash
# Check Redis status
docker-compose exec redis redis-cli ping

# Check memory usage
docker-compose exec redis redis-cli info memory

# Clear cache if needed
docker-compose exec redis redis-cli flushall
```

#### 3. High Response Times

##### Symptoms:

* API responses > 5 seconds
* Frontend loading slowly
* High CPU/memory usage

#### Debugging Steps:

```bash
# Check container resource usage
docker stats

# Check API endpoint performance
curl -w "@curl-format.txt" -o /dev/null -s "http://localhost:8000/api/v1/health"

# Check database slow queries
docker-compose exec db psql -U user -d depresolver -c "SELECT query, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
```

#### 4. Container Crashes

##### Symptoms:

* Containers restarting frequently
* "Exit code 1" errors
* OOMKilled status

##### Investigation:

```bash
# Check container logs
docker-compose logs backend --tail=100

# Check system resources
docker system df
docker system events

# Check for memory limits
docker-compose exec backend cat /sys/fs/cgroup/memory/memory.limit_in_bytes
```

#### Log Analysis

```bash
# Search for errors in logs
docker-compose logs backend | grep -i error

# Monitor logs in real-time
docker-compose logs -f backend

# Export logs for analysis
docker-compose logs --no-color backend > backend.log

# Search for specific patterns
grep "HTTP 500" backend.log | tail -20
```

#### Performance Debugging

```bash
# Enable SQL query logging
# In .env:
ENABLE_SQL_LOGGING=true

# Profile API endpoints
curl -w "Time: %{time_total}s\nSize: %{size_download} bytes\n" \
     -o /dev/null -s "http://localhost:8000/api/v1/packages/search?q=flask"

# Monitor resource usage
watch 'docker stats --no-stream'
```

## ⚡ Performance Tuning

### Database Optimization

```bash
-- Create indexes for common queries
CREATE INDEX CONCURRENTLY idx_packages_ecosystem ON packages(ecosystem);
CREATE INDEX CONCURRENTLY idx_packages_name_ecosystem ON packages(name, ecosystem);
CREATE INDEX CONCURRENTLY idx_dependencies_package_id ON dependencies(package_id);

-- Update statistics
ANALYZE;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes 
ORDER BY idx_scan ASC;
```

### Redis Configuration

```bash
# redis.conf optimizations
maxmemory 1gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
tcp-keepalive 300
timeout 0
```

### Application Tuning

```bash
# backend/settings.py optimizations
# Increase worker processes
WORKERS = min(32, (os.cpu_count() or 1) + 1)

# Tune connection pools
DATABASE_POOL_SIZE = 20
DATABASE_MAX_OVERFLOW = 30
REDIS_MAX_CONNECTIONS = 100

# Cache optimization
CACHE_TTL = 3600  # 1 hour
CACHE_TTL_SHORT = 300  # 5 minutes
CACHE_TTL_LONG = 86400  # 24 hours

# Parallel processing
MAX_PARALLEL_REQUESTS = 20
MAX_PARALLEL_DOWNLOADS = 10
THREAD_POOL_SIZE = 30
```

### Frontend Optimization

```bash
// Enable gzip compression
// In nginx.conf:
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;

// Enable browser caching
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

🎉 Congratulations! Your Universal Dependency Resolver is now ready for production deployment.

For additional support, check our troubleshooting guide or reach out to the community.
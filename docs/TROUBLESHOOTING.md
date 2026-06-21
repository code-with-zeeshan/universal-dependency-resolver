# Troubleshooting Guide

## 🔧 Common Issues and Solutions

This guide helps you diagnose and resolve common issues with the Universal Dependency Resolver.

## 🚀 Startup Issues

### Database Connection Failed
```
Error: Can't connect to PostgreSQL database
```

**Solutions:**
1. Verify PostgreSQL is running:
   ```bash
   docker-compose ps postgres
   ```

2. Check connection string in `.env`:
   ```bash
   DATABASE_URL=postgresql://user:password@localhost/depresolver
   ```

3. Test database connectivity:
   ```bash
   docker-compose exec postgres psql -U user -d depresolver
   ```

### Redis Connection Failed
```
Error: Can't connect to Redis
```

**Solutions:**
1. Verify Redis is running:
   ```bash
   docker-compose ps redis
   ```

2. Check Redis URL in `.env`:
   ```bash
   REDIS_URL=redis://localhost:6379
   ```

3. Test Redis connectivity:
   ```bash
   docker-compose exec redis redis-cli ping
   ```

### Port Already in Use
```
Error: [Errno 48] Address already in use
```

**Solutions:**
1. Find process using the port:
   ```bash
   lsof -i :8000  # For backend
   lsof -i :8080  # For frontend
   ```

2. Kill the process or change ports in docker-compose.yml

## 🔍 API Issues

### Rate Limiting
```
HTTP 429: Too Many Requests
```

**Current Limits:**
- General: 60 requests/minute
- Resolve: 10 requests/minute
- Export: 20 requests/minute

**Solutions:**
1. Wait for rate limit reset
2. Implement request batching
3. Contact administrators for higher limits

### Invalid Package Names
```
HTTP 400: Invalid package name format
```

**Validation Rules:**
- Package names must match: `^[a-zA-Z0-9][a-zA-Z0-9._-]*$`
- Maximum length: 255 characters
- No leading/trailing whitespace

### Resolution Timeout
```
HTTP 504: Resolution timeout
```

**Causes:**
- Complex dependency graphs
- Network issues with external APIs
- Resource constraints

**Solutions:**
1. Simplify dependency requirements
2. Use batch resolution for multiple packages
3. Check external API status

## 🗄️ Database Issues

### Connection Pool Exhausted
```
Error: Timeout waiting for connection from pool
```

**Symptoms:**
- Slow response times
- Database connection errors
- High memory usage

**Solutions:**
1. Increase pool size in `models.py`:
   ```python
   engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=30)
   ```

2. Monitor pool status via health check:
   ```bash
   curl http://localhost:8000/api/v1/health
   ```

3. Check for connection leaks in application code

### Slow Queries
```
Query execution time > 5 seconds
```

**Common Causes:**
- Missing database indexes
- Large result sets
- Complex joins

**Solutions:**
1. Check query execution plan:
   ```sql
   EXPLAIN ANALYZE SELECT * FROM packages WHERE name LIKE 'tensorflow%';
   ```

2. Add missing indexes:
   ```sql
   CREATE INDEX idx_package_search ON packages (name, ecosystem);
   ```

3. Optimize query structure

## ⚡ Performance Issues

### High Memory Usage
**Symptoms:**
- Out of memory errors
- Slow garbage collection
- System instability

**Solutions:**
1. Monitor memory usage:
   ```bash
   docker stats
   ```

2. Adjust Python memory settings:
   ```bash
   PYTHONMALLOC=jemalloc python app.py
   ```

3. Check for memory leaks in async code

### Cache Issues
```
Cache hit rate < 50%
```

**Causes:**
- Redis connection issues
- Short TTL values
- Cache key conflicts

**Solutions:**
1. Verify Redis connectivity
2. Adjust TTL values in settings
3. Monitor cache statistics via health endpoint

## 🔒 Security Issues

### Authentication Failed
```
HTTP 401: Invalid credentials
```

**Solutions:**
1. Verify JWT token format
2. Check token expiration
3. Ensure proper authorization headers

### CORS Errors
```
Access-Control-Allow-Origin error
```

**Solutions:**
1. Add allowed origins to environment:
   ```bash
   ALLOWED_ORIGINS=http://localhost:8080,https://yourdomain.com
   ```

2. Check CORS middleware configuration

## 🌐 External API Issues

### Package Registry Down
```
Error: PyPI/NPM registry unavailable
```

**Fallback Behavior:**
- Uses cached data when available
- Returns partial results with warnings
- Graceful degradation

**Solutions:**
1. Check external service status
2. Use alternative ecosystems
3. Wait for service recovery

### Network Timeouts
```
Connection timeout to external APIs
```

**Solutions:**
1. Increase timeout values in settings
2. Implement retry logic with backoff
3. Use local mirrors if available

## 🔧 Development Issues

### Test Failures
```
pytest failures
```

**Common Issues:**
1. Missing test dependencies
2. Database not initialized for tests
3. Async test setup issues

**Solutions:**
1. Install test dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up test database:
   ```bash
   docker-compose up test-db
   ```

3. Run tests with proper configuration:
   ```bash
   pytest tests/ -v --tb=short
   ```

### Code Quality Issues
```
flake8/black/mypy failures
```

**Solutions:**
1. Auto-format code:
   ```bash
   black .
   ```

2. Fix linting issues:
   ```bash
   flake8 . --max-line-length=127
   ```

3. Check type hints:
   ```bash
   mypy backend/ --ignore-missing-imports
   ```

## 📊 Monitoring Issues

### Missing Metrics
```
Prometheus metrics not available
```

**Solutions:**
1. Verify Prometheus integration:
   ```bash
   curl http://localhost:8000/metrics
   ```

2. Check instrumentation setup in main.py

### Alert Fatigue
```
Too many false positive alerts
```

**Solutions:**
1. Adjust alert thresholds
2. Fine-tune monitoring rules
3. Implement alert silencing

## 🚨 Critical Issues

### Data Loss
**Immediate Actions:**
1. Stop all write operations
2. Create database backup
3. Contact database administrators

### Security Breach
**Immediate Actions:**
1. Rotate all credentials
2. Review access logs
3. Notify security team
4. Follow incident response plan

## 📞 Getting Help

### Support Channels
- **Documentation**: Check this troubleshooting guide
- **Issues**: GitHub Issues for bugs and feature requests
- **Discussions**: GitHub Discussions for questions
- **Email**: support@universal-dependency-resolver.dev

### Diagnostic Information
When reporting issues, include:
- Error messages and stack traces
- Environment details (OS, Python version, etc.)
- Configuration files (redacted)
- Logs from affected services
- Steps to reproduce the issue
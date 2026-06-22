import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const searchDuration = new Trend('search_duration');
const packageInfoDuration = new Trend('package_info_duration');
const healthDuration = new Trend('health_duration');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 10 },  // Ramp up to 10 VUs
    { duration: '1m', target: 20 },   // Stay at 20 VUs
    { duration: '30s', target: 10 },  // Ramp down
    { duration: '30s', target: 0 },   // Cool down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  // 95% of requests must complete within 2s
    errors: ['rate<0.1'],               // Error rate must be below 10%
    http_req_failed: ['rate<0.05'],     // Less than 5% request failure
  },
};

const BASE_URL = __ENV.K6_TARGET_URL || 'http://localhost:8000';

export default function () {
  group('Health Check', () => {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/api/v1/health`);
    const duration = Date.now() - start;
    
    healthDuration.add(duration);
    
    check(res, {
      'health status is 200': (r) => r.status === 200,
      'health body has status': (r) => r.json('status') !== undefined,
    });
    
    errorRate.add(res.status !== 200);
    sleep(1);
  });

  group('Package Search', () => {
    const searchTerms = ['flask', 'numpy', 'tensorflow', 'pandas', 'requests', 'fastapi', 'django', 'scikit-learn'];
    const term = searchTerms[Math.floor(Math.random() * searchTerms.length)];
    
    const start = Date.now();
    const res = http.get(`${BASE_URL}/api/v1/packages/search?q=${term}&limit=10`);
    const duration = Date.now() - start;
    
    searchDuration.add(duration);
    
    check(res, {
      'search status is 200': (r) => r.status === 200,
      'search returns results': (r) => {
        try {
          const body = r.json();
          return body && (body.results || body.data);
        } catch {
          return false;
        }
      },
    });
    
    errorRate.add(res.status !== 200);
    sleep(2);
  });

  group('Package Info', () => {
    const ecosystems = ['pypi', 'npm'];
    const packages = [
      { name: 'flask', ecosystem: 'pypi' },
      { name: 'express', ecosystem: 'npm' },
      { name: 'numpy', ecosystem: 'pypi' },
      { name: 'lodash', ecosystem: 'npm' },
    ];
    
    const pkg = packages[Math.floor(Math.random() * packages.length)];
    
    const start = Date.now();
    const res = http.get(`${BASE_URL}/api/v1/packages/${pkg.ecosystem}/${pkg.name}`);
    const duration = Date.now() - start;
    
    packageInfoDuration.add(duration);
    
    check(res, {
      'package info status is 200': (r) => r.status === 200,
      'package body has name': (r) => r.json('name') !== undefined,
    });
    
    // Try a 404 case occasionally
    if (Math.random() < 0.2) {
      const res404 = http.get(`${BASE_URL}/api/v1/packages/pypi/this-package-does-not-exist-12345`);
      check(res404, {
        'nonexistent package returns 404': (r) => r.status === 404,
      });
    }
    
    errorRate.add(res.status !== 200);
    sleep(3);
  });

  group('System Info', () => {
    const res = http.get(`${BASE_URL}/api/v1/system/info`);
    
    check(res, {
      'system info status is 200': (r) => r.status === 200,
      'system info has os data': (r) => r.json('os') !== undefined,
    });
    
    errorRate.add(res.status !== 200);
    sleep(2);
  });
}

export function teardown() {
  // Log custom metrics summary
  console.log(`Search duration p95: ${searchDuration.avg}ms`);
  console.log(`Package info duration p95: ${packageInfoDuration.avg}ms`);
  console.log(`Health duration p95: ${healthDuration.avg}ms`);
  console.log(`Error rate: ${errorRate.rate}`);
}

// frontend/src/services/packageService.js
import axios from 'axios';

// Base URL for the API - can be configured via environment variable
const API_BASE_URL = process.env.VUE_APP_API_URL || 'http://localhost:8000';
const API_VERSION = 'v1';

// Create axios instance with default config
const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/${API_VERSION}`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 seconds
});

// Add request interceptor for authentication (future use)
apiClient.interceptors.request.use(
  (config) => {
    // Add auth token if available
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Handle rate limiting
    if (error.response?.status === 429) {
      console.error('Rate limit exceeded. Please try again later.');
      // Could implement retry logic here
    }
    
    // Handle authentication errors
    if (error.response?.status === 401) {
      // Redirect to login or refresh token
      localStorage.removeItem('authToken');
      // window.location.href = '/login';
    }
    
    return Promise.reject(error);
  }
);

export default {
  // Search packages across ecosystems
  async searchPackages(query, ecosystems = null, options = {}) {
    try {
      const params = {
        q: query,
        ...options
      };
      
      if (ecosystems && ecosystems.length > 0) {
        params.ecosystems = ecosystems.join(',');
      }
      
      const response = await apiClient.get('/packages/search', { params });
      
      // Add flattening logic if needed
      if (options.flatten && response.data.results) {
        const results = [];
        for (const [eco, packages] of Object.entries(response.data.results)) {
          if (Array.isArray(packages)) {
            packages.forEach(pkg => {
              results.push({ ...pkg, ecosystem: eco });
            });
          }
        }
        return results;
      }

      return response.data;
    } catch (error) {
      console.error('Error searching packages:', error);
      throw error;
    }
  },

  // Get package information - UPDATED ENDPOINT
  async getPackageInfo(ecosystem, packageName) {
    try {
      const response = await apiClient.get(`/packages/${ecosystem}/${packageName}`);
      return response.data;
    } catch (error) {
      console.error('Error fetching package info:', error);
      throw error;
    }
  },

  // Get package versions
  async getPackageVersions(ecosystem, packageName, options = {}) {
    try {
      const response = await apiClient.get(`/packages/${ecosystem}/${packageName}/versions`, {
        params: options
      });
      return response.data;
    } catch (error) {
      console.error('Error fetching package versions:', error);
      throw error;
    }
  },

  // Get package dependencies
  async getPackageDependencies(ecosystem, packageName, version = null, recursive = false) {
    try {
      const params = {};
      if (version) params.version = version;
      if (recursive) params.recursive = recursive;
      
      const response = await apiClient.get(`/packages/${ecosystem}/${packageName}/dependencies`, {
        params
      });
      return response.data;
    } catch (error) {
      console.error('Error fetching dependencies:', error);
      throw error;
    }
  },

  // Get package compatibility
  async getPackageCompatibility(ecosystem, packageName, version = null) {
    try {
      const params = {};
      if (version) params.version = version;
      
      const response = await apiClient.get(`/packages/${ecosystem}/${packageName}/compatibility`, {
        params
      });
      return response.data;
    } catch (error) {
      console.error('Error fetching compatibility:', error);
      throw error;
    }
  },

  // Report compatibility
  async reportCompatibility(ecosystem, packageName, version, systemInfo, works, notes = null) {
    try {
      const data = {
        version,
        system_info: systemInfo,
        works,
        notes
      };
      
      const response = await apiClient.post(
        `/packages/${ecosystem}/${packageName}/compatibility/report`,
        data
      );
      return response.data;
    } catch (error) {
      console.error('Error reporting compatibility:', error);
      throw error;
    }
  },

  // Compare packages
  async comparePackages(packages, aspects = 'all') {
    try {
      const params = {
        packages: packages.join(','),
        aspects
      };
      
      const response = await apiClient.get('/packages/compare', { params });
      return response.data;
    } catch (error) {
      console.error('Error comparing packages:', error);
      throw error;
    }
  },

  // Resolve dependencies - UPDATED ENDPOINT
  async resolveDependencies(packages, systemInfo = null, options = {}) {
    try {
      const data = {
        packages: packages.map(pkg => ({
          name: pkg.name,
          ecosystem: pkg.ecosystem,
          version: pkg.version
        })),
        system_info: systemInfo,
        auto_detect_system: options.autoDetectSystem !== false,
        prefer_compatibility: options.preferCompatibility !== false
      };
      
      const response = await apiClient.post('/packages/resolve', data);
      return response.data;
    } catch (error) {
      console.error('Error resolving dependencies:', error);
      throw error;
    }
  },

  // Export configuration - UPDATED ENDPOINT
  async exportConfiguration(resolvedPackages, format, systemInfo = null, options = {}) {
    try {
      const data = {
        resolved_packages: resolvedPackages,
        format: format,
        system_info: systemInfo,
        options: options
      };
      
      const response = await apiClient.post('/packages/export', data);
      return response.data;
    } catch (error) {
      console.error('Error exporting configuration:', error);
      throw error;
    }
  },

  // Get export formats - UPDATED ENDPOINT
  async getExportFormats() {
    try {
      const response = await apiClient.get('/packages/export-formats');
      return response.data;
    } catch (error) {
      console.error('Error fetching export formats:', error);
      throw error;
    }
  },

  // Helper method to handle errors consistently
  handleError(error) {
    if (error.response) {
      // Server responded with error
      const errorData = error.response.data?.error || error.response.data;
      return {
        message: errorData.message || 'An error occurred',
        status: error.response.status,
        type: errorData.type || 'unknown'
      };
    } else if (error.request) {
      // Request made but no response
      return {
        message: 'No response from server. Please check your connection.',
        status: 0,
        type: 'network_error'
      };
    } else {
      // Something else happened
      return {
        message: error.message || 'An unexpected error occurred',
        status: 0,
        type: 'client_error'
      };
    }
  }
};
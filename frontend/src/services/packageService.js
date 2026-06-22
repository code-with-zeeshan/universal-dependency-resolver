import apiClient from './apiClient'

export default {
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

  async getPackageInfo(ecosystem, packageName) {
    try {
      const response = await apiClient.get(`/packages/${ecosystem}/${packageName}`);
      return response.data;
    } catch (error) {
      console.error('Error fetching package info:', error);
      throw error;
    }
  },

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

  async getExportFormats() {
    try {
      const response = await apiClient.get('/packages/export-formats');
      return response.data;
    } catch (error) {
      console.error('Error fetching export formats:', error);
      throw error;
    }
  }
};

// frontend/src/services/auth.js
import axios from 'axios'

const API_BASE = process.env.VUE_APP_API_URL || 'http://localhost:8000'
const API_VERSION = 'v1'

class AuthService {
  constructor() {
    this.client = axios.create({
      baseURL: `${API_BASE}/api/${API_VERSION}`,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    })

    // Add request interceptor to include auth token
    this.client.interceptors.request.use(
      (config) => {
        const token = this.getToken()
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )

    // Add response interceptor for token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config

        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true

          try {
            const refreshToken = this.getRefreshToken()
            if (refreshToken) {
              const newTokens = await this.refreshAccessToken(refreshToken)
              this.setTokens(newTokens.access_token, newTokens.refresh_token)
              
              // Retry original request with new token
              originalRequest.headers.Authorization = `Bearer ${newTokens.access_token}`
              return this.client(originalRequest)
            }
          } catch (refreshError) {
            this.logout()
            window.location.href = '/login'
          }
        }

        return Promise.reject(error)
      }
    )
  }

  // Token management
  getToken() {
    return localStorage.getItem('access_token')
  }

  getRefreshToken() {
    return localStorage.getItem('refresh_token')
  }

  setTokens(accessToken, refreshToken = null) {
    localStorage.setItem('access_token', accessToken)
    if (refreshToken) {
      localStorage.setItem('refresh_token', refreshToken)
    }
  }

  removeTokens() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  // User management
  getUser() {
    const userStr = localStorage.getItem('user')
    return userStr ? JSON.parse(userStr) : null
  }

  setUser(user) {
    localStorage.setItem('user', JSON.stringify(user))
  }

  removeUser() {
    localStorage.removeItem('user')
  }

  // Check if user is authenticated
  isAuthenticated() {
    const token = this.getToken()
    if (!token) return false

    try {
      // Check if token is expired
      const payload = JSON.parse(atob(token.split('.')[1]))
      const currentTime = Date.now() / 1000
      return payload.exp > currentTime
    } catch {
      return false
    }
  }

  // Authentication methods
  async login(credentials) {
    try {
      const response = await this.client.post('/auth/login', credentials)
      const { access_token, refresh_token, user } = response.data

      this.setTokens(access_token, refresh_token)
      this.setUser(user)

      return {
        success: true,
        user,
        tokens: { access_token, refresh_token }
      }
    } catch (error) {
      return {
        success: false,
        error: this.handleError(error)
      }
    }
  }

  async register(userData) {
    try {
      const response = await this.client.post('/auth/register', userData)
      return {
        success: true,
        user: response.data.user,
        message: 'Registration successful'
      }
    } catch (error) {
      return {
        success: false,
        error: this.handleError(error)
      }
    }
  }

  async refreshAccessToken(refreshToken) {
    try {
      const response = await this.client.post('/auth/refresh', {
        refresh_token: refreshToken
      })
      return response.data
    } catch (error) {
      throw this.handleError(error)
    }
  }

  logout() {
    this.removeTokens()
    this.removeUser()
    
    // Optional: Call logout endpoint to invalidate tokens on server
    this.client.post('/auth/logout').catch(() => {
      // Ignore errors on logout
    })
  }

  // API Key management
  async getApiKeys() {
    try {
      const response = await this.client.get('/auth/api-keys')
      return {
        success: true,
        keys: response.data.keys
      }
    } catch (error) {
      return {
        success: false,
        error: this.handleError(error)
      }
    }
  }

  async createApiKey(keyData) {
    try {
      const response = await this.client.post('/auth/api-keys', keyData)
      return {
        success: true,
        key: response.data.key
      }
    } catch (error) {
      return {
        success: false,
        error: this.handleError(error)
      }
    }
  }

  async revokeApiKey(keyId) {
    try {
      await this.client.delete(`/auth/api-keys/${keyId}`)
      return { success: true }
    } catch (error) {
      return {
        success: false,
        error: this.handleError(error)
      }
    }
  }

  // User profile methods
  async getProfile() {
    try {
      const response = await this.client.get('/auth/profile')
      return {
        success: true,
        user: response.data.user
      }
    } catch (error) {
      return {
        success: false,
        error: this.handleError(error)
      }
    }
  }

  async updateProfile(profileData) {
    try {
      const response = await this.client.put('/auth/profile', profileData)
      const updatedUser = response.data.user
      this.setUser(updatedUser)
      
      return {
        success: true,
        user: updatedUser
      }
    } catch (error) {
      return {
        success: false,
        error: this.handleError(error)
      }
    }
  }

  async changePassword(passwordData) {
    try {
      await this.client.post('/auth/change-password', passwordData)
      return {
        success: true,
        message: 'Password changed successfully'
      }
    } catch (error) {
      return {
        success: false,
        error: this.handleError(error)
      }
    }
  }

  // Permission checking
  hasScope(requiredScope) {
    const user = this.getUser()
    if (!user || !user.scopes) return false
    return user.scopes.includes(requiredScope)
  }

  hasAnyScope(requiredScopes) {
    const user = this.getUser()
    if (!user || !user.scopes) return false
    return requiredScopes.some(scope => user.scopes.includes(scope))
  }

  hasAllScopes(requiredScopes) {
    const user = this.getUser()
    if (!user || !user.scopes) return false
    return requiredScopes.every(scope => user.scopes.includes(scope))
  }

  // Helper methods
  handleError(error) {
    if (error.response) {
      const errorData = error.response.data?.error || error.response.data
      return {
        message: errorData.message || 'An error occurred',
        status: error.response.status,
        type: errorData.type || 'unknown'
      }
    } else if (error.request) {
      return {
        message: 'No response from server. Please check your connection.',
        status: 0,
        type: 'network_error'
      }
    } else {
      return {
        message: error.message || 'An unexpected error occurred',
        status: 0,
        type: 'client_error'
      }
    }
  }

  // Initialize auth state from storage
  initializeAuth() {
    const user = this.getUser()
    const token = this.getToken()
    
    if (user && token && this.isAuthenticated()) {
      return { authenticated: true, user }
    } else {
      this.logout() // Clean up invalid state
      return { authenticated: false, user: null }
    }
  }
}

export default new AuthService()
import apiClient from './apiClient'
import jwt_decode from 'jwt-decode'

class AuthService {
  constructor() {
    this.client = apiClient

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

  isAuthenticated() {
    const token = this.getToken()
    if (!token) return false

    try {
      const payload = jwt_decode(token)
      const currentTime = Date.now() / 1000
      return payload.exp > currentTime
    } catch {
      return false
    }
  }

  async login(credentials) {
    try {
      const response = await this.client.post('/auth/login', credentials)
      const { access_token, refresh_token } = response.data

      this.setTokens(access_token, refresh_token)

      return {
        success: true,
        tokens: { access_token, refresh_token }
      }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.message || error.message || 'An error occurred'
      }
    }
  }

  async register(userData) {
    try {
      const response = await this.client.post('/auth/register', userData)
      return {
        success: true,
        user: response.data,
        message: 'Registration successful'
      }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.message || error.message || 'An error occurred'
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
      throw error
    }
  }

  logout() {
    this.removeTokens()
    this.removeUser()

    this.client.post('/auth/logout').catch(() => {})
  }

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
        error: error.response?.data?.message || error.message || 'An error occurred'
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
        error: error.response?.data?.message || error.message || 'An error occurred'
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
        error: error.response?.data?.message || error.message || 'An error occurred'
      }
    }
  }

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
        error: error.response?.data?.message || error.message || 'An error occurred'
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
        error: error.response?.data?.message || error.message || 'An error occurred'
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
        error: error.response?.data?.message || error.message || 'An error occurred'
      }
    }
  }

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

  initializeAuth() {
    const user = this.getUser()
    const token = this.getToken()

    if (user && token && this.isAuthenticated()) {
      return { authenticated: true, user }
    } else {
      this.logout()
      return { authenticated: false, user: null }
    }
  }
}

export default new AuthService()

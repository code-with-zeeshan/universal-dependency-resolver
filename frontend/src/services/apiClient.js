import axios from 'axios'

let baseUrl = process.env.VUE_APP_API_URL || ''
if (!baseUrl && window.__UDR_BACKEND_URL__) {
  baseUrl = window.__UDR_BACKEND_URL__
}

const API_VERSION = 'v1'

const apiClient = axios.create({
  baseURL: `${baseUrl}/api/${API_VERSION}`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 429) {
      console.error('Rate limit exceeded. Please try again later.')
    }
    return Promise.reject(error)
  }
)

export default apiClient

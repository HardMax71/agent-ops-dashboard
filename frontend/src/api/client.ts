import axios, { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

let accessTokenRef = ''
let isRefreshing = false

export function setAccessToken(token: string): void {
  accessTokenRef = token
}

export function getAccessToken(): string {
  return accessTokenRef
}

const apiClient: AxiosInstance = axios.create({
  baseURL: '/api',
  withCredentials: true,
})

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessTokenRef) {
    config.headers.Authorization = `Bearer ${accessTokenRef}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(error)
    }
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        window.location.href = '/login'
        return Promise.reject(error)
      }
      originalRequest._retry = true
      isRefreshing = true
      const refreshResponse = await apiClient.post<{ access_token: string }>('/auth/refresh')
      isRefreshing = false
      setAccessToken(refreshResponse.data.access_token)
      originalRequest.headers.Authorization = `Bearer ${accessTokenRef}`
      return apiClient(originalRequest)
    }
    if (error.response?.status === 401 && (error.config as InternalAxiosRequestConfig & { _retry?: boolean })._retry) {
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient

import axios from 'axios'

export const TOKEN_KEY = 'reconflow.access_token'
export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api', timeout: 80000 })
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
api.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401 && !String(error.config?.url || '').endsWith('/auth/login')) {
    sessionStorage.removeItem(TOKEN_KEY)
    window.dispatchEvent(new Event('reconflow:unauthorized'))
  }
  return Promise.reject(error)
})

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail?.message) return String(detail.message)
    if (Array.isArray(detail)) return detail.map((item) => {
      const field = Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== 'body').join('.') : ''
      return `${field ? `${field}: ` : ''}${item.msg || 'Invalid value'}`
    }).join('; ')
    if (error.code === 'ERR_NETWORK') return 'Could not connect to ReconFlow API. Check that the backend is running.'
    return error.message || 'The request could not be completed.'
  }
  return error instanceof Error ? error.message : 'Something went wrong.'
}

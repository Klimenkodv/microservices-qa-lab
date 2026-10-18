import { ApiError, type PersonalProfile, type ProfileChanges, type RegisterResponse, type User } from '../types/api'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init.headers },
      signal: controller.signal,
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      const fields = Array.isArray(body.detail) ? body.detail : []
      throw new ApiError(response.status, body.code ?? 'HTTP_ERROR', body.message ?? 'Request failed', fields, body.trace_id)
    }
    return response.json() as Promise<T>
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(null, 'NETWORK_ERROR', 'Сервис не отвечает. Попробуйте позже.')
  } finally {
    window.clearTimeout(timeout)
  }
}

export const authApi = {
  register: (email: string, password: string) => request<RegisterResponse>('/api/v1/register', { method: 'POST', body: JSON.stringify({ email, password }) }),
  getMe: (token: string) => request<User>('/api/v1/me', { headers: { Authorization: `Bearer ${token}` } }),
  getProfile: (token: string) => request<PersonalProfile>('/api/v1/profile', { headers: { Authorization: `Bearer ${token}` } }),
  updateProfile: (token: string, changes: Partial<ProfileChanges>) => request<PersonalProfile>('/api/v1/profile', {
    method: 'PATCH', headers: { Authorization: `Bearer ${token}` }, body: JSON.stringify(changes),
  }),
}

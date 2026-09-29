import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { authApi } from '../api/authApi'
import type { User } from '../types/api'

const TOKEN_KEY = 'qa_lab_access_token'
type AuthContextValue = {
  user: User | null
  token: string | null
  register: (email: string, password: string) => Promise<User>
  loadProfile: () => Promise<User>
  logout: () => void
}
const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY))
  const value = useMemo<AuthContextValue>(() => ({
    user,
    token,
    async register(email, password) {
      const result = await authApi.register(email, password)
      sessionStorage.setItem(TOKEN_KEY, result.access_token)
      setToken(result.access_token)
      const nextUser = { user_id: result.user_id, email: result.email, created_at: result.created_at }
      setUser(nextUser)
      return nextUser
    },
    async loadProfile() {
      const savedToken = sessionStorage.getItem(TOKEN_KEY)
      if (!savedToken) throw new Error('NO_TOKEN')
      const profile = await authApi.getMe(savedToken)
      setUser(profile)
      return profile
    },
    logout() { sessionStorage.removeItem(TOKEN_KEY); setToken(null); setUser(null) },
  }), [token, user])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

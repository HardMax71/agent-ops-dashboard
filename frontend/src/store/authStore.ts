import { create } from 'zustand'
import type { UserInfo } from '../types'
import { setAccessToken } from '../api/client'

interface AuthState {
  user: UserInfo | null
  isAuthenticated: boolean
  setUser: (user: UserInfo | null) => void
  setToken: (token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  setUser: (user) => set({ user, isAuthenticated: user !== null }),
  setToken: (token) => {
    setAccessToken(token)
    set({ isAuthenticated: true })
  },
  logout: () => {
    setAccessToken('')
    set({ user: null, isAuthenticated: false })
  },
}))

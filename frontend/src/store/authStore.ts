import { create } from 'zustand'
import type { UserInfo } from '../generated/schema'
import { setAccessToken } from '../api/graphqlClient'

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

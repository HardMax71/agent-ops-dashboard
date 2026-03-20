import { create } from 'zustand'
import type { UserInfo } from '../generated/schema'
import { setAccessToken, gql } from '../api/graphqlClient'

interface AuthState {
  user: UserInfo | null
  isAuthenticated: boolean
  isLoading: boolean
  setUser: (user: UserInfo | null) => void
  setToken: (token: string) => void
  logout: () => void
  restoreSession: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  setUser: (user) => set({ user, isAuthenticated: user !== null }),
  setToken: (token) => {
    setAccessToken(token)
    set({ isAuthenticated: true })
  },
  logout: () => {
    setAccessToken('')
    set({ user: null, isAuthenticated: false, isLoading: false })
  },
  restoreSession: async () => {
    try {
      const resp = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
      })
      if (!resp.ok) {
        set({ isLoading: false })
        return
      }
      const data = await resp.json() as { access_token: string }
      setAccessToken(data.access_token)
      set({ isAuthenticated: true })
      const meResult = await gql.query({ me: { __scalar: true } })
      set({ user: meResult.me, isLoading: false })
    } catch {
      set({ isLoading: false })
    }
  },
}))

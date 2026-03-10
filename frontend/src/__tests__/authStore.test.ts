import { describe, it, expect, beforeEach, vi } from 'vitest'

const mockSetAccessToken = vi.fn()
const mockQuery = vi.fn()

vi.mock('../api/graphqlClient', () => ({
  setAccessToken: (...args: unknown[]) => mockSetAccessToken(...args),
  gql: { query: (...args: unknown[]) => mockQuery(...args) },
}))

import { useAuthStore } from '../store/authStore'

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: true,
    })
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    mockSetAccessToken.mockClear()
    mockQuery.mockClear()
  })

  describe('setUser', () => {
    it('sets user and isAuthenticated=true when user is provided', () => {
      const user = { githubId: '1', githubLogin: 'alice', avatarUrl: 'https://example.com/a.png', __typename: 'UserInfo' as const }
      useAuthStore.getState().setUser(user)
      const state = useAuthStore.getState()
      expect(state.user).toEqual(user)
      expect(state.isAuthenticated).toBe(true)
    })

    it('sets isAuthenticated=false when user is null', () => {
      useAuthStore.getState().setUser(null)
      expect(useAuthStore.getState().isAuthenticated).toBe(false)
    })
  })

  describe('setToken', () => {
    it('calls setAccessToken and sets isAuthenticated=true', () => {
      useAuthStore.getState().setToken('tok-123')
      expect(mockSetAccessToken).toHaveBeenCalledWith('tok-123')
      expect(useAuthStore.getState().isAuthenticated).toBe(true)
    })
  })

  describe('logout', () => {
    it('clears user and sets isAuthenticated=false and isLoading=false', () => {
      useAuthStore.setState({ user: { githubId: '2', githubLogin: 'x', avatarUrl: '', __typename: 'UserInfo' as const }, isAuthenticated: true, isLoading: true })
      useAuthStore.getState().logout()
      const state = useAuthStore.getState()
      expect(state.user).toBeNull()
      expect(state.isAuthenticated).toBe(false)
      expect(state.isLoading).toBe(false)
      expect(mockSetAccessToken).toHaveBeenCalledWith('')
    })
  })

  describe('restoreSession', () => {
    it('happy path: refreshes token, queries user, sets state', async () => {
      const mockUser = { githubId: '3', githubLogin: 'bob', avatarUrl: 'https://example.com/b.png', __typename: 'UserInfo' as const }
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ access_token: 'new-tok' }),
      }))
      mockQuery.mockResolvedValue({ me: mockUser })

      await useAuthStore.getState().restoreSession()

      expect(mockSetAccessToken).toHaveBeenCalledWith('new-tok')
      expect(mockQuery).toHaveBeenCalledWith({ me: { __scalar: true } })
      const state = useAuthStore.getState()
      expect(state.user).toEqual(mockUser)
      expect(state.isAuthenticated).toBe(true)
      expect(state.isLoading).toBe(false)
    })

    it('sets isLoading=false when fetch returns non-ok', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))

      await useAuthStore.getState().restoreSession()

      expect(useAuthStore.getState().isLoading).toBe(false)
      expect(useAuthStore.getState().user).toBeNull()
      expect(mockSetAccessToken).not.toHaveBeenCalled()
    })

    it('sets isLoading=false when fetch throws', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')))

      await useAuthStore.getState().restoreSession()

      expect(useAuthStore.getState().isLoading).toBe(false)
      expect(useAuthStore.getState().user).toBeNull()
    })
  })
})

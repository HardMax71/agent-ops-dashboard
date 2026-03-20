import { describe, it, expect } from 'vitest'
import { setAccessToken, getAccessToken } from '../api/graphqlClient'

describe('graphqlClient token management', () => {
  it('defaults to empty string', () => {
    setAccessToken('')
    expect(getAccessToken()).toBe('')
  })

  it('round-trips a token', () => {
    setAccessToken('my-token-123')
    expect(getAccessToken()).toBe('my-token-123')
  })

  it('overwrites a previously set token', () => {
    setAccessToken('first')
    setAccessToken('second')
    expect(getAccessToken()).toBe('second')
  })
})

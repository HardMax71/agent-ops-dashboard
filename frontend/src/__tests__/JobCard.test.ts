import { describe, it, expect, vi, afterEach } from 'vitest'
import { formatTimeAgo, extractRepo } from '../components/JobCard'

describe('formatTimeAgo', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it.each([
    { input: undefined, expected: '', label: 'undefined returns empty string' },
  ])('$label', ({ input, expected }) => {
    expect(formatTimeAgo(input)).toBe(expected)
  })

  it('returns "just now" for current time', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    expect(formatTimeAgo('2026-01-01T00:00:00Z')).toBe('just now')
  })

  it('returns "5m ago" for 5 minutes ago', () => {
    vi.useFakeTimers()
    const now = new Date('2026-01-01T00:05:00Z')
    vi.setSystemTime(now)
    expect(formatTimeAgo('2026-01-01T00:00:00Z')).toBe('5m ago')
  })

  it('returns "59m ago" for 59 minutes ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:59:00Z'))
    expect(formatTimeAgo('2026-01-01T00:00:00Z')).toBe('59m ago')
  })

  it('returns "1h ago" for 60 minutes ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T01:00:00Z'))
    expect(formatTimeAgo('2026-01-01T00:00:00Z')).toBe('1h ago')
  })

  it('returns "23h ago" for 23 hours ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T23:00:00Z'))
    expect(formatTimeAgo('2026-01-01T00:00:00Z')).toBe('23h ago')
  })

  it('returns "1d ago" for 24 hours ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-02T00:00:00Z'))
    expect(formatTimeAgo('2026-01-01T00:00:00Z')).toBe('1d ago')
  })

  it('returns "3d ago" for 72 hours ago', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-04T00:00:00Z'))
    expect(formatTimeAgo('2026-01-01T00:00:00Z')).toBe('3d ago')
  })
})

describe('extractRepo', () => {
  it.each([
    { input: 'https://github.com/owner/repo/issues/123', expected: 'owner/repo', label: 'extracts owner/repo from github URL' },
    { input: 'https://github.com/my-org/my-repo/issues/1', expected: 'my-org/my-repo', label: 'handles hyphenated org and repo' },
    { input: 'not-a-github-url', expected: 'not-a-github-url', label: 'returns input for non-github URL' },
    { input: 'https://example.com/foo', expected: 'https://example.com/foo', label: 'returns input for non-github domain' },
  ])('$label', ({ input, expected }) => {
    expect(extractRepo(input)).toBe(expected)
  })
})

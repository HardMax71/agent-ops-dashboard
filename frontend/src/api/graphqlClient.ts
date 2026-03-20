import { createClient, generateSubscriptionOp, everything } from '../generated'
import { createClient as createWsClient } from 'graphql-ws'

let accessToken = ''

export function setAccessToken(token: string): void {
  accessToken = token
}

export function getAccessToken(): string {
  return accessToken
}

// Queries & mutations — GenQL client with dynamic auth headers
export const gql = createClient({
  url: '/graphql',
  headers: (): Record<string, string> => {
    return accessToken ? { Authorization: `Bearer ${accessToken}` } : {}
  },
})

// Subscriptions — graphql-ws with connectionParams auth
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const wsClient = createWsClient({
  url: `${wsProtocol}//${window.location.host}/graphql`,
  connectionParams: () => ({
    Authorization: `Bearer ${accessToken}`,
  }),
})

export function subscribe<T>(
  op: { query: string; variables?: Record<string, unknown> },
  onData: (data: T) => void,
  onError?: (err: unknown) => void,
): () => void {
  console.log('[ws] subscribing', op.query?.substring(0, 80))
  const cleanup = wsClient.subscribe(op, {
    next: (result) => {
      console.log('[ws] next', result)
      if (result.data) onData(result.data as T)
    },
    error: (err) => { console.error('[ws] error', err); onError?.(err) },
    complete: () => { console.log('[ws] complete') },
  })
  return cleanup
}

export { generateSubscriptionOp, everything }

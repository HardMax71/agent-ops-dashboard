import { useEffect, useRef } from 'react'
import { useJobStore } from '../store/jobStore'
import type { SSEEvent } from '../types'
import { getAccessToken } from '../api/client'

export function useJobStream(jobId: string | null): void {
  const processSSEEvent = useJobStore((s) => s.processSSEEvent)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!jobId) return

    const token = getAccessToken()
    const url = token
      ? `/api/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`
      : `/api/jobs/${jobId}/stream`

    const es = new EventSource(url, { withCredentials: true })
    eventSourceRef.current = es

    es.onmessage = (e: MessageEvent<string>) => {
      const event = JSON.parse(e.data) as SSEEvent
      processSSEEvent(event)
    }

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
      eventSourceRef.current = null
    }
  }, [jobId, processSSEEvent])
}

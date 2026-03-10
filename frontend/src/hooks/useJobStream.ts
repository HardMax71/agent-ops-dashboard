import { useEffect, useRef } from 'react'
import { generateSubscriptionOp, subscribe } from '../api/graphqlClient'
import { useJobStore } from '../store/jobStore'
import type { JobEvent } from '../generated/schema'

export function useJobStream(jobId: string | null): void {
  const processJobEvent = useJobStore((s) => s.processJobEvent)
  const cleanupRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (!jobId) return

    const op = generateSubscriptionOp({
      jobEvents: {
        __args: { jobId },
        on_AgentSpawnedEvent: { __scalar: true },
        on_AgentTokenEvent: { __scalar: true },
        on_OutputTokenEvent: { __scalar: true },
        on_AgentToolCallEvent: { __scalar: true },
        on_AgentToolResultEvent: { __scalar: true },
        on_AgentDoneEvent: { __scalar: true },
        on_OutputSectionDoneEvent: { __scalar: true },
        on_GraphNodeCompleteEvent: { __scalar: true },
        on_GraphInterruptEvent: { __scalar: true },
        on_JobDoneEvent: { __scalar: true },
        on_JobFailedEvent: { __scalar: true },
        on_JobKilledEvent: { __scalar: true },
        on_JobTimedOutEvent: { __scalar: true },
      },
    })

    cleanupRef.current = subscribe<{ jobEvents: JobEvent }>(op, (data) => {
      processJobEvent(jobId, data.jobEvents)
    })

    return () => {
      cleanupRef.current?.()
      cleanupRef.current = null
    }
  }, [jobId, processJobEvent])
}

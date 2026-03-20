import { create } from 'zustand'
import type { JobEvent } from '../generated/schema'
import { generateSubscriptionOp, subscribe } from '../api/graphqlClient'

export type JobStatus =
  | 'queued'
  | 'running'
  | 'waiting'
  | 'pausing'
  | 'paused'
  | 'done'
  | 'failed'
  | 'killed'
  | 'timed_out'

const TERMINAL: Set<JobStatus> = new Set(['done', 'failed', 'killed', 'timed_out'])

export interface AgentFinding {
  agentName: string
  summary: string
  confidence: number
  hypothesis?: string
  affectedAreas?: string[]
  keywordsForSearch?: string[]
  errorMessages?: string[]
  relevantFiles?: string[]
  rootCauseLocation?: string
  verdict?: string
  gaps?: string[]
}

export interface HumanExchange {
  question: string
  answer: string
  askedAt?: string
  answeredAt?: string
}

export interface TriageReport {
  severity: 'critical' | 'high' | 'medium' | 'low'
  rootCause: string
  relevantFiles: string[]
  recommendedFix: string
  confidence: number
  githubComment: string
  ticketDraft: Record<string, string>
}

export interface JobLocal {
  jobId: string
  status: JobStatus
  issueUrl: string
  issueTitle?: string
  repository?: string
  currentNode?: string
  awaitingHuman?: boolean
  pendingQuestion?: string
  pendingQuestionContext?: string
  langsmithUrl?: string
  findings?: AgentFinding[]
  report?: TriageReport
  humanExchanges?: HumanExchange[]
  createdAt?: string
}

interface JobStore {
  jobs: Record<string, JobLocal>
  selectedJobId: string | null
  agentTokens: Record<string, string>
  setJob: (job: JobLocal) => void
  updateJob: (jobId: string, updates: Partial<JobLocal>) => void
  selectJob: (jobId: string) => void
  appendToken: (jobId: string, token: string) => void
  processJobEvent: (jobId: string, event: JobEvent) => void
}

// Subscription cleanup functions keyed by jobId
const _subscriptions: Record<string, () => void> = {}

function _ensureSubscription(jobId: string, status: JobStatus, processJobEvent: (jobId: string, event: JobEvent) => void): void {
  if (TERMINAL.has(status)) {
    // Clean up subscription for terminal jobs
    _subscriptions[jobId]?.()
    delete _subscriptions[jobId]
    return
  }
  if (_subscriptions[jobId]) return // already subscribed

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

  _subscriptions[jobId] = subscribe<{ jobEvents: JobEvent }>(op, (data) => {
    processJobEvent(jobId, data.jobEvents)
  })
}

export const useJobStore = create<JobStore>((set, get) => ({
  jobs: {},
  selectedJobId: null,
  agentTokens: {},

  setJob: (job) => {
    set((state) => ({ jobs: { ...state.jobs, [job.jobId]: job } }))
    _ensureSubscription(job.jobId, job.status, get().processJobEvent)
  },

  updateJob: (jobId, updates) =>
    set((state) => {
      const existing = state.jobs[jobId]
      if (!existing) return state
      const updated = { ...existing, ...updates }
      if (updates.status) {
        _ensureSubscription(jobId, updated.status, get().processJobEvent)
      }
      return {
        jobs: { ...state.jobs, [jobId]: updated },
      }
    }),

  selectJob: (jobId) => set({ selectedJobId: jobId }),

  appendToken: (jobId, token) =>
    set((state) => {
      const node = state.jobs[jobId]?.currentNode || '_output'
      const key = `${jobId}:${node}`
      return {
        agentTokens: {
          ...state.agentTokens,
          [key]: (state.agentTokens[key] || '') + token,
        },
      }
    }),

  processJobEvent: (jobId, event) => {
    const { jobs } = get()
    const currentJob = jobs[jobId]
    if (!currentJob) return

    if (event.__typename === 'AgentSpawnedEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, currentNode: event.node, status: 'running' },
        },
      }))
    } else if (event.__typename === 'AgentTokenEvent') {
      get().appendToken(jobId, event.token)
    } else if (event.__typename === 'OutputTokenEvent') {
      get().appendToken(jobId, event.token)
    } else if (event.__typename === 'GraphNodeCompleteEvent') {
      // Node completed
    } else if (event.__typename === 'GraphInterruptEvent') {
      set((state) => {
        const existing = state.jobs[jobId]!
        const exchanges = existing.humanExchanges ? [...existing.humanExchanges] : []
        exchanges.push({ question: event.question, answer: '' })
        return {
          jobs: {
            ...state.jobs,
            [jobId]: {
              ...existing,
              awaitingHuman: true,
              status: 'waiting',
              pendingQuestion: event.question,
              pendingQuestionContext: event.context,
              humanExchanges: exchanges,
            },
          },
        }
      })
      _ensureSubscription(jobId, 'waiting', get().processJobEvent)
    } else if (event.__typename === 'JobDoneEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'done' },
        },
      }))
      _ensureSubscription(jobId, 'done', get().processJobEvent)
    } else if (event.__typename === 'JobFailedEvent' || event.__typename === 'JobTimedOutEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'failed' },
        },
      }))
      _ensureSubscription(jobId, 'failed', get().processJobEvent)
    } else if (event.__typename === 'JobKilledEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'killed' },
        },
      }))
      _ensureSubscription(jobId, 'killed', get().processJobEvent)
    }
  },
}))

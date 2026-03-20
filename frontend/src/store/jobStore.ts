import { create } from 'zustand'
import type { JobEvent } from '../generated/schema'
import { gql, generateSubscriptionOp, subscribe } from '../api/graphqlClient'

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

// Synthetic event for user answers (not from subscription)
export interface HumanAnswerEntry {
  __typename: 'HumanAnswerEntry'
  answer: string
}

export type LogEntry = JobEvent | HumanAnswerEntry

// Events worth showing in the activity log (skip noisy token streams)
const LOG_WORTHY = new Set([
  'AgentSpawnedEvent',
  'AgentDoneEvent',
  'AgentToolCallEvent',
  'AgentToolResultEvent',
  'GraphInterruptEvent',
  'JobDoneEvent',
  'JobFailedEvent',
  'JobKilledEvent',
  'JobTimedOutEvent',
  'JobSnapshotEvent',
])

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
  eventLog: Record<string, LogEntry[]>
  setJob: (job: JobLocal) => void
  updateJob: (jobId: string, updates: Partial<JobLocal>) => void
  selectJob: (jobId: string) => void
  appendToken: (jobId: string, token: string) => void
  pushEvent: (jobId: string, entry: LogEntry) => void
  processJobEvent: (jobId: string, event: JobEvent) => void
}

// Subscription cleanup functions keyed by jobId
const _subscriptions: Record<string, () => void> = {}

function _ensureSubscription(
  jobId: string,
  status: JobStatus,
  processJobEvent: (jobId: string, event: JobEvent) => void,
): void {
  if (TERMINAL.has(status)) {
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
      on_JobSnapshotEvent: { __scalar: true },
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
  eventLog: {},

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

  pushEvent: (jobId, entry) => {
    if (!LOG_WORTHY.has(entry.__typename)) return

    // Supervisor runs between every node — its start/done events are noise
    if (
      (entry.__typename === 'AgentSpawnedEvent' || entry.__typename === 'AgentDoneEvent')
      && entry.node === 'supervisor'
    ) return

    // Deduplicate consecutive identical events (nested chains emit duplicates)
    const log = get().eventLog[jobId]
    if (log && log.length > 0) {
      const prev = log[log.length - 1]
      if (prev.__typename === entry.__typename) {
        const same =
          (entry.__typename === 'AgentSpawnedEvent' && prev.__typename === 'AgentSpawnedEvent' && prev.node === entry.node)
          || (entry.__typename === 'AgentDoneEvent' && prev.__typename === 'AgentDoneEvent' && prev.node === entry.node)
          || (entry.__typename === 'AgentToolCallEvent' && prev.__typename === 'AgentToolCallEvent'
              && prev.toolName === entry.toolName && prev.inputPreview === entry.inputPreview)
        if (same) return
      }
    }

    set((state) => ({
      eventLog: {
        ...state.eventLog,
        [jobId]: [...(state.eventLog[jobId] || []), entry],
      },
    }))
  },

  processJobEvent: (jobId, event) => {
    const { jobs, pushEvent } = get()
    const currentJob = jobs[jobId]
    if (!currentJob) return

    // Log every event (pushEvent filters by LOG_WORTHY)
    pushEvent(jobId, event)

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
    } else if (event.__typename === 'JobSnapshotEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: {
            ...state.jobs[jobId]!,
            status: event.status as JobStatus,
            currentNode: event.currentNode,
            awaitingHuman: event.awaitingHuman,
            pendingQuestion: event.pendingQuestion,
            pendingQuestionContext: event.pendingQuestionContext,
          },
        },
      }))
    } else if (event.__typename === 'JobDoneEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'done' },
        },
      }))
      _ensureSubscription(jobId, 'done', get().processJobEvent)
      gql.query({ job: { __args: { jobId }, __scalar: true, relevantFiles: true } })
        .then((result) => {
          const j = result.job
          if (j.severity) {
            set((state) => ({
              jobs: {
                ...state.jobs,
                [jobId]: {
                  ...state.jobs[jobId]!,
                  report: {
                    severity: j.severity as 'critical' | 'high' | 'medium' | 'low',
                    rootCause: j.recommendedFix || '',
                    relevantFiles: j.relevantFiles || [],
                    recommendedFix: j.recommendedFix || '',
                    confidence: 0,
                    githubComment: j.githubComment || '',
                    ticketDraft: {},
                  },
                },
              },
            }))
          }
        })
        .catch(() => {})
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

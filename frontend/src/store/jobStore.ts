import { create } from 'zustand'
import type { JobEvent } from '../generated/schema'

export type JobStatus =
  | 'queued'
  | 'running'
  | 'waiting'
  | 'paused'
  | 'done'
  | 'failed'
  | 'killed'

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

export const useJobStore = create<JobStore>((set, get) => ({
  jobs: {},
  selectedJobId: null,
  agentTokens: {},

  setJob: (job) =>
    set((state) => ({ jobs: { ...state.jobs, [job.jobId]: job } })),

  updateJob: (jobId, updates) =>
    set((state) => {
      const existing = state.jobs[jobId]
      if (!existing) return state
      return {
        jobs: {
          ...state.jobs,
          [jobId]: { ...existing, ...updates },
        },
      }
    }),

  selectJob: (jobId) => set({ selectedJobId: jobId }),

  appendToken: (jobId, token) =>
    set((state) => ({
      agentTokens: {
        ...state.agentTokens,
        [jobId]: (state.agentTokens[jobId] || '') + token,
      },
    })),

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
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, awaitingHuman: true, status: 'waiting' },
        },
      }))
    } else if (event.__typename === 'JobDoneEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'done' },
        },
      }))
    } else if (event.__typename === 'JobFailedEvent' || event.__typename === 'JobTimedOutEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'failed' },
        },
      }))
    } else if (event.__typename === 'JobKilledEvent') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'killed' },
        },
      }))
    }
  },
}))

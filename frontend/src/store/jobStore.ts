import { create } from 'zustand'
import type { Job, SSEEvent } from '../types'

interface JobStore {
  jobs: Record<string, Job>
  selectedJobId: string | null
  agentTokens: Record<string, string>
  setJob: (job: Job) => void
  updateJob: (jobId: string, updates: Partial<Job>) => void
  selectJob: (jobId: string) => void
  appendToken: (jobId: string, token: string) => void
  processSSEEvent: (event: SSEEvent) => void
}

export const useJobStore = create<JobStore>((set, get) => ({
  jobs: {},
  selectedJobId: null,
  agentTokens: {},

  setJob: (job) =>
    set((state) => ({ jobs: { ...state.jobs, [job.job_id]: job } })),

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

  processSSEEvent: (event) => {
    const jobId = event.job_id
    if (!jobId) return

    const { jobs } = get()
    const currentJob = jobs[jobId]
    if (!currentJob) return

    if (event.type === 'graph.node_start') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, current_node: event.node || '', status: 'running' },
        },
      }))
    } else if (event.type === 'graph.node_complete') {
      // Node completed
    } else if (event.type === 'graph.interrupt') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, awaiting_human: true, status: 'waiting' },
        },
      }))
    } else if (event.type === 'graph.resumed') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, awaiting_human: false, status: 'running' },
        },
      }))
    } else if (event.type === 'graph.paused') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'paused' },
        },
      }))
    } else if (event.type === 'job.done') {
      set((state) => ({
        jobs: {
          ...state.jobs,
          [jobId]: { ...state.jobs[jobId]!, status: 'done' },
        },
      }))
    } else if (event.type === 'output.token' && event.token) {
      get().appendToken(jobId, event.token)
    }
  },
}))

import { describe, it, expect, beforeEach } from 'vitest'
import { useJobStore } from '../store/jobStore'
import type { JobLocal } from '../store/jobStore'
import type { JobEvent } from '../generated/schema'

function makeJob(overrides: Partial<JobLocal> = {}): JobLocal {
  return {
    jobId: 'job-1',
    status: 'queued',
    issueUrl: 'https://github.com/org/repo/issues/1',
    ...overrides,
  }
}

describe('jobStore', () => {
  beforeEach(() => {
    useJobStore.setState({ jobs: {}, selectedJobId: null, agentTokens: {} })
  })

  describe('setJob', () => {
    it('adds a new job', () => {
      const job = makeJob()
      useJobStore.getState().setJob(job)
      expect(useJobStore.getState().jobs['job-1']).toEqual(job)
    })

    it('overwrites an existing job', () => {
      useJobStore.getState().setJob(makeJob())
      const updated = makeJob({ status: 'running' })
      useJobStore.getState().setJob(updated)
      expect(useJobStore.getState().jobs['job-1']?.status).toBe('running')
    })
  })

  describe('updateJob', () => {
    it('partially merges updates into existing job', () => {
      useJobStore.getState().setJob(makeJob())
      useJobStore.getState().updateJob('job-1', { status: 'done', currentNode: 'writer' })
      const job = useJobStore.getState().jobs['job-1']
      expect(job?.status).toBe('done')
      expect(job?.currentNode).toBe('writer')
      expect(job?.issueUrl).toBe('https://github.com/org/repo/issues/1')
    })

    it('is a no-op for missing jobId', () => {
      useJobStore.getState().setJob(makeJob())
      useJobStore.getState().updateJob('nonexistent', { status: 'done' })
      expect(useJobStore.getState().jobs['nonexistent']).toBeUndefined()
      expect(useJobStore.getState().jobs['job-1']?.status).toBe('queued')
    })
  })

  describe('selectJob', () => {
    it('sets selectedJobId', () => {
      useJobStore.getState().selectJob('job-1')
      expect(useJobStore.getState().selectedJobId).toBe('job-1')
    })
  })

  describe('appendToken', () => {
    it('keys by jobId:currentNode', () => {
      useJobStore.getState().setJob(makeJob({ currentNode: 'investigator' }))
      useJobStore.getState().appendToken('job-1', 'hello')
      useJobStore.getState().appendToken('job-1', ' world')
      expect(useJobStore.getState().agentTokens['job-1:investigator']).toBe('hello world')
    })

    it('falls back to _output when currentNode is unset', () => {
      useJobStore.getState().setJob(makeJob())
      useJobStore.getState().appendToken('job-1', 'tok')
      expect(useJobStore.getState().agentTokens['job-1:_output']).toBe('tok')
    })
  })

  describe('processJobEvent', () => {
    beforeEach(() => {
      useJobStore.getState().setJob(makeJob({ currentNode: 'supervisor' }))
    })

    it.each([
      {
        label: 'AgentSpawnedEvent sets currentNode and status=running',
        event: { __typename: 'AgentSpawnedEvent', agentId: 'a1', agentName: 'investigator', node: 'investigator' } as JobEvent,
        check: () => {
          const job = useJobStore.getState().jobs['job-1']
          expect(job?.currentNode).toBe('investigator')
          expect(job?.status).toBe('running')
        },
      },
      {
        label: 'AgentTokenEvent appends token',
        event: { __typename: 'AgentTokenEvent', agentId: 'a1', token: 'hi' } as JobEvent,
        check: () => {
          expect(useJobStore.getState().agentTokens['job-1:supervisor']).toBe('hi')
        },
      },
      {
        label: 'OutputTokenEvent appends token',
        event: { __typename: 'OutputTokenEvent', token: 'out', section: null } as JobEvent,
        check: () => {
          expect(useJobStore.getState().agentTokens['job-1:supervisor']).toBe('out')
        },
      },
      {
        label: 'GraphNodeCompleteEvent is a no-op',
        event: { __typename: 'GraphNodeCompleteEvent', node: 'supervisor', step: 1 } as JobEvent,
        check: () => {
          const job = useJobStore.getState().jobs['job-1']
          expect(job?.status).toBe('queued')
          expect(job?.currentNode).toBe('supervisor')
        },
      },
      {
        label: 'GraphInterruptEvent sets awaitingHuman and status=waiting',
        event: { __typename: 'GraphInterruptEvent', question: 'Need info?', context: 'ctx' } as JobEvent,
        check: () => {
          const job = useJobStore.getState().jobs['job-1']
          expect(job?.awaitingHuman).toBe(true)
          expect(job?.status).toBe('waiting')
          expect(job?.humanExchanges).toHaveLength(1)
          expect(job?.humanExchanges?.[0]?.question).toBe('Need info?')
        },
      },
      {
        label: 'JobDoneEvent sets status=done',
        event: { __typename: 'JobDoneEvent', Empty: null } as JobEvent,
        check: () => {
          expect(useJobStore.getState().jobs['job-1']?.status).toBe('done')
        },
      },
      {
        label: 'JobFailedEvent sets status=failed',
        event: { __typename: 'JobFailedEvent', error: 'boom' } as JobEvent,
        check: () => {
          expect(useJobStore.getState().jobs['job-1']?.status).toBe('failed')
        },
      },
      {
        label: 'JobTimedOutEvent sets status=failed',
        event: { __typename: 'JobTimedOutEvent', Empty: null } as JobEvent,
        check: () => {
          expect(useJobStore.getState().jobs['job-1']?.status).toBe('failed')
        },
      },
      {
        label: 'JobKilledEvent sets status=killed',
        event: { __typename: 'JobKilledEvent', Empty: null } as JobEvent,
        check: () => {
          expect(useJobStore.getState().jobs['job-1']?.status).toBe('killed')
        },
      },
      {
        label: 'AgentDoneEvent is a no-op',
        event: { __typename: 'AgentDoneEvent', agentId: 'a1', node: 'supervisor' } as JobEvent,
        check: () => {
          expect(useJobStore.getState().jobs['job-1']?.status).toBe('queued')
        },
      },
      {
        label: 'AgentToolCallEvent is a no-op',
        event: { __typename: 'AgentToolCallEvent', agentId: 'a1', toolName: 'search', inputPreview: '{}' } as JobEvent,
        check: () => {
          expect(useJobStore.getState().jobs['job-1']?.status).toBe('queued')
        },
      },
      {
        label: 'AgentToolResultEvent is a no-op',
        event: { __typename: 'AgentToolResultEvent', agentId: 'a1', toolName: 'search', resultSummary: 'ok' } as JobEvent,
        check: () => {
          expect(useJobStore.getState().jobs['job-1']?.status).toBe('queued')
        },
      },
      {
        label: 'OutputSectionDoneEvent is a no-op',
        event: { __typename: 'OutputSectionDoneEvent', section: 'summary' } as JobEvent,
        check: () => {
          expect(useJobStore.getState().jobs['job-1']?.status).toBe('queued')
        },
      },
    ])('$label', ({ event, check }) => {
      useJobStore.getState().processJobEvent('job-1', event)
      check()
    })

    it('is a no-op for unknown jobId', () => {
      const before = useJobStore.getState()
      useJobStore.getState().processJobEvent('unknown', {
        __typename: 'JobDoneEvent',
        Empty: null,
      } as JobEvent)
      expect(useJobStore.getState().jobs).toEqual(before.jobs)
    })

    it('GraphInterruptEvent appends to existing exchanges', () => {
      useJobStore.getState().setJob(
        makeJob({
          humanExchanges: [{ question: 'First?', answer: 'yes' }],
        })
      )
      useJobStore.getState().processJobEvent('job-1', {
        __typename: 'GraphInterruptEvent',
        question: 'Second?',
        context: 'ctx',
      } as JobEvent)
      const exchanges = useJobStore.getState().jobs['job-1']?.humanExchanges
      expect(exchanges).toHaveLength(2)
      expect(exchanges?.[0]?.question).toBe('First?')
      expect(exchanges?.[1]?.question).toBe('Second?')
    })
  })
})

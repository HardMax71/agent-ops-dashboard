import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { ExecutionTimeline } from '../components/ExecutionTimeline'
import type { AgentFinding } from '../store/jobStore'

function makeFinding(agentName: string): AgentFinding {
  return {
    agentName,
    summary: 'test summary',
    confidence: 0.8,
  }
}

const NODE_ORDER = ['supervisor', 'investigator', 'codebase_search', 'web_search', 'critic', 'human_input', 'writer']

describe('ExecutionTimeline', () => {
  afterEach(cleanup)

  it.each([
    {
      label: 'investigator running — supervisor=completed, investigator=active, rest=pending',
      currentNode: 'investigator',
      findings: [] as AgentFinding[],
      status: 'running',
      expected: {
        supervisor: 'completed',
        investigator: 'active',
        codebase_search: 'pending',
        web_search: 'pending',
        critic: 'pending',
        human_input: 'pending',
        writer: 'pending',
      },
    },
    {
      label: 'critic running with investigator finding — supervisor through web_search=completed, critic=active',
      currentNode: 'critic',
      findings: [makeFinding('investigator')],
      status: 'running',
      expected: {
        supervisor: 'completed',
        investigator: 'completed',
        codebase_search: 'completed',
        web_search: 'completed',
        critic: 'active',
        human_input: 'pending',
        writer: 'pending',
      },
    },
    {
      label: 'writer done with investigator finding — all completed (terminal)',
      currentNode: 'writer',
      findings: [makeFinding('investigator')],
      status: 'done',
      expected: {
        supervisor: 'completed',
        investigator: 'completed',
        codebase_search: 'completed',
        web_search: 'completed',
        critic: 'completed',
        human_input: 'completed',
        writer: 'completed',
      },
    },
    {
      label: 'empty currentNode queued — all pending',
      currentNode: '',
      findings: [] as AgentFinding[],
      status: 'queued',
      expected: {
        supervisor: 'pending',
        investigator: 'pending',
        codebase_search: 'pending',
        web_search: 'pending',
        critic: 'pending',
        human_input: 'pending',
        writer: 'pending',
      },
    },
    {
      label: 'supervisor failed with findings — supervisor=completed (terminal)',
      currentNode: 'supervisor',
      findings: [makeFinding('supervisor'), makeFinding('investigator')],
      status: 'failed',
      expected: {
        supervisor: 'completed',
        investigator: 'completed',
        codebase_search: 'pending',
        web_search: 'pending',
        critic: 'pending',
        human_input: 'pending',
        writer: 'pending',
      },
    },
  ])('$label', ({ currentNode, findings, status, expected }) => {
    render(
      <ExecutionTimeline
        currentNode={currentNode}
        findings={findings}
        status={status}
      />
    )
    for (const node of NODE_ORDER) {
      const expectedState = expected[node as keyof typeof expected]
      expect(screen.getByLabelText(`${node}: ${expectedState}`)).toBeInTheDocument()
    }
  })
})

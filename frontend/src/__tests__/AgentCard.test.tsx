import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { AgentCard } from '../components/AgentCard'
import type { AgentFinding } from '../store/jobStore'

function makeFinding(overrides: Partial<AgentFinding> = {}): AgentFinding {
  return {
    agentName: 'investigator',
    summary: 'Found a null pointer issue',
    confidence: 0.85,
    ...overrides,
  }
}

describe('AgentCard', () => {
  afterEach(cleanup)

  it.each([
    { agentName: 'investigator', expectedClass: 'border-blue-600' },
    { agentName: 'codebase_search', expectedClass: 'border-purple-600' },
    { agentName: 'web_search', expectedClass: 'border-cyan-600' },
    { agentName: 'critic', expectedClass: 'border-orange-600' },
    { agentName: 'writer', expectedClass: 'border-green-600' },
    { agentName: 'supervisor', expectedClass: 'border-gray-600' },
  ])('known agent "$agentName" has border class "$expectedClass"', ({ agentName, expectedClass }) => {
    const { container } = render(
      <AgentCard finding={makeFinding({ agentName })} state="done" />
    )
    const card = container.querySelector('[role="article"]')
    expect(card?.className).toContain(expectedClass)
  })

  it('unknown agent name uses fallback gray class', () => {
    const { container } = render(
      <AgentCard finding={makeFinding({ agentName: 'unknown_agent' })} state="done" />
    )
    const card = container.querySelector('[role="article"]')
    expect(card?.className).toContain('border-gray-600')
    expect(card?.className).toContain('bg-gray-800/30')
  })

  it('shows "processing..." when state=running', () => {
    render(<AgentCard finding={makeFinding()} state="running" />)
    expect(screen.getByText('processing...')).toBeInTheDocument()
  })

  it('does not show "processing..." when state=done', () => {
    render(<AgentCard finding={makeFinding()} state="done" />)
    expect(screen.queryByText('processing...')).not.toBeInTheDocument()
  })

  it('renders finding summary', () => {
    render(<AgentCard finding={makeFinding({ summary: 'Memory leak detected' })} state="done" />)
    expect(screen.getByText('Memory leak detected')).toBeInTheDocument()
  })

  it('renders confidence percentage', () => {
    render(<AgentCard finding={makeFinding({ confidence: 0.92 })} state="done" />)
    expect(screen.getByText('92% confidence')).toBeInTheDocument()
  })

  it('renders hypothesis when present', () => {
    render(
      <AgentCard
        finding={makeFinding({ hypothesis: 'Race condition in worker pool' })}
        state="done"
      />
    )
    expect(screen.getByText('Hypothesis')).toBeInTheDocument()
    expect(screen.getByText('Race condition in worker pool')).toBeInTheDocument()
  })

  it('omits hypothesis when absent', () => {
    render(<AgentCard finding={makeFinding({ hypothesis: undefined })} state="done" />)
    expect(screen.queryByText('Hypothesis')).not.toBeInTheDocument()
  })

  it('renders affectedAreas tags', () => {
    render(
      <AgentCard
        finding={makeFinding({ affectedAreas: ['auth', 'database', 'api'] })}
        state="done"
      />
    )
    expect(screen.getByText('auth')).toBeInTheDocument()
    expect(screen.getByText('database')).toBeInTheDocument()
    expect(screen.getByText('api')).toBeInTheDocument()
  })

  it('renders streamedTokens when provided', () => {
    render(
      <AgentCard
        finding={makeFinding()}
        state="running"
        streamedTokens="Analyzing codebase..."
      />
    )
    expect(screen.getByText('Analyzing codebase...')).toBeInTheDocument()
  })
})

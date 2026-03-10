import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { StatusBadge } from '../components/StatusBadge'
import type { JobStatus } from '../store/jobStore'

const statusCases: { status: JobStatus; label: string; pulse: boolean }[] = [
  { status: 'queued', label: 'Queued', pulse: false },
  { status: 'running', label: 'Running', pulse: true },
  { status: 'waiting', label: 'Waiting', pulse: true },
  { status: 'paused', label: 'Paused', pulse: false },
  { status: 'done', label: 'Done', pulse: false },
  { status: 'failed', label: 'Failed', pulse: false },
  { status: 'killed', label: 'Killed', pulse: false },
]

describe('StatusBadge', () => {
  afterEach(cleanup)

  it.each(statusCases)('renders "$label" for status=$status', ({ status, label }) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it.each(statusCases)('has aria-label "Status: $label" for status=$status', ({ status, label }) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByLabelText(`Status: ${label}`)).toBeInTheDocument()
  })

  it.each(statusCases)('shows pulse indicator only when pulse=$pulse for status=$status', ({ status, pulse }) => {
    const { container } = render(<StatusBadge status={status} />)
    const pulseEl = container.querySelector('.animate-pulse-slow')
    if (pulse) {
      expect(pulseEl).toBeInTheDocument()
    } else {
      expect(pulseEl).not.toBeInTheDocument()
    }
  })
})

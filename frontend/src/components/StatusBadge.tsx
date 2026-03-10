import React from 'react'
import clsx from 'clsx'
import type { JobStatus } from '../store/jobStore'

interface StatusBadgeProps {
  status: JobStatus
}

const STATUS_CONFIG: Record<JobStatus, { label: string; className: string; pulse: boolean }> = {
  queued: { label: 'Queued', className: 'bg-gray-700 text-gray-300', pulse: false },
  running: { label: 'Running', className: 'bg-blue-900 text-blue-200', pulse: true },
  waiting: { label: 'Waiting', className: 'bg-amber-900 text-amber-200', pulse: true },
  paused: { label: 'Paused', className: 'bg-yellow-900 text-yellow-200', pulse: false },
  done: { label: 'Done', className: 'bg-green-900 text-green-200', pulse: false },
  failed: { label: 'Failed', className: 'bg-red-900 text-red-200', pulse: false },
  killed: { label: 'Killed', className: 'bg-gray-800 text-gray-400', pulse: false },
}

export function StatusBadge({ status }: StatusBadgeProps): React.ReactElement {
  const config = STATUS_CONFIG[status]
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        config.className
      )}
      aria-label={`Status: ${config.label}`}
    >
      {config.pulse && (
        <span
          className="h-1.5 w-1.5 rounded-full bg-current animate-pulse-slow"
          aria-hidden="true"
        />
      )}
      {config.label}
    </span>
  )
}

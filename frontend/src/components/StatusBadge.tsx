import React from 'react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { JobStatus } from '../store/jobStore'

interface StatusBadgeProps {
  status: JobStatus
}

const STATUS_CONFIG: Record<JobStatus, { label: string; className: string; pulse: boolean }> = {
  queued: { label: 'Queued', className: 'bg-slate-100 text-slate-600 border-slate-200', pulse: false },
  running: { label: 'Running', className: 'bg-blue-50 text-blue-700 border-blue-200', pulse: true },
  waiting: { label: 'Waiting', className: 'bg-amber-50 text-amber-700 border-amber-200', pulse: true },
  pausing: { label: 'Pausing', className: 'bg-yellow-50 text-yellow-700 border-yellow-200', pulse: true },
  paused: { label: 'Paused', className: 'bg-yellow-50 text-yellow-700 border-yellow-200', pulse: false },
  done: { label: 'Done', className: 'bg-emerald-50 text-emerald-700 border-emerald-200', pulse: false },
  failed: { label: 'Failed', className: 'bg-red-50 text-red-700 border-red-200', pulse: false },
  killed: { label: 'Killed', className: 'bg-slate-100 text-slate-500 border-slate-200', pulse: false },
  timed_out: { label: 'Timed Out', className: 'bg-red-50 text-red-700 border-red-200', pulse: false },
}

const FALLBACK_CONFIG = { label: 'Unknown', className: 'bg-slate-100 text-slate-600 border-slate-200', pulse: false }

export function StatusBadge({ status }: StatusBadgeProps): React.ReactElement {
  const config = STATUS_CONFIG[status] || FALLBACK_CONFIG
  return (
    <Badge
      variant="outline"
      className={cn('gap-1 font-medium', config.className)}
      aria-label={`Status: ${config.label}`}
    >
      {config.pulse && (
        <span
          className="h-1.5 w-1.5 rounded-full bg-current animate-pulse-slow"
          aria-hidden="true"
        />
      )}
      {config.label}
    </Badge>
  )
}

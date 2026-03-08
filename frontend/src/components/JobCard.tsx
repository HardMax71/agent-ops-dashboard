import React from 'react'
import clsx from 'clsx'
import type { Job } from '../types'
import { StatusBadge } from './StatusBadge'

interface JobCardProps {
  job: Job
  isSelected: boolean
  onClick: () => void
}

function formatTimeAgo(dateStr: string | undefined): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const diff = Date.now() - date.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function extractRepo(issueUrl: string): string {
  const match = issueUrl.match(/github\.com\/([^/]+\/[^/]+)\/issues/)
  return match ? match[1] : issueUrl
}

export function JobCard({ job, isSelected, onClick }: JobCardProps): React.ReactElement {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left p-4 rounded-lg border transition-colors cursor-pointer',
        isSelected
          ? 'bg-gray-700 border-blue-500'
          : 'bg-gray-800 border-gray-700 hover:bg-gray-750 hover:border-gray-600'
      )}
      aria-pressed={isSelected}
      aria-label={`Job: ${job.issue_title || extractRepo(job.issue_url)}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <StatusBadge status={job.status} />
        <span className="text-xs text-gray-500">{formatTimeAgo(job.created_at)}</span>
      </div>
      <p className="text-sm font-medium text-gray-200 truncate mb-1">
        {job.issue_title || extractRepo(job.issue_url)}
      </p>
      <p className="text-xs text-gray-500 truncate font-mono">
        {extractRepo(job.issue_url)}
      </p>
    </button>
  )
}

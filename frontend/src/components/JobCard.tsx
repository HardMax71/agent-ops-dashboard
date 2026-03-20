import React from 'react'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { JobLocal } from '../store/jobStore'
import { StatusBadge } from './StatusBadge'

interface JobCardProps {
  job: JobLocal
  isSelected: boolean
  onClick: () => void
}

export function formatTimeAgo(dateStr: string | undefined): string {
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

export function extractRepo(issueUrl: string): string {
  const match = issueUrl.match(/github\.com\/([^/]+\/[^/]+)\/issues/)
  return match ? match[1] : issueUrl
}

export function JobCard({ job, isSelected, onClick }: JobCardProps): React.ReactElement {
  return (
    <Card
      className={cn(
        'cursor-pointer transition-all p-3',
        isSelected
          ? 'ring-2 ring-primary shadow-sm'
          : 'hover:shadow-sm hover:border-border/80'
      )}
      onClick={onClick}
      role="button"
      aria-pressed={isSelected}
      aria-label={`Job: ${job.issueTitle || extractRepo(job.issueUrl)}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <StatusBadge status={job.status} />
        <span className="text-xs text-muted-foreground">{formatTimeAgo(job.createdAt)}</span>
      </div>
      <p className="text-sm font-medium truncate mb-1">
        {job.issueTitle || extractRepo(job.issueUrl)}
      </p>
      <p className="text-xs text-muted-foreground truncate font-mono">
        {extractRepo(job.issueUrl)}
      </p>
    </Card>
  )
}

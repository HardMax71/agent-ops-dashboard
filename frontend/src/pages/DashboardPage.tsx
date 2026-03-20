import React, { useState, useEffect, useCallback } from 'react'
import { useJobStore } from '../store/jobStore'
import type { JobLocal } from '../store/jobStore'
import { gql } from '../api/graphqlClient'
import { JobCard } from '../components/JobCard'
import { ActivityLog } from '../components/ActivityLog'
import { ExecutionTimeline } from '../components/ExecutionTimeline'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Plus, Pause, Play, CornerDownRight, X, ExternalLink } from 'lucide-react'

function NewJobModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }): React.ReactElement {
  const [issueUrl, setIssueUrl] = useState('')
  const [supervisorNotes, setSupervisorNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const setJob = useJobStore((s) => s.setJob)
  const selectJob = useJobStore((s) => s.selectJob)

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault()
    if (!issueUrl.trim()) return
    setIsSubmitting(true)
    try {
      const result = await gql.mutation({
        createJob: {
          __args: { input: { issueUrl: issueUrl, supervisorNotes: supervisorNotes } },
          __scalar: true,
        },
      })
      const job: JobLocal = {
        jobId: result.createJob.jobId,
        status: (result.createJob.status || 'queued') as JobLocal['status'],
        issueUrl: issueUrl,
      }
      setJob(job)
      selectJob(result.createJob.jobId)
      setIssueUrl('')
      setSupervisorNotes('')
      onClose()
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="New Triage Job">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="issue-url">GitHub Issue URL</label>
          <Input
            id="issue-url"
            type="url"
            value={issueUrl}
            onChange={(e) => setIssueUrl(e.target.value)}
            placeholder="https://github.com/owner/repo/issues/123"
            required
            aria-label="GitHub issue URL"
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="notes">Supervisor Notes (optional)</label>
          <Textarea
            id="notes"
            value={supervisorNotes}
            onChange={(e) => setSupervisorNotes(e.target.value)}
            placeholder="Focus on authentication module..."
            rows={2}
            aria-label="Supervisor notes"
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={!issueUrl.trim() || isSubmitting}>
            {isSubmitting ? 'Creating...' : 'Create Job'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function JobWorkspace({ job }: { job: JobLocal }): React.ReactElement {
  const [showRedirectModal, setShowRedirectModal] = useState(false)
  const [showKillModal, setShowKillModal] = useState(false)
  const [redirectInstruction, setRedirectInstruction] = useState('')
  const updateJob = useJobStore((s) => s.updateJob)

  const handlePause = async (): Promise<void> => {
    await gql.mutation({ pauseJob: { __args: { jobId: job.jobId }, __scalar: true } })
    updateJob(job.jobId, { status: 'paused' })
  }

  const handleResume = async (): Promise<void> => {
    await gql.mutation({ resumeJob: { __args: { jobId: job.jobId }, __scalar: true } })
    updateJob(job.jobId, { status: 'running' })
  }

  const handleRedirect = async (): Promise<void> => {
    if (!redirectInstruction.trim()) return
    await gql.mutation({ redirectJob: { __args: { jobId: job.jobId, instruction: redirectInstruction }, __scalar: true } })
    setShowRedirectModal(false)
    setRedirectInstruction('')
  }

  const handleKill = async (): Promise<void> => {
    await gql.mutation({ killJob: { __args: { jobId: job.jobId }, __scalar: true } })
    updateJob(job.jobId, { status: 'killed' })
    setShowKillModal(false)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <StatusBadge status={job.status} />
          <span className="text-sm font-medium truncate">
            {job.issueTitle || job.issueUrl}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowRedirectModal(true)}
            aria-label="Redirect job"
            className="gap-1"
          >
            <CornerDownRight className="h-3 w-3" /> Redirect
          </Button>
          {job.status === 'running' ? (
            <Button
              variant="outline"
              size="sm"
              onClick={handlePause}
              aria-label="Pause job"
              className="gap-1 text-amber-600 border-amber-200 hover:bg-amber-50"
            >
              <Pause className="h-3 w-3" /> Pause
            </Button>
          ) : job.status === 'paused' ? (
            <Button
              variant="outline"
              size="sm"
              onClick={handleResume}
              aria-label="Resume job"
              className="gap-1 text-emerald-600 border-emerald-200 hover:bg-emerald-50"
            >
              <Play className="h-3 w-3" /> Resume
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowKillModal(true)}
            aria-label="Kill job"
            className="gap-1 text-red-600 border-red-200 hover:bg-red-50"
          >
            <X className="h-3 w-3" /> Kill
          </Button>
        </div>
      </div>

      {/* Timeline */}
      <div className="p-4 border-b flex-shrink-0">
        <ExecutionTimeline findings={job.findings || []} currentNode={job.currentNode || ''} status={job.status} />
      </div>

      {/* Activity Log */}
      <ScrollArea className="flex-1 p-4">
        <ActivityLog jobId={job.jobId} />
      </ScrollArea>

      {/* Redirect Modal */}
      <Modal isOpen={showRedirectModal} onClose={() => setShowRedirectModal(false)} title="Redirect Job">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">Provide new instructions for the supervisor.</p>
          <Textarea
            value={redirectInstruction}
            onChange={(e) => setRedirectInstruction(e.target.value)}
            placeholder="Focus on the authentication module..."
            rows={3}
            aria-label="Redirect instruction"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowRedirectModal(false)}>Cancel</Button>
            <Button onClick={handleRedirect}>Redirect</Button>
          </div>
        </div>
      </Modal>

      {/* Kill Modal */}
      <Modal isOpen={showKillModal} onClose={() => setShowKillModal(false)} title="Kill Job">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">Are you sure you want to kill this job? This cannot be undone.</p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowKillModal(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleKill}>Kill Job</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function OutputPanel({ job }: { job: JobLocal }): React.ReactElement {
  const [commentText, setCommentText] = useState(job.report?.githubComment || '')
  const [isPostingComment, setIsPostingComment] = useState(false)
  const [commentUrl, setCommentUrl] = useState('')

  const handlePostComment = async (): Promise<void> => {
    setIsPostingComment(true)
    try {
      const result = await gql.mutation({
        postComment: {
          __args: { jobId: job.jobId },
          ok: true,
          commentUrl: true,
        },
      })
      if (result.postComment.commentUrl) {
        setCommentUrl(result.postComment.commentUrl)
      }
    } finally {
      setIsPostingComment(false)
    }
  }

  if (!job.report) {
    return (
      <div className="p-6 text-center text-muted-foreground text-sm">
        Output will appear when the job completes.
      </div>
    )
  }

  const severityVariant: Record<string, string> = {
    critical: 'bg-red-100 text-red-800 border-red-200',
    high: 'bg-orange-100 text-orange-800 border-orange-200',
    medium: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    low: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  }

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-4">
        {/* Triage Report */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Triage Report</CardTitle>
              <Badge variant="outline" className={severityVariant[job.report.severity] || ''}>
                {job.report.severity}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Root Cause</p>
              <p className="text-sm">{job.report.rootCause}</p>
            </div>
            {job.report.relevantFiles.length > 0 && (
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Relevant Files</p>
                {job.report.relevantFiles.map((f) => (
                  <p key={f} className="text-xs text-primary font-mono">{f}</p>
                ))}
              </div>
            )}
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Confidence</p>
              <p className="text-sm">{Math.round(job.report.confidence * 100)}%</p>
            </div>
          </CardContent>
        </Card>

        <Separator />

        {/* GitHub Comment */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">GitHub Comment</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              className="font-mono text-xs"
              rows={4}
              aria-label="GitHub comment editor"
            />
            {commentUrl ? (
              <a
                href={commentUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="View posted comment on GitHub"
              >
                <Button variant="outline" className="w-full gap-2 text-emerald-700 border-emerald-200">
                  <ExternalLink className="h-3 w-3" /> Comment posted — view on GitHub
                </Button>
              </a>
            ) : (
              <Button
                onClick={handlePostComment}
                disabled={isPostingComment || !commentText.trim()}
                className="w-full"
                aria-label="Post comment to GitHub"
              >
                {isPostingComment ? 'Posting...' : 'Post Comment to GitHub'}
              </Button>
            )}
          </CardContent>
        </Card>

        {/* LangSmith Link */}
        {job.langsmithUrl && (
          <a
            href={job.langsmithUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="View trace in LangSmith"
          >
            <Button variant="outline" className="w-full gap-2">
              <ExternalLink className="h-3 w-3" /> View in LangSmith
            </Button>
          </a>
        )}
      </div>
    </ScrollArea>
  )
}

export function DashboardPage(): React.ReactElement {
  const { jobs, selectedJobId, selectJob, setJob } = useJobStore()
  const [showNewJobModal, setShowNewJobModal] = useState(false)
  const [filterStatus, setFilterStatus] = useState<string>('all')

  useEffect(() => {
    gql.query({ jobs: { __scalar: true, relevantFiles: true } }).then((result) => {
      for (const j of result.jobs) {
        const report = j.severity ? {
          severity: j.severity as 'critical' | 'high' | 'medium' | 'low',
          rootCause: j.recommendedFix || '',
          relevantFiles: j.relevantFiles || [],
          recommendedFix: j.recommendedFix || '',
          confidence: 0,
          githubComment: j.githubComment || '',
          ticketDraft: {},
        } : undefined
        setJob({ ...j, status: j.status as JobLocal['status'], report })
      }
    }).catch(() => {})
  }, [setJob])

  const jobList = Object.values(jobs)
  const filteredJobs = filterStatus === 'all' ? jobList : jobList.filter((j) => j.status === filterStatus)
  const selectedJob = selectedJobId ? jobs[selectedJobId] : null

  const handleKeyDown = useCallback((e: KeyboardEvent): void => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
    if (e.ctrlKey || e.altKey || e.metaKey) return
    if (e.key === 'n' || e.key === 'N') setShowNewJobModal(true)
  }, [])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div className="flex h-screen bg-muted/30 overflow-hidden">
      {/* Zone 1: Job Queue Sidebar */}
      <aside
        className="w-80 flex-shrink-0 bg-background border-r flex flex-col"
        aria-label="Job queue"
      >
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold tracking-tight">AgentOps</h1>
              <a
                href="/langflow/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground transition-colors"
                title="Configure flows in LangFlow"
                aria-label="Open LangFlow editor"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
                </svg>
              </a>
            </div>
            <Button
              onClick={() => setShowNewJobModal(true)}
              size="sm"
              className="gap-1"
              aria-label="New job (N)"
              title="New job (N)"
            >
              <Plus className="h-3 w-3" /> New
            </Button>
          </div>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="w-full border rounded-md text-sm px-2 py-1.5 bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Filter by status"
          >
            <option value="all">All statuses</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="waiting">Waiting</option>
            <option value="paused">Paused</option>
            <option value="done">Done</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-2" role="list" aria-label="Jobs list">
            {filteredJobs.length === 0 ? (
              <p className="text-center text-muted-foreground text-xs py-8">No jobs. Press N to create one.</p>
            ) : (
              filteredJobs.map((job) => (
                <div key={job.jobId} role="listitem">
                  <JobCard
                    job={job}
                    isSelected={selectedJobId === job.jobId}
                    onClick={() => selectJob(job.jobId)}
                  />
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </aside>

      {/* Zone 2: Live Workspace */}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden bg-background" aria-label="Job workspace">
        {selectedJob ? (
          <JobWorkspace job={selectedJob} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <p className="text-lg mb-2">No job selected</p>
              <p className="text-sm">Select a job from the sidebar or create a new one</p>
            </div>
          </div>
        )}
      </main>

      {/* Zone 3: Output Panel */}
      <aside
        className="w-96 flex-shrink-0 bg-background border-l overflow-hidden"
        aria-label="Output panel"
      >
        <div className="p-4 border-b">
          <h2 className="text-sm font-semibold">Output</h2>
        </div>
        {selectedJob ? (
          <OutputPanel key={selectedJob.jobId} job={selectedJob} />
        ) : (
          <div className="p-4 text-center text-muted-foreground text-sm">
            Select a job to see output
          </div>
        )}
      </aside>

      <NewJobModal isOpen={showNewJobModal} onClose={() => setShowNewJobModal(false)} />
    </div>
  )
}

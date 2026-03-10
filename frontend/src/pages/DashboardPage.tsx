import React, { useState, useEffect, useCallback } from 'react'
import { useJobStore } from '../store/jobStore'
import type { JobLocal } from '../store/jobStore'
import { gql } from '../api/graphqlClient'
import { JobCard } from '../components/JobCard'
import { AgentCard } from '../components/AgentCard'
import { QuestionCard } from '../components/QuestionCard'
import { ExecutionTimeline } from '../components/ExecutionTimeline'
import { StatusBadge } from '../components/StatusBadge'
import { Modal } from '../components/Modal'
import { useJobStream } from '../hooks/useJobStream'

function NewJobModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }): React.ReactElement {
  const [issueUrl, setIssueUrl] = useState('')
  const [supervisorNotes, setSupervisorNotes] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const setJob = useJobStore((s) => s.setJob)

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault()
    if (!issueUrl.trim()) return
    setIsSubmitting(true)
    const result = await gql.mutation({
      createJob: {
        __args: { input: { issueUrl: issueUrl, supervisorNotes: supervisorNotes } },
        __scalar: true,
      },
    })
    const job: JobLocal = {
      jobId: result.createJob.jobId,
      status: 'queued',
      issueUrl: issueUrl,
    }
    setJob(job)
    setIsSubmitting(false)
    setIssueUrl('')
    setSupervisorNotes('')
    onClose()
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="New Triage Job">
      <form onSubmit={handleSubmit}>
        <label className="block mb-4">
          <span className="text-sm text-gray-300 mb-1 block">GitHub Issue URL</span>
          <input
            type="url"
            value={issueUrl}
            onChange={(e) => setIssueUrl(e.target.value)}
            placeholder="https://github.com/owner/repo/issues/123"
            className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            required
            aria-label="GitHub issue URL"
          />
        </label>
        <label className="block mb-4">
          <span className="text-sm text-gray-300 mb-1 block">Supervisor Notes (optional)</span>
          <textarea
            value={supervisorNotes}
            onChange={(e) => setSupervisorNotes(e.target.value)}
            placeholder="Focus on authentication module..."
            className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500"
            rows={2}
            aria-label="Supervisor notes"
          />
        </label>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-300 hover:text-gray-100 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!issueUrl.trim() || isSubmitting}
            className="bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium px-4 py-2 rounded transition-colors"
          >
            {isSubmitting ? 'Creating...' : 'Create Job'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function JobWorkspace({ job }: { job: JobLocal }): React.ReactElement {
  const [showRedirectModal, setShowRedirectModal] = useState(false)
  const [showKillModal, setShowKillModal] = useState(false)
  const [redirectInstruction, setRedirectInstruction] = useState('')
  const agentTokens = useJobStore((s) => s.agentTokens[job.jobId] || '')
  const updateJob = useJobStore((s) => s.updateJob)

  useJobStream(job.jobId)

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
      <div className="flex items-center justify-between p-4 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <StatusBadge status={job.status} />
          <span className="text-sm font-medium text-gray-200 truncate">
            {job.issueTitle || job.issueUrl}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => setShowRedirectModal(true)}
            className="text-xs text-gray-300 hover:text-gray-100 border border-gray-600 hover:border-gray-500 px-3 py-1 rounded transition-colors"
            aria-label="Redirect job"
          >
            ↪ Redirect
          </button>
          {job.status === 'running' ? (
            <button
              onClick={handlePause}
              className="text-xs text-yellow-300 hover:text-yellow-100 border border-yellow-700 hover:border-yellow-600 px-3 py-1 rounded transition-colors"
              aria-label="Pause job"
            >
              ⏸ Pause
            </button>
          ) : job.status === 'paused' ? (
            <button
              onClick={handleResume}
              className="text-xs text-green-300 hover:text-green-100 border border-green-700 hover:border-green-600 px-3 py-1 rounded transition-colors"
              aria-label="Resume job"
            >
              ▶ Resume
            </button>
          ) : null}
          <button
            onClick={() => setShowKillModal(true)}
            className="text-xs text-red-300 hover:text-red-100 border border-red-800 hover:border-red-700 px-3 py-1 rounded transition-colors"
            aria-label="Kill job"
          >
            ✕ Kill
          </button>
        </div>
      </div>

      {/* Timeline */}
      <div className="p-4 border-b border-gray-700 flex-shrink-0">
        <ExecutionTimeline findings={job.findings || []} currentNode={job.currentNode || ''} />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Question card */}
        {job.awaitingHuman && job.humanExchanges && job.humanExchanges.length > 0 && (
          <QuestionCard
            jobId={job.jobId}
            question={job.humanExchanges[job.humanExchanges.length - 1]?.question || 'Additional context needed'}
            onAnswered={() => updateJob(job.jobId, { awaitingHuman: false })}
          />
        )}

        {/* Agent cards */}
        {(job.findings || []).map((finding, idx) => (
          <AgentCard
            key={`${finding.agentName}-${idx}`}
            finding={finding}
            state={job.currentNode === finding.agentName ? 'running' : 'done'}
            streamedTokens={job.currentNode === finding.agentName ? agentTokens : undefined}
          />
        ))}

        {job.status === 'queued' && (
          <div className="text-center text-gray-500 text-sm py-8">
            Job queued. Waiting for worker...
          </div>
        )}
      </div>

      {/* Redirect Modal */}
      <Modal isOpen={showRedirectModal} onClose={() => setShowRedirectModal(false)} title="Redirect Job">
        <div className="space-y-4">
          <p className="text-sm text-gray-400">Provide new instructions for the supervisor.</p>
          <textarea
            value={redirectInstruction}
            onChange={(e) => setRedirectInstruction(e.target.value)}
            placeholder="Focus on the authentication module..."
            className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500"
            rows={3}
            aria-label="Redirect instruction"
          />
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowRedirectModal(false)} className="px-4 py-2 text-sm text-gray-300">Cancel</button>
            <button
              onClick={handleRedirect}
              className="bg-blue-600 hover:bg-blue-500 text-white text-sm px-4 py-2 rounded transition-colors"
            >
              Redirect
            </button>
          </div>
        </div>
      </Modal>

      {/* Kill Modal */}
      <Modal isOpen={showKillModal} onClose={() => setShowKillModal(false)} title="Kill Job">
        <div className="space-y-4">
          <p className="text-sm text-gray-300">Are you sure you want to kill this job? This cannot be undone.</p>
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowKillModal(false)} className="px-4 py-2 text-sm text-gray-300">Cancel</button>
            <button
              onClick={handleKill}
              className="bg-red-600 hover:bg-red-500 text-white text-sm px-4 py-2 rounded transition-colors"
            >
              Kill Job
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function OutputPanel({ job }: { job: JobLocal }): React.ReactElement {
  const [commentText, setCommentText] = useState(job.report?.githubComment || '')

  if (!job.report) {
    return (
      <div className="p-4 text-center text-gray-500 text-sm">
        Output will appear when the job completes.
      </div>
    )
  }

  const severityColors: Record<string, string> = {
    critical: 'bg-red-900 text-red-200',
    high: 'bg-orange-900 text-orange-200',
    medium: 'bg-yellow-900 text-yellow-200',
    low: 'bg-green-900 text-green-200',
  }

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      {/* Triage Report */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-200">Triage Report</h3>
          <span className={`text-xs rounded-full px-2 py-0.5 font-medium ${severityColors[job.report.severity] || ''}`}>
            {job.report.severity}
          </span>
        </div>
        <div className="space-y-2">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Root Cause</p>
            <p className="text-sm text-gray-300">{job.report.rootCause}</p>
          </div>
          {job.report.relevantFiles.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Relevant Files</p>
              {job.report.relevantFiles.map((f) => (
                <p key={f} className="text-xs text-blue-300 font-mono">{f}</p>
              ))}
            </div>
          )}
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Confidence</p>
            <p className="text-sm text-gray-300">{Math.round(job.report.confidence * 100)}%</p>
          </div>
        </div>
      </div>

      {/* GitHub Comment */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
        <h3 className="text-sm font-semibold text-gray-200 mb-2">GitHub Comment</h3>
        <textarea
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          className="w-full bg-gray-900 border border-gray-600 rounded p-2 text-xs text-gray-300 font-mono resize-none focus:outline-none focus:border-blue-500"
          rows={4}
          aria-label="GitHub comment editor"
        />
        <button
          disabled
          title="Not yet implemented"
          className="mt-2 w-full bg-gray-700 text-gray-500 text-xs font-medium py-2 rounded cursor-not-allowed"
          aria-label="Post comment to GitHub (not yet implemented)"
        >
          Post Comment to GitHub
        </button>
      </div>

      {/* LangSmith Link */}
      {job.langsmithUrl && (
        <a
          href={job.langsmithUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="block w-full text-center text-xs text-blue-400 hover:text-blue-300 border border-blue-800 hover:border-blue-700 rounded p-2 transition-colors"
          aria-label="View trace in LangSmith"
        >
          View in LangSmith →
        </a>
      )}
    </div>
  )
}

export function DashboardPage(): React.ReactElement {
  const { jobs, selectedJobId, selectJob } = useJobStore()
  const [showNewJobModal, setShowNewJobModal] = useState(false)
  const [filterStatus, setFilterStatus] = useState<string>('all')

  const jobList = Object.values(jobs)
  const filteredJobs = filterStatus === 'all' ? jobList : jobList.filter((j) => j.status === filterStatus)
  const selectedJob = selectedJobId ? jobs[selectedJobId] : null

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent): void => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
    if (e.key === 'n' || e.key === 'N') setShowNewJobModal(true)
  }, [])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Zone 1: Job Queue Sidebar */}
      <aside
        className="w-72 flex-shrink-0 bg-gray-900 border-r border-gray-700 flex flex-col"
        aria-label="Job queue"
      >
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-sm font-semibold text-gray-200">AgentOps</h1>
            <button
              onClick={() => setShowNewJobModal(true)}
              className="bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium px-3 py-1.5 rounded transition-colors"
              aria-label="New job (N)"
              title="New job (N)"
            >
              + New
            </button>
          </div>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="w-full bg-gray-800 border border-gray-600 text-gray-300 text-xs rounded p-1.5 focus:outline-none"
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
        <div className="flex-1 overflow-y-auto p-2 space-y-2" role="list" aria-label="Jobs list">
          {filteredJobs.length === 0 ? (
            <p className="text-center text-gray-600 text-xs py-8">No jobs. Press N to create one.</p>
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
      </aside>

      {/* Zone 2: Live Workspace */}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden" aria-label="Job workspace">
        {selectedJob ? (
          <JobWorkspace job={selectedJob} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-600">
            <div className="text-center">
              <p className="text-lg mb-2">No job selected</p>
              <p className="text-sm">Select a job from the sidebar or create a new one</p>
            </div>
          </div>
        )}
      </main>

      {/* Zone 3: Output Panel */}
      <aside
        className="w-80 flex-shrink-0 bg-gray-900 border-l border-gray-700 overflow-hidden"
        aria-label="Output panel"
      >
        <div className="p-4 border-b border-gray-700">
          <h2 className="text-sm font-semibold text-gray-200">Output</h2>
        </div>
        {selectedJob ? (
          <OutputPanel job={selectedJob} />
        ) : (
          <div className="p-4 text-center text-gray-600 text-sm">
            Select a job to see output
          </div>
        )}
      </aside>

      <NewJobModal isOpen={showNewJobModal} onClose={() => setShowNewJobModal(false)} />
    </div>
  )
}

export type JobStatus =
  | 'queued'
  | 'running'
  | 'waiting'
  | 'paused'
  | 'done'
  | 'failed'
  | 'killed'

export interface AgentFinding {
  agent_name: string
  summary: string
  confidence: number
  hypothesis?: string
  affected_areas?: string[]
  keywords_for_search?: string[]
  error_messages?: string[]
  relevant_files?: string[]
  root_cause_location?: string
  verdict?: string
  gaps?: string[]
}

export interface HumanExchange {
  question: string
  answer: string
  asked_at?: string
  answered_at?: string
}

export interface TriageReport {
  severity: 'critical' | 'high' | 'medium' | 'low'
  root_cause: string
  relevant_files: string[]
  recommended_fix: string
  confidence: number
  github_comment: string
  ticket_draft: Record<string, string>
}

export interface Job {
  job_id: string
  status: JobStatus
  issue_url: string
  issue_title?: string
  repository?: string
  current_node?: string
  awaiting_human?: boolean
  langsmith_url?: string
  findings?: AgentFinding[]
  report?: TriageReport
  human_exchanges?: HumanExchange[]
  created_at?: string
}

export interface SSEEvent {
  type: string
  job_id?: string
  data?: Record<string, unknown>
  node?: string
  token?: string
  question?: string
}

export interface UserInfo {
  github_id: string
  github_login: string
  avatar_url?: string
}

export type AgentCardState = 'idle' | 'running' | 'done' | 'error'

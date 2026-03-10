import apiClient from './client'
import type { Job, UserInfo } from '../types'

export interface CreateJobRequest {
  issue_url: string
  supervisor_notes?: string
}

export interface CreateJobResponse {
  job_id: string
  status: string
}

export const jobsApi = {
  create: (data: CreateJobRequest) =>
    apiClient.post<CreateJobResponse>('/jobs', data),

  get: (jobId: string) =>
    apiClient.get<Job>(`/jobs/${jobId}`),

  answer: (jobId: string, answer: string) =>
    apiClient.post<{ status: string }>(`/jobs/${jobId}/answer`, { answer }),

  pause: (jobId: string) =>
    apiClient.post<{ status: string }>(`/jobs/${jobId}/pause`),

  resume: (jobId: string) =>
    apiClient.post<{ status: string }>(`/jobs/${jobId}/resume`),

  redirect: (jobId: string, instruction: string) =>
    apiClient.post<{ status: string }>(`/jobs/${jobId}/redirect`, { instruction }),

  kill: (jobId: string) =>
    apiClient.delete<{ status: string }>(`/jobs/${jobId}`),

  postComment: (jobId: string) =>
    apiClient.post<{ status: string }>(`/jobs/${jobId}/post-comment`),
}

export const authApi = {
  refresh: () =>
    apiClient.post<{ access_token: string; expires_in: number }>('/auth/refresh'),

  me: () =>
    apiClient.get<UserInfo>('/auth/me'),

  logout: () =>
    apiClient.delete('/auth/logout'),

  deleteGithubToken: () =>
    apiClient.delete('/auth/github-token'),
}

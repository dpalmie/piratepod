const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type JobStage = 'queued' | 'ingest' | 'script' | 'audio' | 'publish' | 'done'

export interface Source {
  title: string
  url: string
  markdown: string
}

export interface GenerateResult {
  urls: string[]
  sources: Source[]
  title: string
  script: string
  audio_path: string
  audio_format: string
  feed_url: string
  episode_id: string
  episode_audio_url: string
}

export interface JobEvent {
  id: number
  stage: JobStage
  status: JobStatus
  message?: string
  created_at: string
}

export interface Job {
  id: string
  status: JobStatus
  stage: JobStage
  title?: string
  urls: string[]
  result?: GenerateResult
  error?: string
  events?: JobEvent[]
  created_at: string
  updated_at: string
  started_at?: string
  finished_at?: string
}

export interface Podcast {
  id: string
  slug: string
  title: string
  description: string
  author: string
  cover_url: string
  language: string
  feed_url: string
  created_at: string
}

export interface Episode {
  id: string
  podcast_id: string
  title: string
  description: string
  audio_url: string
  audio_type: string
  audio_bytes: number
  duration_sec: number
  guid: string
  published_at: string
}

export interface Feed {
  podcast: Podcast
  episodes: Episode[]
}

export async function createJob(input: { urls: string[]; title?: string }) {
  return request<Job>('/jobs', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function listJobs() {
  return request<Job[]>('/jobs')
}

export async function getJob(id: string) {
  return request<Job>(`/jobs/${id}`)
}

export async function retryJob(id: string) {
  return request<Job>(`/jobs/${id}/retry`, { method: 'POST' })
}

export async function getFeed() {
  return request<Feed>('/feed')
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

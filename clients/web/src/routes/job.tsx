import { useParams } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useStore } from '@tanstack/react-store'
import { toast } from 'sonner'
import { Hash, Loader2, RefreshCcw, Rss } from 'lucide-react'
import { StageProgress } from '@/components/stage-progress'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getJob, retryJob } from '@/lib/api'
import { uiActions, uiStore } from '@/lib/ui-store'

export function JobPage() {
  const { jobId } = useParams({ from: '/jobs/$jobId' })
  const queryClient = useQueryClient()
  const expanded = useStore(uiStore, (state) => state.expandedJobSections)
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'queued' || status === 'running' ? 2000 : false
    },
  })
  const retry = useMutation({
    mutationFn: () => retryJob(jobId),
    onSuccess: async () => {
      toast.success('Job queued again')
      await queryClient.invalidateQueries({ queryKey: ['job', jobId] })
      await queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
    onError: (error) => toast.error(error.message),
  })

  if (job.isLoading) return <p className="text-sm text-muted-foreground">Loading job…</p>
  if (job.error) return <Alert><AlertTitle>Could not load job</AlertTitle><AlertDescription>{job.error.message}</AlertDescription></Alert>
  if (!job.data) return null

  const data = job.data
  const result = data.result

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="border-b">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <CardTitle className="text-2xl">{result?.title || data.title || 'Podcast job'}</CardTitle>
              <CardDescription className="mt-1 flex items-center gap-1">
                <Button
                  aria-label="Click to copy job ID"
                  title="Click to copy job ID"
                  variant="ghost"
                  size="icon"
                  className="-ml-1 h-7 w-7 text-muted-foreground"
                  onClick={() => copy(data.id, 'Copied job ID')}
                >
                  <Hash className="h-4 w-4" />
                </Button>
                {result ? (
                  <Button
                    aria-label="Click to copy RSS URL"
                    title="Click to copy RSS URL"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground"
                    onClick={() => copy(result.feed_url, 'Copied RSS URL')}
                  >
                    <Rss className="h-4 w-4" />
                  </Button>
                ) : null}
              </CardDescription>
            </div>
            {data.status === 'failed' ? (
              <Button variant="secondary" onClick={() => retry.mutate()} disabled={retry.isPending}>
                {retry.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
                Retry
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-5 pt-6">
          <StageProgress job={data} />
          {data.error ? <Alert className="border-destructive text-destructive"><AlertTitle>Generation failed</AlertTitle><AlertDescription>{data.error}</AlertDescription></Alert> : null}
          {result ? (
            <div>
              <audio className="w-full" controls src={result.episode_audio_url} />
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sources</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {(result?.sources ?? data.urls.map((url) => ({ title: url, url, markdown: '', image_url: null }))).map((source) => (
            <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="flex items-center gap-3 rounded-lg border p-3 hover:bg-accent">
              {source.image_url ? (
                <img
                  src={source.image_url}
                  alt=""
                  className="h-16 w-24 shrink-0 rounded-md border object-cover"
                  loading="lazy"
                  onError={(event) => {
                    event.currentTarget.style.display = 'none'
                  }}
                />
              ) : null}
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium" title={source.title}>{source.title}</p>
                <p className="truncate text-sm text-muted-foreground" title={source.url}>{source.url}</p>
              </div>
            </a>
          ))}
        </CardContent>
      </Card>

      {result ? (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Script</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => uiActions.toggleJobSection('script')}>{expanded.script ? 'Hide' : 'Show'}</Button>
            </div>
          </CardHeader>
          {expanded.script ? <CardContent><pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm">{result.script}</pre></CardContent> : null}
        </Card>
      ) : null}

    </div>
  )
}

async function copy(value: string, message = 'Copied') {
  await navigator.clipboard.writeText(value)
  toast.success(message)
}

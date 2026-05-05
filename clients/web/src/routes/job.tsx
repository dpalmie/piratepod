import { useParams } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useStore } from '@tanstack/react-store'
import { toast } from 'sonner'
import { Loader2, RefreshCcw } from 'lucide-react'
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
        <CardHeader>
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <CardTitle className="text-2xl">{result?.title || data.title || 'Podcast job'}</CardTitle>
              <CardDescription>{data.id}</CardDescription>
            </div>
            {data.status === 'failed' ? (
              <Button variant="secondary" onClick={() => retry.mutate()} disabled={retry.isPending}>
                {retry.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
                Retry
              </Button>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <StageProgress job={data} />
          {data.error ? <Alert className="border-destructive text-destructive"><AlertTitle>Generation failed</AlertTitle><AlertDescription>{data.error}</AlertDescription></Alert> : null}
          {result ? (
            <div className="grid gap-3 md:grid-cols-2">
              <Button variant="secondary" onClick={() => copy(result.feed_url)}>Copy RSS URL</Button>
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
          {(result?.sources ?? data.urls.map((url) => ({ title: url, url, markdown: '' }))).map((source) => (
            <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="block rounded-lg border p-3 hover:bg-accent">
              <p className="font-medium">{source.title}</p>
              <p className="break-all text-sm text-muted-foreground">{source.url}</p>
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

async function copy(value: string) {
  await navigator.clipboard.writeText(value)
  toast.success('Copied')
}

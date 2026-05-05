import { CheckCircle2, Circle, CircleDot, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import type { Job, JobEvent, JobStage } from '@/lib/api'

const stages: Array<{ key: JobStage; label: string }> = [
  { key: 'queued', label: 'Queued' },
  { key: 'ingest', label: 'Ingest' },
  { key: 'script', label: 'Script' },
  { key: 'audio', label: 'Audio' },
  { key: 'publish', label: 'Publish' },
  { key: 'done', label: 'Done' },
]

export function StageProgress({ job }: { job: Job }) {
  const currentIndex = stages.findIndex((stage) => stage.key === job.stage)
  const value = job.status === 'succeeded' ? 100 : Math.max(currentIndex, 0) * 20
  const currentEvent = latestEvent(job.events)

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <Badge variant={job.status === 'failed' ? 'destructive' : job.status === 'succeeded' ? 'default' : 'secondary'}>{job.status}</Badge>
        <div className="text-sm text-muted-foreground md:text-right">
          <p>Current stage: {job.stage}</p>
          {currentEvent?.message ? <p className="text-xs">{currentEvent.message}</p> : null}
        </div>
      </div>
      <Progress value={value} />
      <div className="grid gap-3 md:grid-cols-6">
        {stages.map((stage, index) => {
          const isDone = job.status === 'succeeded' || index < currentIndex
          const isCurrent = stage.key === job.stage && job.status !== 'succeeded'
          const isFailed = isCurrent && job.status === 'failed'
          const event = stageEvent(job.events, stage.key)
          const Icon = isFailed ? XCircle : isDone ? CheckCircle2 : isCurrent ? CircleDot : Circle
          return (
            <div key={stage.key} className="flex items-start gap-2 text-sm">
              <Icon className={isFailed ? 'h-4 w-4 text-destructive' : isDone || isCurrent ? 'h-4 w-4 text-primary' : 'h-4 w-4 text-muted-foreground'} />
              <div className="min-w-0">
                <p className={isDone || isCurrent ? 'text-foreground' : 'text-muted-foreground'}>{stage.label}</p>
                {event ? <time className="text-xs text-muted-foreground">{formatEventTime(event.created_at)}</time> : null}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function stageEvent(events: JobEvent[] | undefined, stage: JobStage) {
  if (!events?.length) return undefined
  const matches = events.filter((event) => event.stage === stage)
  if (stage === 'queued') {
    return matches.find((event) => event.status === 'queued') ?? matches[0]
  }
  if (stage === 'done') {
    return matches.find((event) => event.status === 'succeeded') ?? matches.at(-1)
  }
  return matches.find((event) => event.status === 'running') ?? matches.at(-1)
}

function latestEvent(events: JobEvent[] | undefined) {
  return events?.at(-1)
}

function formatEventTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  })
}

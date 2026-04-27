import { CheckCircle2, Circle, CircleDot, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import type { Job, JobStage } from '@/lib/api'

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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <Badge variant={job.status === 'failed' ? 'destructive' : job.status === 'succeeded' ? 'default' : 'secondary'}>{job.status}</Badge>
        <span className="text-sm text-muted-foreground">Current stage: {job.stage}</span>
      </div>
      <Progress value={value} />
      <div className="grid gap-3 md:grid-cols-6">
        {stages.map((stage, index) => {
          const isDone = job.status === 'succeeded' || index < currentIndex
          const isCurrent = stage.key === job.stage && job.status !== 'succeeded'
          const isFailed = isCurrent && job.status === 'failed'
          const Icon = isFailed ? XCircle : isDone ? CheckCircle2 : isCurrent ? CircleDot : Circle
          return (
            <div key={stage.key} className="flex items-center gap-2 text-sm">
              <Icon className={isFailed ? 'h-4 w-4 text-destructive' : isDone || isCurrent ? 'h-4 w-4 text-primary' : 'h-4 w-4 text-muted-foreground'} />
              <span className={isDone || isCurrent ? 'text-foreground' : 'text-muted-foreground'}>{stage.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

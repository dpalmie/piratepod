import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useStore } from "@tanstack/react-store";
import { toast } from "sonner";
import { ArrowRight, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { createJob, listJobs, type Job } from "@/lib/api";
import { uiActions, uiStore } from "@/lib/ui-store";

export function HomePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const urlDraft = useStore(uiStore, (state) => state.urlDraft);
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: 5000,
  });
  const mutation = useMutation({
    mutationFn: createJob,
    onSuccess: async (job) => {
      uiActions.clearCreateForm();
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Podcast generation queued");
      await navigate({ to: "/jobs/$jobId", params: { jobId: job.id } });
    },
    onError: (error) => toast.error(error.message),
  });

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const urls = parseURLs(urlDraft);
    if (urls.length === 0) {
      toast.error("Add at least one URL");
      return;
    }
    mutation.mutate({ urls });
  }

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Create a Podcast</CardTitle>
          <CardDescription>
            Paste one or many URLs. PiratePod will handle the rest.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="urls">
                URLs
              </label>
              <Textarea
                id="urls"
                placeholder="https://example.com/article\nhttps://another.example/post"
                value={urlDraft}
                onChange={(event) => uiActions.setUrlDraft(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                One per line, comma separated, or whitespace separated.
              </p>
            </div>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Generate Podcast
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Jobs</CardTitle>
          <CardDescription>
            Run history. Go to Feed to view all episodes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {jobs.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading jobs…</p>
          ) : null}
          {jobs.error ? (
            <p className="text-sm text-destructive">{jobs.error.message}</p>
          ) : null}
          {jobs.data?.length === 0 ? (
            <p className="text-sm text-muted-foreground">No jobs yet.</p>
          ) : null}
          {jobs.data?.map((job) => (
            <JobRow key={job.id} job={job} />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function JobRow({ job }: { job: Job }) {
  return (
    <Link
      to="/jobs/$jobId"
      params={{ jobId: job.id }}
      className="flex items-center justify-between gap-3 rounded-lg border p-3 hover:bg-accent"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">
          {job.result?.title || job.title || job.urls[0] || job.id}
        </p>
        <p className="text-xs text-muted-foreground">
          {formatDateTime(job.created_at)}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Badge
          className="capitalize"
          variant={
            job.status === "failed"
              ? "destructive"
              : job.status === "succeeded"
                ? "default"
                : "secondary"
          }
        >
          {job.status}
        </Badge>
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
      </div>
    </Link>
  );
}

function parseURLs(raw: string) {
  return raw
    .split(/[\s,]+/)
    .map((url) => url.trim())
    .filter(Boolean);
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

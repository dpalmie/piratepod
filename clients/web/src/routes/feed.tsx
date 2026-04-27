import { useQuery } from "@tanstack/react-query";
import { useStore } from "@tanstack/react-store";
import { toast } from "sonner";
import { Copy, ExternalLink, Play, Rss } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getFeed, type Episode } from "@/lib/api";
import { uiActions, uiStore } from "@/lib/ui-store";

export function FeedPage() {
  const selectedEpisodeId = useStore(
    uiStore,
    (state) => state.selectedEpisodeId,
  );
  const autoplayEpisodeId = useStore(
    uiStore,
    (state) => state.autoplayEpisodeId,
  );
  const feed = useQuery({
    queryKey: ["feed"],
    queryFn: getFeed,
    refetchInterval: 10000,
  });

  if (feed.isLoading)
    return <p className="text-sm text-muted-foreground">Loading feed…</p>;
  if (feed.error)
    return (
      <Alert>
        <AlertTitle>Could not load feed</AlertTitle>
        <AlertDescription>{feed.error.message}</AlertDescription>
      </Alert>
    );
  if (!feed.data) return null;

  const episodes = feed.data.episodes;
  const expandedId =
    selectedEpisodeId && episodes.some((e) => e.id === selectedEpisodeId)
      ? selectedEpisodeId
      : undefined;

  return (
    <div className="grid gap-6">
      <Card className="h-fit">
        <CardHeader>
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-primary/10 p-3 text-primary">
              <Rss className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-2xl">
                {feed.data.podcast.title}
              </CardTitle>
              <CardDescription>
                {feed.data.podcast.description ||
                  "Your generated PiratePod feed"}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border p-3">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              RSS URL
            </p>
            <p className="break-all text-sm">{feed.data.podcast.feed_url}</p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => copy(feed.data.podcast.feed_url)}
            >
              <Copy className="h-4 w-4" />
              Copy
            </Button>
            <Button variant="ghost" asChild>
              <a
                href={feed.data.podcast.feed_url}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink className="h-4 w-4" />
                Open XML
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Episodes</CardTitle>
          <CardDescription>
            Newest episodes from your PiratePod.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {episodes.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No episodes yet. Create one from the dashboard.
            </p>
          ) : (
            episodes.map((episode) => (
              <EpisodeRow
                key={episode.id}
                episode={episode}
                expanded={episode.id === expandedId}
                autoplay={episode.id === autoplayEpisodeId}
                onToggle={() =>
                  episode.id === expandedId
                    ? uiActions.collapseEpisode()
                    : uiActions.selectEpisode(episode.id)
                }
                onPlay={() => uiActions.playEpisode(episode.id)}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function EpisodeRow({
  episode,
  expanded,
  autoplay,
  onToggle,
  onPlay,
}: {
  episode: Episode;
  expanded: boolean;
  autoplay: boolean;
  onToggle: () => void;
  onPlay: () => void;
}) {
  return (
    <div
      onClick={onToggle}
      data-selected={expanded}
      className="cursor-pointer rounded-lg border p-4 transition hover:bg-accent data-[selected=true]:border-primary data-[selected=true]:bg-accent/40"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{episode.title}</p>
          <p className="text-sm text-muted-foreground">
            {formatDateTime(episode.published_at)}
          </p>
          {episode.duration_sec > 0 ? (
            <p className="text-xs text-muted-foreground">
              {formatDuration(episode.duration_sec)}
            </p>
          ) : null}
        </div>
        {!expanded ? (
          <Button
            size="icon"
            variant="secondary"
            aria-label="Play episode"
            onClick={(event) => {
              event.stopPropagation();
              onPlay();
            }}
          >
            <Play className="h-4 w-4" />
          </Button>
        ) : null}
      </div>
      {expanded ? (
        <div
          className="mt-4 space-y-3"
          onClick={(event) => event.stopPropagation()}
        >
          <audio
            className="w-full"
            controls
            autoPlay={autoplay}
            src={episode.audio_url}
          />
          {episode.description ? (
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm">
              {episode.description}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

async function copy(value: string) {
  await navigator.clipboard.writeText(value);
  toast.success("Copied");
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

function formatDuration(seconds: number) {
  if (!seconds || seconds <= 0) return "unknown duration";
  const total = Math.round(seconds);
  if (total < 60) return `${total}s`;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

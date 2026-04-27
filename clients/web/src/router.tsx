import { Link, Outlet, createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import { Headphones, Radio } from 'lucide-react'
import { Toaster } from 'sonner'
import { HomePage } from '@/routes/home'
import { FeedPage } from '@/routes/feed'
import { JobPage } from '@/routes/job'

function RootLayout() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link to="/" className="flex items-center gap-2">
            <img src="/logo.png" alt="PiratePod" className="h-8 w-8 object-contain" />
            <span className="brand-wordmark text-2xl">PiratePod</span>
          </Link>
          <nav className="flex items-center gap-2 text-sm">
            <Link to="/" className="rounded-md px-3 py-2 text-muted-foreground hover:bg-accent hover:text-foreground" activeProps={{ className: 'rounded-md bg-accent px-3 py-2 text-foreground' }}>
              <Radio className="mr-2 inline h-4 w-4" />
              Create
            </Link>
            <Link to="/feed" className="rounded-md px-3 py-2 text-muted-foreground hover:bg-accent hover:text-foreground" activeProps={{ className: 'rounded-md bg-accent px-3 py-2 text-foreground' }}>
              <Headphones className="mr-2 inline h-4 w-4" />
              Feed
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
      <Toaster richColors />
    </div>
  )
}

const rootRoute = createRootRoute({ component: RootLayout })
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: HomePage })
const feedRoute = createRoute({ getParentRoute: () => rootRoute, path: '/feed', component: FeedPage })
const jobRoute = createRoute({ getParentRoute: () => rootRoute, path: '/jobs/$jobId', component: JobPage })

const routeTree = rootRoute.addChildren([indexRoute, feedRoute, jobRoute])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/react'
import './index.css'
import App from './App.tsx'

// Sentry is disabled in local development and in the Vitest jsdom test
// environment. Both guards are required:
// - import.meta.env.DEV covers the Vite dev server.
// - import.meta.env.MODE !== 'test' covers Vitest, which sets MODE="test".
// Without the test guard, Sentry would intercept console errors and attempt
// outbound network requests during CI, breaking test isolation.
if (!import.meta.env.DEV && import.meta.env.MODE !== 'test') {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN as string | undefined,

    // Disable performance tracing. SPA routing would otherwise leak sensitive
    // URL parameters into transaction names.
    tracesSampleRate: 0,

    // Disable the default integrations that track DOM interactions and
    // navigation. These can capture patient input events and URL changes.
    integrations: (defaults) =>
      defaults.filter(
        (i) =>
          i.name !== 'BrowserTracing' &&
          i.name !== 'Breadcrumbs' &&
          i.name !== 'GlobalHandlers' &&
          i.name !== 'LinkedErrors' &&
          i.name !== 'HttpContext' &&
          i.name !== 'Dedupe'
      ),

    // Sanitise fetch breadcrumbs. Drop the request body size for any POST to
    // the form endpoints — these carry raw clinical JSON and FormData payloads.
    beforeBreadcrumb(breadcrumb) {
      if (
        breadcrumb.type === 'http' &&
        breadcrumb.data?.method === 'POST' &&
        typeof breadcrumb.data?.url === 'string' &&
        (breadcrumb.data.url.includes('/form/update') ||
          breadcrumb.data.url.includes('/form/finish'))
      ) {
        if (breadcrumb.data) {
          delete breadcrumb.data.requestBodySize;
        }
      }
      return breadcrumb;
    },
  })
}

// The ErrorBoundary catches synchronous render-phase crashes that the
// fatalError state in App.tsx cannot catch (those only fire from event
// handlers and effects, not from the render path itself).
//
// Prop and state serialisation is explicitly disabled via beforeCapture to
// prevent patient answers held in transient UI state from being transmitted
// to Sentry.
//
// The fallback renders the same "Unable to load the form" UI as App.tsx's
// fatalError branch. The reset button performs a hard reload rather than
// attempting React tree recovery — this guarantees object URL cleanup and
// a clean memory slate.
function FatalFallback() {
  return (
    <div style={{ padding: '2rem', maxWidth: '600px', margin: '0 auto' }}>
      <h1>Unable to load the form</h1>
      <div className="alert alert-danger">
        <p>An unexpected error occurred.</p>
      </div>
      <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '12px' }}>
        If this problem persists, please contact the practice directly.
      </p>
      <div className="btn-row" style={{ marginTop: '1rem' }}>
        <button
          className="btn btn-primary"
          onClick={() => window.location.reload()}
        >
          Try again
        </button>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Sentry.ErrorBoundary
      fallback={<FatalFallback />}
      beforeCapture={(scope) => {
        // Drop React component props and state from the event payload.
        // This deterministically prevents patient answers held in UI state
        // from being serialised and sent to Sentry.
        scope.setExtra('componentProps', undefined)
        scope.setExtra('componentState', undefined)
      }}
    >
      <App />
    </Sentry.ErrorBoundary>
  </StrictMode>,
)
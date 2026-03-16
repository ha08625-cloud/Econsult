# Admin Portal — Vite Migration Plan (completed)

## What this plan does and does not do

This plan migrates `backend/admin/index.html` from a standalone CDN page into a proper TypeScript React application built by Vite. At the end of this plan, the admin portal has TypeScript, npm packages, proper imports, linting, and hot-reload in local development. The clinical form frontend is not touched. No new admin features are added — this is purely a build and tooling change.

---

## The core problem: Vite multi-page apps

Vite supports multiple HTML entry points via Rollup's `input` option. The current config has one entry point (`index.html`). We need two: the patient-facing form and the admin portal. Vite will build both and output them into `frontend/dist/`. The patient form lands at `frontend/dist/index.html` (unchanged). The admin portal lands at `frontend/dist/admin/index.html`.

FastAPI currently serves the entire `frontend/dist/` directory at `/`. It will continue to do this. Visiting `/admin/` will serve `frontend/dist/admin/index.html` automatically because `StaticFiles(html=True)` serves `index.html` for directory paths. The separate `StaticFiles` mount at `/admin-portal` pointing to `backend/admin/` becomes redundant and is removed from `main.py`.

---

## New directory layout

```
frontend/
├── src/                        # patient app source (unchanged)
│   ├── App.tsx
│   ├── main.tsx
│   └── ...
├── admin/
│   └── src/                    # new admin app source
│       ├── main.tsx            # admin entry point
│       ├── App.tsx             # admin root component
│       ├── SignpostingEditor.tsx
│       ├── TokenView.tsx
│       ├── api.ts              # admin API helpers
│       └── types.ts            # admin-specific types
├── index.html                  # patient app HTML entry (unchanged)
├── admin/
│   └── index.html              # admin app HTML entry (new, replaces backend/admin/index.html)
├── vite.config.ts              # updated with two entry points
└── package.json                # quill and dompurify added as npm deps
```

Note the `admin/src/` nesting under `frontend/admin/`. This keeps source for both apps inside `frontend/` without mixing their files. The HTML entry for the admin app lives at `frontend/admin/index.html` (the Vite entry point HTML, not a content file). `backend/admin/` is deleted.

---

## Step-by-step

### Step 1 — Add npm dependencies

```
npm install quill @types/quill
```

DOMPurify is already installed for `App.tsx`. No additional install needed.

### Step 2 — Update vite.config.ts

Change `input` from a single string to an object with named entry points:

```typescript
build: {
  rollupOptions: {
    input: {
      main: 'index.html',
      admin: 'admin/index.html',
    }
  }
}
```

Add `/admin` to the dev server proxy list so the admin portal can reach the backend during local development:

```typescript
server: {
  proxy: {
    '/conditions': 'http://localhost:8000',
    '/form': 'http://localhost:8000',
    '/admin': 'http://localhost:8000',
  }
}
```

### Step 3 — Create frontend/admin/index.html

A minimal Vite HTML entry point, mirroring the patient form's `index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Practice Admin</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="./src/main.tsx"></script>
  </body>
</html>
```

No CDN links. No inline styles. No Babel. Vite injects the built bundle.

### Step 4 — Create admin/src/ TypeScript components

Translate the existing `backend/admin/index.html` JSX and logic into proper TypeScript files. This is a direct translation — no new behaviour.

Files to create:
- `admin/src/main.tsx` — entry point, renders `<App />`
- `admin/src/App.tsx` — token gate, condition list; renders `TokenView` or `EditorView`
- `admin/src/TokenView.tsx` — token input component (currently inline in the CDN file)
- `admin/src/EditorView.tsx` — condition selector, `key={selectedId}` logic
- `admin/src/SignpostingEditor.tsx` — Quill instantiation, save/load, unsaved-change detection. Quill imported from npm, not CDN.
- `admin/src/api.ts` — `fetchConditions`, `fetchSignposting`, `putSignposting`
- `admin/src/types.ts` — admin-facing types (condition list shape, signposting response shape)

The `SIGNPOSTING_PURIFY_CONFIG` constant moves from an inline script variable to a named export in a shared constants file, importable by `SignpostingEditor.tsx`.

### Step 5 — Update main.py

Remove the `/admin-portal` StaticFiles mount and the `_ADMIN_PORTAL_DIR` block entirely. The admin portal is now served by the existing `/` mount from `frontend/dist/`. No new route needed.

Add `/admin` to the dev-server proxy list in `vite.config.ts` (already covered in Step 2).

### Step 6 — Delete backend/admin/

`backend/admin/index.html` is now replaced by the built output. Delete the directory.

### Step 7 — Update build.sh if needed

The build command (`npm run build`) does not change. Vite reads `vite.config.ts` and builds both entry points automatically. Verify the Railway build still works end to end.

---

## What gets simpler

- No more Babel in-browser transpilation (slow, no error checking)
- No more CDN dependencies (version drift risk, network dependency at runtime)
- TypeScript catches type errors in the admin portal the same way it does in the patient form
- Quill imported as a typed npm package — `@types/quill` provides type definitions
- `SIGNPOSTING_PURIFY_CONFIG` can be imported as a shared constant rather than duplicated. This eliminates one of the three locations that must be kept in sync — bringing it down to two (the TypeScript constant and the Python `nh3` call)
- Hot-reload in local development works for the admin portal

## What gets more complex

- The Vite config becomes slightly more involved with two entry points
- The admin portal now has a build step, so a compile error in admin source blocks the Railway deployment for the patient-facing form too. They share a build pipeline. If this becomes a problem, the correct fix is separate Vite builds, but that is premature for now.
- Local development: you need to remember that `http://localhost:5173/admin/` serves the admin portal from Vite dev server, and the proxy config must cover all `/admin` routes

## An open question to resolve before coding

The `SIGNPOSTING_PURIFY_CONFIG` currently has to be kept identical in three places: `practice_repository.py`, `admin.html`, and `App.tsx`. After this migration, the admin portal is a TypeScript module and could share the constant with `App.tsx` via a shared file (e.g. `frontend/src/signpostingConfig.ts`). This would reduce it to two locations. Should the constant live in `frontend/src/` (shared between both apps) or should each app define its own copy? The shared approach is cleaner but introduces a cross-app import dependency. The duplicated approach is explicit and matches the current three-location model but now at two locations. This is worth deciding before starting Step 4 because it affects the file structure.

---

## Questions for you before we start a new chat

1. Does the file structure above look right to you, specifically the `frontend/admin/src/` nesting? The alternative is `frontend/admin-src/` at the top level, which some people find cleaner.

2. On the shared constant question: prefer sharing it in a common file, or keep it duplicated in both apps with a comment?

3. Before we start: `file_structure.md` currently shows `frontend/admin/index.html` which is wrong — the admin portal moved to `backend/admin/index.html` in the last sprint. That should be corrected now, before it misleads the next chat. Do you want to update it yourself or should I produce a corrected version?

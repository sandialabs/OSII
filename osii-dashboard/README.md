# OSII Dashboard

**Browse, search, view, and chat with your documents through OSII.**

OSII Dashboard is a local browser-based workbench for exploring personal or project document collections backed by the OSII API. It is designed to make document-centric workflows feel natural: you can browse documents, search across extracted text, inspect source files like PDFs, organize documents into collections, and prepare for future chat workflows grounded in your own data.

The dashboard is intentionally modular. It is a standalone frontend that talks to an existing OSII backend API, so it can be used when you want a rich browser experience without forcing every OSII workflow to go through a UI.

---

## What you can do

- Browse documents across your indexed corpus
- Search using semantic, lexical, or hybrid retrieval
- Reuse or delete up to 20 recent browser-local searches and chat prompts; answers and results are never stored
- Explore root or collection scopes through saved noun/adjective phrase suggestions
- Open and inspect documents including source PDFs
- Navigate by folder using a lazy-loaded tree
- Organize documents into collections
- Add or remove collection members without touching their originals, and export/import manifest-validated collection OSII packages
- Apply structured sensitivity-awareness labels, handling notes, and reusable plain-text tags
- Preview and surgically remove one file's OSII data, with a separate option to delete the writable original too
- Expand Library Insights on Home to view root-level standard enrichments without loading them into the normal file grid
- Prepare for future document chat workflows

---

## How it works

OSII Dashboard is a standalone frontend application. It does not ingest or index files by itself. Instead, it connects to an existing OSII-compatible backend API that provides:

- document metadata
- folder and tree traversal
- search endpoints
- source document access
- collection APIs

In development, the dashboard typically runs on:

```text
http://localhost:5173
```

and talks to an OSII backend running on:

```text
http://localhost:8511
```

---

## Stack

This repo currently uses:

- React for the UI
- TypeScript for type safety
- Vite for local development and bundling
- Refine for app structure, routing, and resource-oriented workflows
- Material UI (MUI) for layout and components
- TanStack Query for API data fetching and caching

The app is organized as a document workbench:

- a left-hand navigation pane for app navigation and folder scope
- a main pane for browsing, searching, and viewing documents
- a right-hand contextual pane for scope, metadata, and future chat functionality

---

## Repository layout

```text
.
├─ src/
│  ├─ app/          # app shell, layout, providers, theme
│  ├─ api/          # API client, types, adapters
│  ├─ pages/        # custom pages like Home and Search
│  ├─ resources/    # Refine resource pages such as documents, collections, folders
│  ├─ hooks/        # data hooks
│  └─ utils/        # small helpers
├─ index.html
├─ package.json
├─ vite.config.ts
├─ tsconfig.json
└─ tsconfig.app.json
```

---

## Prerequisites

Before starting the dashboard, make sure you have:

- Node.js 18 or newer recommended
- npm available in your shell
- an OSII backend API running locally

The backend should already expose the dashboard-facing endpoints used by this UI.

---

## Quick start

### 1. Start the OSII backend

Make sure your backend API is running, typically at:

```text
http://localhost:8511
```

You can test that quickly in a browser or with PowerShell:

```powershell
Invoke-WebRequest http://localhost:8511/api/dashboard/root
```

### 2. Install dependencies

From the dashboard repo root:

```powershell
npm install
```

### 3. Start the dashboard

```powershell
npm run dev
```

Vite should print a local development URL, usually:

```text
http://localhost:5173
```

Open that URL in your browser.

---

## Development notes

### API proxy

In local development, Vite is configured to proxy API requests to the backend at `http://localhost:8511`.

That means the frontend can call paths like:

```text
/api/dashboard/root
```

without hard-coding the backend URL into most requests.

### Data volume

This frontend does not read directly from the local filesystem. Document and source access should always go through the backend API.

If this repo includes a `data_volume` symlink or mount point, that is for local environment consistency and future container deployment, not for direct browser access.

### Type checking

To run a TypeScript check:

```powershell
npx tsc -p tsconfig.app.json --noEmit
```

---

## Common commands

Install dependencies:

```powershell
npm install
```

Start the dev server:

```powershell
npm run dev
```

Build for production:

```powershell
npm run build
```

Preview the production build locally:

```powershell
npm run preview
```

---

## Current status

This dashboard currently provides a working MVP-style structure with:

- a Refine-based app shell
- document browsing
- search
- document detail views
- collection management
- folder navigation through a lazy tree

The UX is still evolving. Near-term improvements may include denser document browsing, richer contextual side panels, client-side PDF thumbnails, and future chat workflows.

---

## Troubleshooting

### The page is blank

Open browser developer tools and check the Console for runtime errors.

Also verify that the backend is running and that the expected dashboard endpoints respond.

### API requests fail

Confirm the OSII backend is available at:

```text
http://localhost:8511
```

and that Vite proxy settings in `vite.config.ts` are correct.

### PDF thumbnails do not appear

Thumbnails are rendered in the browser from the original PDF; they are not
created by Intake, Tesseract, or another backend processor. First hard-refresh
the page (<kbd>Command</kbd>+<kbd>Shift</kbd>+<kbd>R</kbd> on macOS or
<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>R</kbd> on Windows). If one PDF still has
no preview, open `/api/objects/<file-id>/source` through the dashboard address.
A missing response means the original file is no longer available at the
source path recorded by OSII; put the original back at that path or intake it
from its new location.

### Dependency issues

If installs seem broken, from the repo root you can remove local install artifacts and reinstall:

```powershell
Remove-Item -Recurse -Force node_modules
Remove-Item -Force package-lock.json
npm install
```

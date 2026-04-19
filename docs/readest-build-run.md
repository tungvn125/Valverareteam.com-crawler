# Building and Running the Readest Fork

This guide covers how to build, run, test, and debug this Readest fork after the VVR Social Reader integration changes.

The project is a pnpm monorepo. The main application lives at `apps/readest-app/`. It uses Next.js for the frontend and optionally Tauri v2 for native desktop/mobile builds.

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Node.js | v22+ (v24 recommended) | Next.js frontend |
| pnpm | 10.x (locked in `package.json`) | Package manager |
| Rust | latest stable | Tauri native backend (only needed for desktop/mobile builds) |

Install them:

```bash
nvm install v24
nvm use v24
npm install -g pnpm
rustup update
```

For Tauri platform prerequisites (system libraries, SDKs), see the [Tauri v2 prerequisites page](https://v2.tauri.app/start/prerequisites/).

---

## Initial Setup

### 1. Clone and install

```bash
cd /path/to/parent/directory
git clone <your-fork-url> readest
cd readest
git submodule update --init --recursive
pnpm install
```

### 2. Copy vendor libraries

The app bundles PDF.js and SimpleCC (Chinese text conversion) as static assets:

```bash
pnpm --filter @readest/readest-app setup-vendors
```

This only needs to run once, or again when `packages/foliate-js/` dependencies change.

### 3. Verify the environment

```bash
pnpm tauri info
```

This prints platform details and Tauri toolchain status. Review the output for any missing dependencies on your OS.

---

## Running in Development

### Web-only (fastest iteration loop)

The web build runs entirely in Node.js without Tauri. This is the fastest way to iterate on social reader UI changes:

```bash
pnpm dev-web
```

Opens `http://localhost:3000` by default.

The web build uses `apps/readest-app/.env.web`:

```dotenv
NEXT_PUBLIC_APP_PLATFORM=web
AI_GATEWAY_API_KEY=your_key_here
NEXT_PUBLIC_AI_GATEWAY_API_KEY=your_key_here
```

### Tauri desktop (native window)

```bash
pnpm tauri dev
```

This starts both the Next.js dev server and the Rust/Tauri backend. A native desktop window opens automatically.

The Tauri build uses `apps/readest-app/.env.tauri`:

```dotenv
NEXT_PUBLIC_APP_PLATFORM=tauri
AI_GATEWAY_API_KEY=your_key_here
```

### Android

```bash
# first time only
rm apps/readest-app/src-tauri/gen/android
pnpm tauri android init
pnpm tauri icon ../../data/icons/readest-book.png
git checkout apps/readest-app/src-tauri/gen/android

# then run
pnpm tauri android dev
# or on a physical device
pnpm tauri android dev --host
```

### iOS

```bash
# first time only
pnpm tauri ios init
pnpm tauri icon ../../data/icons/readest-book.png

# then run
pnpm tauri ios dev
# or on a physical device
pnpm tauri ios dev --host
```

---

## Testing

### Unit tests (Vitest)

All tests run through Vitest with jsdom environment. The test command loads env vars from `apps/readest-app/.env` and `.env.test.local`:

```bash
# run all unit tests
pnpm --filter @readest/readest-app test

# run in watch mode
pnpm --filter @readest/readest-app test -- --watch

# run a specific test file
pnpm --filter @readest/readest-app test -- --run src/__tests__/store/social-store.test.ts

# run only social-related tests
pnpm --filter @readest/readest-app test -- --run src/__tests__/utils/social.test.ts src/__tests__/store/social-store.test.ts src/__tests__/hooks/use-social.test.tsx src/__tests__/components/social-panel.test.tsx
```

### Browser-specific tests

Some tests require a real browser environment:

```bash
pnpm --filter @readest/readest-app test:browser
```

### Tauri-specific tests

Tests that require the Tauri runtime:

```bash
pnpm --filter @readest/readest-app test:tauri
```

### Full PR check

```bash
# web PR
pnpm --filter @readest/readest-app test:pr:web

# tauri PR
pnpm --filter @readest/readest-app test:pr:tauri

# everything
pnpm --filter @readest/readest-app test:all
```

### Coverage

```bash
pnpm --filter @readest/readest-app test:coverage
```

---

## Linting and Type Checking

The project uses two linters plus TypeScript checking:

```bash
# type check + biome lint (the primary check)
pnpm --filter @readest/readest-app lint

# Rust format check (Tauri code)
pnpm --filter @readest/readest-app fmt:check

# Rust clippy (Tauri code)
pnpm --filter @readest/readest-app clippy:check

# Prettier formatting check (monorepo-wide)
pnpm format:check

# Auto-fix formatting
pnpm format
```

The `lint` script runs `tsgo --noEmit` (TypeScript type check) then `biome check .`. Fix biome issues with:

```bash
cd apps/readest-app
npx biome check --write .
```

---

## Production Builds

### Web build

```bash
pnpm build-web
```

Output goes to `apps/readest-app/.next/`. Start the production server:

```bash
pnpm --filter @readest/readest-app start-web
```

### Tauri desktop build

```bash
pnpm tauri build
```

Platform-specific builds:

```bash
# Linux x64 (AppImage)
pnpm --filter @readest/readest-app build-linux-x64

# Windows x64 (NSIS installer)
pnpm --filter @readest/readest-app build-win-x64

# Windows ARM64
pnpm --filter @readest/readest-app build-win-arm64

# macOS universal (DMG)
pnpm --filter @readest/readest-app build-macos-universial
```

These require the corresponding `.env.tauri.local` and platform-specific `.env.*.local` files.

### Mobile builds

```bash
# Android
pnpm tauri android build

# iOS
pnpm --filter @readest/readest-app build-ios
```

### Cloudflare preview

```bash
pnpm preview
```

Builds with OpenNext for Cloudflare and starts a local preview server at `http://0.0.0.0:3001`.

---

## Environment Files

The app uses different env files depending on the build target:

| File | Used By | Purpose |
|---|---|---|
| `.env` | all builds + tests | Base config, shared secrets |
| `.env.web` | web builds | Sets `NEXT_PUBLIC_APP_PLATFORM=web` |
| `.env.tauri` | Tauri builds | Sets `NEXT_PUBLIC_APP_PLATFORM=tauri` |
| `.env.local` | overrides | Supabase, S3/R2, DeepL keys |
| `.env.test.local` | tests | Test-specific overrides |

All env files are in `apps/readest-app/`. Start from the examples:

```bash
cd apps/readest-app
cp .env.web.example .env.web
cp .env.tauri.example .env.tauri
cp .env.local.example .env.local
```

Key variables for social reader development:

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_APP_PLATFORM` | yes | `web` or `tauri` |
| `AI_GATEWAY_API_KEY` | no | AI assistant features (not needed for social reader) |

The social reader settings (VVR server URL, enable/disable) are configured at runtime through the Settings dialog in the app, not via env vars.

---

## Project Structure

```
readest/
├── apps/
│   └── readest-app/           # main Next.js + Tauri application
│       ├── src/
│       │   ├── app/            # Next.js app router pages
│       │   │   ├── reader/     # reader page + components
│       │   │   │   ├── components/
│       │   │   │   │   ├── annotator/   # annotation popup, highlight tools
│       │   │   │   │   └── notebook/    # notes, AI, social tabs
│       │   │   │   └── hooks/           # useFoliateEvents, useTextSelector, useSocial
│       │   │   └── library/    # library page
│       │   ├── components/     # shared components
│       │   │   ├── settings/   # settings dialog panels (Font, Layout, Color, Social, etc.)
│       │   │   └── social/     # AuthModal, SocialPanel, ReactionBar, CommentThread, etc.
│       │   ├── store/          # zustand stores
│       │   │   ├── socialStore.ts
│       │   │   ├── notebookStore.ts
│       │   │   ├── settingsStore.ts
│       │   │   └── readerStore.ts
│       │   ├── types/          # TypeScript type definitions
│       │   │   ├── social.ts
│       │   │   ├── settings.ts
│       │   │   └── book.ts
│       │   ├── hooks/          # shared React hooks
│       │   │   └── useSocial.ts
│       │   ├── utils/          # utility functions
│       │   │   └── social.ts
│       │   ├── __tests__/      # test files mirror src/ structure
│       │   │   ├── store/
│       │   │   ├── utils/
│       │   │   ├── hooks/
│       │   │   └── components/
│       │   └── services/       # service layer (AI, sync, cloud)
│       ├── src-tauri/          # Rust/Tauri backend
│       ├── public/             # static assets, vendor libs
│       └── vitest.config.mts   # test configuration
├── packages/
│   └── foliate-js/             # foliate-js submodule (EPUB/PDF rendering)
└── package.json                # monorepo root scripts
```

---

## Social Reader Files Added

These are the files added for the VVR Social Reader integration:

| File | Purpose |
|---|---|
| `src/types/social.ts` | TypeScript types: SocialUser, SocialReaction, SocialComment, SocialSettings |
| `src/store/socialStore.ts` | Zustand store for auth state, chapter data, reactions, comments |
| `src/utils/social.ts` | URL normalization, VVR slug extraction from OPDS download URLs |
| `src/hooks/useSocial.ts` | REST client + WebSocket lifecycle for social features |
| `src/components/social/AuthModal.tsx` | Login/register modal |
| `src/components/social/SocialPanel.tsx` | Notebook tab: comments + reactions for current chapter |
| `src/components/social/ReactionBar.tsx` | Emoji reaction picker (8 types) |
| `src/components/social/ReactionBadges.tsx` | Inline reaction count badges |
| `src/components/social/CommentThread.tsx` | Threaded comment list with edit/delete |
| `src/components/social/CommentInput.tsx` | Comment composer textarea |
| `src/components/settings/SocialPanel.tsx` | Settings panel: enable toggle + server URL |
| `src/__tests__/store/social-store.test.ts` | Store tests |
| `src/__tests__/utils/social.test.ts` | Utility tests |
| `src/__tests__/hooks/use-social.test.tsx` | Hook tests |
| `src/__tests__/components/social-panel.test.tsx` | Component tests |

Modified files:

| File | Change |
|---|---|
| `src/types/settings.ts` | Added `social: SocialSettings` to SystemSettings |
| `src/store/notebookStore.ts` | Added `'social'` to NotebookTab union |
| `src/services/constants.ts` | Added DEFAULT_SOCIAL_SETTINGS |
| `src/components/settings/SettingsDialog.tsx` | Added Social tab |
| `src/app/reader/components/notebook/NotebookTabNavigation.tsx` | Social tab icon + label |
| `src/app/reader/components/notebook/Notebook.tsx` | Renders SocialPanel |
| `src/app/reader/components/annotator/Annotator.tsx` | React button + ReactionBar + ReactionBadges |

---

## Connecting to the VVR Backend

The social reader connects to a running VVR Scraper backend. You need:

1. **VVR backend running** with social endpoints enabled (see `docs/running-the-server.md` in the VVR repo).
2. **A user account** on the VVR backend (register via the AuthModal or the `vvrt social create-admin` CLI command).
3. **Books imported via OPDS** from the VVR backend — the social reader resolves the `book_slug` from the OPDS download URL stored in the book's metadata.

### Setup flow

1. Start the VVR backend: `vvrt web --host 0.0.0.0 --port 8000`
2. Open Readest (web or desktop)
3. Go to **Settings > Social**
4. Enable "Social Reader" and enter the VVR server URL (e.g., `http://localhost:8000`)
5. Import a book via the VVR OPDS catalog (Settings > OPDS, add catalog at `http://localhost:8000/opds/v1/root`)
6. Open the imported book in the reader
7. Select text to see the React button, or open the Social tab in the notebook panel

---

## Troubleshooting

### `pnpm install` fails with submodule errors

```bash
git submodule update --init --recursive
pnpm install
```

### Vendor libraries missing (PDF.js errors)

```bash
pnpm --filter @readest/readest-app setup-vendors
```

### TypeScript errors about `foliate-js` or `tauri-plugin-turso`

These are pre-existing type resolution issues from optional native modules. They do not affect the web build or social reader functionality. Ignore them unless they reference files you changed.

### Test failures in unrelated files

The test suite has ~25 pre-existing failures in `foliate-js/*`, `tauri-plugin-turso`, and `@simplecc/simplecc_wasm` module resolution. These are infrastructure issues unrelated to social reader changes. Focus on the social-specific test files listed above.

### `tsgo --noEmit` fails

Make sure you have the TypeScript nightly toolchain. The project uses `tsgo` (Go-based TypeScript checker) instead of `tsc`. If it's not installed:

```bash
pnpm install
```

### Social tab doesn't appear in notebook

Check that:
1. Settings > Social > "Enable Social Reader" is toggled on
2. A valid server URL is configured
3. The book was imported via VVR OPDS (not sideloaded from a local file)

### WebSocket connection fails

The social WebSocket at `/ws/social/{book_slug}/{chapter_id}` uses plain `ws://` in development. If the VVR backend uses HTTPS, the client auto-upgrades to `wss://`. Check the browser console for connection errors.

### `downloadUrl` property not found on Book type

This is a pre-existing TypeScript issue. The `Book` type in `types/book.ts` does not formally declare `downloadUrl` but it exists at runtime on OPDS-imported books. The code uses optional chaining (`book?.downloadUrl`) to handle this safely.

---

## Useful Scripts Quick Reference

All commands run from the readest repo root unless noted:

| Command | Description |
|---|---|
| `pnpm install` | Install all dependencies |
| `pnpm --filter @readest/readest-app setup-vendors` | Copy PDF.js and SimpleCC to public/ |
| `pnpm dev-web` | Start web dev server (port 3000) |
| `pnpm tauri dev` | Start Tauri desktop dev |
| `pnpm --filter @readest/readest-app test` | Run unit tests |
| `pnpm --filter @readest/readest-app lint` | TypeScript + biome check |
| `pnpm build-web` | Production web build |
| `pnpm tauri build` | Production desktop build |
| `pnpm format` | Auto-fix formatting |
| `pnpm tauri info` | Verify toolchain setup |

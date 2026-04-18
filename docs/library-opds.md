# Library And OPDS Guide

## Library Storage Model

The Web UI and background jobs use a SQLite database managed by `DatabaseManager`.

By default, the web app initializes the database at the config-path location for `vvr_library.db`, not in the repository root.

The `novels` table stores the main library records, including fields such as:

- `title`
- `slug`
- `author`
- `description`
- `cover_url`
- `status`
- `last_chapter_count`
- `last_downloaded_at`
- `output_folder`
- `formats`
- `genres`
- `last_synced_count`
- `server_chapter_count`
- `has_updates`
- `last_checked_at`

The database also stores job history and audio-drama-related character data.

## Library API Routes

The current library routes live under `/api`:

- `GET /api/library`: return all library entries
- `POST /api/library/sync-all`: queue incremental downloads for all novels marked with updates
- `POST /api/library/check`: trigger a background library update check
- `POST /api/library/scan`: scan the configured output tree for existing `.vvr_checkpoint.json` files and import them into the library database
- `POST /api/batch-import`: queue multiple slugs or URLs for download

## How Library Update Checks Work

Library update checks compare current site metadata with the stored library state.

The current implementation:

1. loads all novels from the database
2. fetches story metadata from the source site
3. parses the remote chapter count
4. compares it with `last_synced_count`
5. updates `server_chapter_count`, `has_updates`, and `last_checked_at`

If a title returns `404`, the record is marked as `archived`.

When a connection manager is available, progress events are broadcast over the WebSocket layer during the check.

## Auto-Sync Behavior

The web app always schedules the `auto_sync_background_task()` at startup, but the task only performs actual sync work when:

```bash
VVR_AUTO_SYNC=1
```

When enabled, the current loop:

- checks the library for updates
- finds novels with `has_updates == 1`
- creates crawl jobs for those novels
- submits them to the worker queue
- sleeps for one hour before the next cycle

If `VVR_AUTO_SYNC` is not set to `1`, the loop stays idle except for debug logging.

## Scanning Existing Downloads

`POST /api/library/scan` scans the configured output folder for directories that contain `.vvr_checkpoint.json`.

For each checkpoint it finds, the current implementation imports:

- `title`
- `slug`
- derived chapter count from `scraped`
- `output_folder`
- `cover_url`

This is useful when you already have downloaded novels on disk and want to rebuild the library index without re-downloading everything.

## OPDS Overview

The app exposes an OPDS 1.1 catalog intended for reader apps such as Moon+ Reader or KyBook.

Current navigation routes under `/opds/v1`:

- `/root`
- `/newest`
- `/all`
- `/search`
- `/genres`
- `/authors`

There is also a logical download route outside the `/opds/v1` prefix:

- `/api/opds/download/{slug:path}?fmt=epub`

## OPDS Authentication

All OPDS routes depend on HTTP Basic authentication through `get_current_user()`.

Required environment variables:

- `VVR_OPDS_USER`
- `VVR_OPDS_PASS`

Important behavior:

- if either variable is missing, OPDS does not fall back to anonymous access
- instead, the dependency returns `401` with the message that OPDS authentication is not configured
- if credentials are wrong, the server also returns `401`

That means OPDS should be treated as unavailable until both variables are configured.

## OPDS Download Formats

The current allowed OPDS acquisition formats are:

- `epub`
- `pdf`
- `mobi`
- `azw3`

The download route looks up the novel by slug in the database, resolves the output folder on disk, and then serves a file named from the sanitized novel title plus the requested extension.

If the database record is missing, the output folder does not exist, or the requested file is not present, the route returns `404`.

## Operational Notes

- The web app logs a startup warning telling operators not to move novel folders manually, because that can break library links.
- The OPDS catalog depends on the library database being populated and the referenced files still existing on disk.
- Genre and author feeds are derived from the database, not fetched live from the source site.

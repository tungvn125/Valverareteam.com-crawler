# Job Runner Guide

## Purpose

The job runner executes structured JSON manifests that describe one or more jobs. The current implementation supports:

- `crawl`
- `render`
- `server`

You can trigger it from the CLI with:

```bash
vvrt run manifest.json
```

## How Manifest Execution Works

When you run `vvrt run <file>`, the CLI:

1. loads the JSON manifest from disk
2. validates it against `JobManifest`
3. applies an optional CLI Playwright override to `crawl` jobs
4. validates dependencies with `parse_manifest()`
5. tries to submit the manifest to a local Web UI server at `http://127.0.0.1:8000/api/jobs`
6. falls back to local execution if no local server accepts the submission

That means a running Web UI can act as the execution surface for manifest jobs, while standalone CLI runs still work without the server.

## Supported Job Types

### `crawl`

`crawl` jobs use `ScrapePayload`.

Current payload fields:

- `slug`: required story slug or full supported URL
- `chapters`: explicit chapter indexes
- `from_chapter`, `to_chapter`: chapter range controls
- `grouping`: optional grouping mode
- `skip_illustrations`: skip illustration content
- `output_folder`: explicit output folder override
- `formats`: list of output formats
- `playwright_mode`: `head` or `headless`

Current default formats for `crawl` payloads are:

```json
["epub", "pdf", "cinema"]
```

### `render`

`render` jobs use `RenderPayload`.

Current payload fields:

- `manifest_path`
- `output_path`
- `fps` with default `30`
- `render_format` with default `landscape`
- `vfx_scale` with default `100`

The render path also attempts to mux audio into the generated video when the referenced manifest includes an `audio_path` or `audio` field.

### `server`

`server` jobs use `ServerPayload`.

Current payload fields:

- `host`, default `0.0.0.0`
- `port`, default `8000`
- `opds_password`, optional

If `opds_password` is provided, the runner sets `VVR_OPDS_PASS` before starting the FastAPI web server.

## Dependency Model

The manifest parser supports dependency graphs through `alias_id` and `depends_on`.

Rules enforced by `parse_manifest()`:

- every dependency name in `depends_on` must match an existing `alias_id`
- cyclic dependencies are rejected
- jobs are returned in topological order before execution or submission

Jobs without an `alias_id` are still allowed, but other jobs cannot depend on them by name.

## Manifest Shape

`JobManifest` accepts either:

- a single job object
- a list of job objects

Each job can also include shared scheduling metadata:

- `alias_id`
- `batch_id`
- `depends_on`
- `priority`

## Example: Single Crawl Job

```json
{
  "task": "crawl",
  "payload": {
    "slug": "truyen/example-slug",
    "formats": ["epub"],
    "skip_illustrations": true
  }
}
```

## Example: Dependent Crawl And Render Jobs

```json
[
  {
    "alias_id": "crawl_story",
    "task": "crawl",
    "payload": {
      "slug": "truyen/example-slug",
      "formats": ["epub", "pdf"]
    }
  },
  {
    "depends_on": ["crawl_story"],
    "task": "render",
    "payload": {
      "manifest_path": "/path/to/manifest.json",
      "output_path": "/path/to/output.mp4",
      "fps": 30,
      "render_format": "landscape"
    }
  }
]
```

## Playwright Overrides

The CLI accepts:

- `--head-playwright`
- `--headless-playwright`

When you pass either flag to `vvrt run`, the runner rewrites `playwright_mode` for every `crawl` job in the validated manifest before submission or local execution.

Example:

```bash
vvrt run manifest.json --headless-playwright
```

## Operational Notes

- If the manifest file does not exist, the runner logs an error and exits.
- Local execution creates or reuses the SQLite database under the config path and starts a `JobWorker` when needed.
- In local mode, the runner waits for queued jobs to drain before shutting down the temporary worker.
- If a local Web UI is already running on `127.0.0.1:8000`, manifest submission is handed off to the API so logs and job state are visible there.

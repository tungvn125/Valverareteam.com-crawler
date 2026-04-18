# CLI Guide

## Entry Point `vvrt`

The package exposes `vvrt` as its command-line entry point. The CLI supports three top-level usage modes through the positional `ten_truyen` argument:

- normal story download mode: `vvrt <slug> ...`
- web server mode: `vvrt web ...`
- manifest runner mode: `vvrt run <file> ...`

The same parser also accepts a shared set of output, Playwright, and web-related flags.

## Standard Story Download Mode

Use standard mode when the first positional argument is a story slug or another story identifier that `resolve_story_url()` can resolve.

Example:

```bash
vvrt <slug> -f EPUB
```

In this mode, the CLI resolves the story URL, loads metadata, fetches the chapter tree, filters chapters, scrapes the selected content, and exports one or more output files.

## `web` Mode

Use `web` as the first positional argument to start the FastAPI-based Web UI:

```bash
vvrt web --host 0.0.0.0 --port 8000
```

Relevant flags in this mode:

- `--host`: host passed to the web server. Default: `127.0.0.1`
- `--port`: port passed to the web server. Default: `8000`
- `--workers`: number of concurrent novel workers for web mode. Default: `1`
- `--no-browser`: do not auto-open a local browser window
- `--head-playwright`: force headed Playwright for scraping tasks
- `--headless-playwright`: force headless Playwright for scraping tasks

## `run` Mode

Use `run` as the first positional argument to execute a job manifest file:

```bash
vvrt run manifest.json
```

If no manifest path is provided after `run`, the CLI logs an error and exits.

`run` mode also accepts the Playwright mode overrides:

- `--head-playwright`
- `--headless-playwright`

Those values are forwarded to the manifest runner so crawl or render jobs can use the requested browser mode.

## Chapter And Volume Selection

The CLI uses a mutually exclusive selection group for download scope:

- `--all`: download all chapters
- `--volumes <n> <n> ...`: download specific volume indexes
- `--chapters <n> <n> ...`: download specific flattened chapter indexes

If you do not pass one of these flags in CLI mode, the current implementation falls back to downloading all chapters.

Examples:

```bash
vvrt <slug> --all
vvrt <slug> --volumes 1 2
vvrt <slug> --chapters 1 2 3
```

## Output Formats

Use `-f` or `--format` with one or more values. The current supported choices are:

- `PDF`
- `EPUB`
- `HTML`
- `MD`
- `TXT`
- `MP3`
- `AD-MP3`
- `MP4`

Default:

```bash
--format EPUB
```

Multiple formats are allowed:

```bash
vvrt <slug> -f EPUB PDF HTML
```

Some formats need extra runtime dependencies or environment variables:

- `MP3` requires the audio export path to be available
- `AD-MP3` depends on `VVR_API_KEY` and `VVR_BASE_URL` for its AI-assisted path
- `MP4` also depends on the audio drama/video pipeline and warns when `VVR_API_KEY` or `VVR_BASE_URL` is missing

## Output Grouping

Use `-g` or `--gop` to control how files are grouped:

- `rieng`: export each chapter separately
- `volume`: export one file per volume
- `tatca`: export everything into a single combined output

Example:

```bash
vvrt <slug> -f EPUB -g volume
```

## Core CLI Flags

- `-o`, `--output`: output directory
- `--khong-minh-hoa`: skip illustration chapters
- `--font`: PDF font choice, either `NotoSerif` or `DejaVuSans`
- `-t`, `--tasks`: number of parallel tasks during scraping/export setup. Default: `5`
- `--fps`: video FPS for MP4 output. Choices: `30`, `60`. Default: `30`
- `--render-format`: MP4 render orientation. Choices: `landscape`, `portrait`. Default: `landscape`
- `--login`: force a manual login flow and capture a fresh session
- `--refresh-session`: remove the old saved session before continuing
- `--verbose`: enable more detailed logs

## Playwright Modes

The CLI exposes a mutually exclusive Playwright mode group:

- `--head-playwright`: run Playwright with a visible browser window
- `--headless-playwright`: force Playwright to run headless

If neither flag is passed, the CLI leaves the mode unset and the runtime falls back to its normal Playwright headless resolution.

## Examples

Download a story as EPUB:

```bash
vvrt <slug> -f EPUB
```

Download all chapters and export one EPUB per volume:

```bash
vvrt <slug> --all -f EPUB -g volume
```

Download selected chapters and export Markdown and text files:

```bash
vvrt <slug> --chapters 1 2 3 -f MD TXT
```

Run the web server without opening a local browser:

```bash
vvrt web --host 0.0.0.0 --port 8000 --no-browser
```

Run a manifest with explicit headless Playwright:

```bash
vvrt run manifest.json --headless-playwright
```

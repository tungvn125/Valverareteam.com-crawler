# Design Spec: LnHako retry + global Playwright head mode

Date: 2026-04-17
Status: Proposed (approved in chat, pending final user review)

## 1) Goal

Implement two focused improvements:

1. Add retry behavior for `LnHakoSource.get_content()` only.
2. Add global Playwright mode control with CLI flags + env fallback:
   - CLI (highest priority): `--head-playwright` and `--headless-playwright`
   - ENV (persistent config): `VVR_PLAYWRIGHT_MODE`
   - Default when unset: headless

This must apply consistently to all Playwright launch points, including fallback flows.

## 2) Current context

### LnHako content fetching
- `vvr_scraper/sources/lnhako.py` has `get_content()` that:
  - requires `self.browser`
  - launches a new page, navigates, waits for selectors, extracts paragraphs/images
  - currently has no retry loop

### Playwright launch points (current explicit/implicit behavior)
- `vvr_scraper/cli.py` (main scrape flow)
- `vvr_scraper/job_runner.py` (manifest/job run flow)
- `vvr_scraper/web/routes/download.py` (web download task flow)
- `vvr_scraper/web/routes/library.py` (library sync flow)
- `vvr_scraper/tao_so_do_cay.py` (chapter tree fallback internal launch)
- `vvr_scraper/video_renderer.py` (MP4 render flow)

## 3) Requirements

### Functional
1. `LnHakoSource.get_content()` retries transient Playwright failures with capped attempts.
2. New CLI flags:
   - `--head-playwright` => headed mode
   - `--headless-playwright` => headless mode
   - mutually exclusive
3. New ENV setting:
   - `VVR_PLAYWRIGHT_MODE=head|headless`
4. Precedence:
   - CLI flags > ENV > default headless
5. All launch sites must resolve mode consistently using shared helper in `vvr_scraper/utils.py`.

### Non-functional
- Keep changes minimal and backward-compatible.
- Avoid broad refactors unrelated to retry/head mode.
- Preserve existing runtime behavior when no new flags/env are set.

## 4) Selected approach

### A) LnHako retry: inline loop in `get_content()` (approved)
- Add retry loop around existing navigation + selector wait + extraction block.
- Policy:
  - total attempts: 3
  - backoff: 2s, 4s
  - retry only transient Playwright failures (navigation/timeout/network-like)
  - non-retryable errors fail fast
- Keep current final behavior: raise on unrecoverable/final failure.

Why chosen:
- Lowest-risk implementation for requested scope.
- Preserves current parsing logic.
- Easy to test incrementally.

### B) Global Playwright mode: shared resolver in `utils.py` (approved)
- Add a helper in `vvr_scraper/utils.py` to resolve headless mode from:
  - optional CLI overrides
  - env var
  - default
- Launch sites call this helper and pass explicit `headless=...` to `chromium.launch()`.

Why chosen:
- Single source of truth for precedence and parsing.
- Avoids duplicated conditionals across modules.
- Aligns with existing project preference to use `utils.py` for shared behavior.

## 5) Detailed design

### 5.1 Retry behavior in LnHako source
Target: `vvr_scraper/sources/lnhako.py`

Update `get_content(chapter_url)`:
1. Keep browser presence check and page lifecycle handling.
2. Wrap main fetch/extract logic in attempt loop.
3. On retryable exception:
   - if attempts remain, wait backoff and retry
   - else re-raise last exception
4. On success, return extracted `list[ContentItem]` exactly as today.

Retryable error set:
- Playwright transient failures (`TimeoutError` and related navigation/network exceptions exposed in async API).

### 5.2 Playwright mode resolution helper
Target: `vvr_scraper/utils.py`

Add helper (name to be finalized in implementation plan) that:
- accepts optional explicit CLI override (`head`, `headless`, or `None`)
- reads `VVR_PLAYWRIGHT_MODE`
- resolves final `headless: bool` by precedence:
  1) CLI explicit
  2) ENV
  3) default `True` (headless)
- tolerates invalid env values by falling back to default and optional debug/warn log.

### 5.3 CLI argument model
Target: `vvr_scraper/cli.py`

- Add mutually exclusive group for:
  - `--head-playwright`
  - `--headless-playwright`
- Translate these into explicit mode passed to resolver.
- Ensure scrape/web/run command paths propagate resolved mode into launch sites.

### 5.4 Launch-site integration
Update all launch sites to use resolved mode and pass `headless=...` explicitly:
- `vvr_scraper/cli.py`
- `vvr_scraper/job_runner.py`
- `vvr_scraper/web/routes/download.py`
- `vvr_scraper/web/routes/library.py`
- `vvr_scraper/tao_so_do_cay.py` (remove implicit default by making explicit)
- `vvr_scraper/video_renderer.py`

Note:
- Session capture in `session_manager.py` intentionally uses headed login UX today; out of scope unless explicitly requested.

## 6) Error handling

- LnHako retry:
  - Retry only known transient Playwright errors.
  - Preserve original exception semantics on final failure.
- Mode resolution:
  - Invalid env value should not crash; fall back to headless default.

## 7) Testing strategy (TDD)

### LnHako retry tests
File: `tests/test_sources.py`

1. Add failing test: first Playwright navigation attempt fails transiently, second succeeds; assert multiple attempts and successful content return.
2. Add failing test: all attempts fail transiently; assert final exception raised after max attempts.

### CLI + mode resolution tests
Files likely: `tests/test_cli_unit.py` and/or utility-focused tests

1. Add failing tests for parsing mutual-exclusive flags.
2. Add failing tests for precedence behavior:
   - CLI `--head-playwright` overrides env `headless`
   - CLI `--headless-playwright` overrides env `head`
   - env-only works
   - none set => headless
3. Add/adjust tests for launch calls receiving explicit `headless` value where mocks cover launch invocation.

## 8) Scope boundaries

In scope:
- LnHako content retry only
- Global Playwright mode resolution (CLI + env + default)
- Consistent integration at launch sites

Out of scope:
- Retrying LnHako HTTP metadata/list methods
- Source-specific rendering behavior redesign
- Session/login UX redesign

## 9) Rollout and compatibility

- Existing users without new flags/env keep current default headless behavior.
- New flags provide explicit runtime control.
- Env var provides persistent default across non-CLI-triggered paths.

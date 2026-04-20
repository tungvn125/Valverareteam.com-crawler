# CHANGELOG


## v0.3.0 (2026-04-19)

### Unknown

* Merge branch 'master' of https://github.com/tungvn125/Valvrareteam.net-crawler ([`f42349c`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f42349c7c1a03b1ffefd9a4573edc5511485b98a))


## v0.2.1 (2026-04-18)

### Bug Fixes

* fix: some error ([`940693e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/940693e60d9490f4296869fcc049c88cf4b3b2a6))

* fix: serveral code issue ([`343d064`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/343d064a7fffcf18aafc0ebae85bac6347c95b1f))

### Chores

* chore(release): 0.2.1 [skip ci] ([`4018261`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/4018261a26d775d545b4505392a7fd79ffa0222a))

* chore: verify social backend integration ([`b397c9f`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/b397c9f86a3df958b6171d1026ab6b06820d6023))

* chore: edit docker files for recent updates ([`2f337bd`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/2f337bdd675c8218251f7703351959484e9691d4))

* chore: format using ruff format ([`14cf8d9`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/14cf8d99d21df712016510bcf46a945c4e56e044))

* chore: delete cov ([`9f82afe`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9f82afe6f0b580854690a55c30f693eaca63ea26))

* chore: commit current workspace updates ([`ad9c085`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ad9c085606ef0b69d85bcf39f90e3f1ec9bd2269))

### Documentation

* docs: write some docs about the readest client/server ([`ae219c3`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ae219c36b678e61051368e28f87a1ae310f92438))

* docs: rewrite/add more docs ([`788ca99`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/788ca990d039b91c00932c8b31e8013921e4f409))

### Features

* feat: add social reactions, realtime broadcasts, and websocket manager

- Create SocialConnectionManager with chapter-scoped rooms
- Add reaction CRUD routes with owner-only delete
- Add websocket endpoint for chapter-scoped broadcasts
- Add get_reaction, delete_reaction, group_reactions_by_anchor to db
- Add in-process rate limiting (5/1s reactions, 1/3s comments)
- Add comment CRUD routes with owner-only edit/delete
- Add nested replies in list_comments
- Add update_comment, delete_comment to db ([`a20568a`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a20568a6c354e7549dbae3871cd3c21c088996bd))

* feat: add social auth and admin API routes ([`eae87ec`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/eae87ec817f62a24bd7475c583f715996f3cf3cb))

* feat: add social auth and admin bootstrap ([`6c3612b`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/6c3612bb205e3c88d3a2ee3119348204af452d45))

* feat: add social data models and queries ([`2759207`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/275920742aee07857654b4b13994ca33ff8ed449))

* feat: add social database foundation ([`9f2223e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9f2223e9872c22e0e271363a7558c8b8cd44e02a))

### Testing

* test: add reaction, comment, rate limit, and websocket broadcast tests ([`5cc7836`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/5cc783636cac5cff71b201b860e0d255110207a0))

### Unknown

* Merge branch 'master' of https://github.com/tungvn125/Valvrareteam.net-crawler ([`4518ba9`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/4518ba9a526c976f52990140cb584e8eb969e26b))


## v0.2.0 (2026-04-16)

### Breaking

* feat!: ship major scraper and web update

BREAKING CHANGE: this update introduces broad behavior and interface changes across audio-drama generation, web routes/state handling, and related data models/tests. Existing integrations and automation scripts may require updates. ([`e98e4fc`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/e98e4fc4647303cd7182a93494e7e3725137cfc9))

### Bug Fixes

* fix: stabilize async flows and test harness compatibility ([`f59fc04`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f59fc0400c8ecc08cc704e6f1e226357ddfa9fb4))

* fix(sources): cache adapters and close owned clients safely

Prevent adapter client leaks by adding aclose ownership semantics, avoid repeated source re-instantiation with domain caching, and harden temp file cleanup paths to avoid stale files after exceptions. ([`fa421a4`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/fa421a40ec4f91145b54a50bc8a93abd33670fdf))

* fix(web): deduplicate library check endpoint and parallelize update checks ([`672bfb5`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/672bfb53c848257e19553d1d343c7d4b6bcd50d2))

* fix: encode query params in SSR search using httpx params argument ([`3750264`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/375026401c7aeb991ec0b229bb484082ab8feb93))

* fix(job_worker): iterative BFS for cancel_dependents and align priority default

- Replace recursive cancel_dependents with iterative BFS to avoid
  hitting Python recursion limit on long dependency chains
- Change priority default from 3 to 0 to match job_models.py default ([`02c5b28`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/02c5b280994759adef07c5e6193c3a57a647b678))

* fix(video_renderer): add SO_REUSEADDR and health poll for port race condition

- Add sock.setsockopt(SO_REUSEADDR, 1) before bind to allow immediate rebind
- Replace fragile time.sleep(1) with health poll loop (30 retries, 0.1s interval)
- Add httpx import for async health check client ([`4f71898`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/4f71898f84d102c947ba7792f15930215cabe849))

* fix(correction): remove dead code and fix aggressive file deletion

- Delete _get_output_dir_for_slug (lines 88-114) - uses blocking
  run_until_complete which crashes on Python 3.10+, dead code since
  all routes use _async_get_output_dir instead
- Fix save_corrections: only delete MP3/WAV files whose name contains
  the chapter index pattern; remove manifest.json from deletion pattern ([`0571acd`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0571acd12ab0fc3d52839be560e8586c43295180))

* fix: restrict session file permissions to owner-only (0o600) ([`b43483e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/b43483ea00f7b9e7c5d630b34f1e897c8469ca6c))

* fix(opds): use UTC timezone for datetime in OPDS feeds

Replace datetime.now() + 'Z' with datetime.now(timezone.utc).isoformat()
to produce actual UTC timestamps instead of local time falsely marked as UTC.

Changes:
- vvr_scraper/opds.py: line 36 (create_feed), line 85 (add_entry fallback)
- vvr_scraper/web/routes/opds.py: lines 54, 146, 166 (nav entries, genres, authors) ([`1ee75b0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/1ee75b088cc71b65c0a66b450bbc21df84e9318d))

### Chores

* chore(release): 0.2.0 [skip ci] ([`d9e98f3`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/d9e98f37b8dfc38e4a10ec0fcf64375ba8920a55))

* chore(lint): apply ruff autofixes across tests and utils ([`2f5dd8a`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/2f5dd8ac81180cbdb0d8f29287cf7377b9d1fd0f))

* chore: update coverage data report ([`11c89f0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/11c89f07552bc7efbc35e67c992acdb729b4bbdd))

* chore: bump version to 1.10.0 ([`9a3fbee`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9a3fbee3a08264314aff46feb9068163accc88af))

* chore: sync version with pypi (1.9.0) ([`f710065`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f7100657e4dd50d4dd52c5192bed90735643ca85))

* chore(cd): remove pypi publish job per user request ([`afde6c8`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/afde6c8505b4cb57535de39d83ef7b14e65140ba))

### Testing

* test: add e2e integration tests for scrape -> export flow

- Add tests/test_e2e_flow.py with real HTTP tests for HTML/MD/TXT/EPUB export
- Tests use @pytest.mark.skipif to skip on CI (WAF blocks)
- Tests verify content integrity across export formats

fix(scraper): add SSR fallback to lay_thong_tin_truyen

- Story info page was not using SSR proxy, causing WAF blocks
- Now uses same SSR fallback as chapter scraping ([`44e9f27`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/44e9f279f28db55754b2642b03e95782178ec21c))


## v0.1.0 (2026-04-10)

### Breaking

* feat!: overhaul DevOps pipeline, testing infrastructure, and core security

BREAKING CHANGE: SQL strings migrated to parameterized queries. JobStatus strictly typed as Enum.

- Setup GitHub Actions for python-semantic-release & PyPI OIDC
- Add SQLite Sidecar backup with 7-day cron retention
- Instrument Prometheus /metrics & Grafana on docker-compose
- Introduce structured JSON logging (VVR_LOG_JSON)
- Boost coverage >60% via new Web API & Concurrency Edge tests
- Fortify against SQL injections and wrap Bare Except handlers
- Standardize contribution workflow via CONTRIBUTING.md
- Add property-based testing (Hypothesis) for utility functions ([`07abfb7`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/07abfb77251306b7f8ab99bd2c25b02b957b4ab5))

### Bug Fixes

* fix: change python-semantic-release build_command to native python build ([`ca1cc9e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ca1cc9ea79d2ca742f21cf1ae74a355104f7a59e))

* fix: format all files ([`f3392b0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f3392b09c78e1a4132a0da12298372e9b7eff1da))

* fix: require python 3.12 and fix CI dependency groups ([`cb0ceca`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/cb0ceca0c08d0de5382351106ebcf3a65c57cf2c))

* fix: ensure video renderer can track and report progress to DB ([`8fd7448`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/8fd744822e7313bb06b48b9a8e9df39e725bb8ff))

* fix: consistent job_id type hint in JobWorker ([`f9e30a6`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f9e30a6ea332cc5dad5bb0c877b83dba3aa851a4))

* fix: refine deduplication logic in generate ([`cb521a9`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/cb521a9392ce2d819a5753dce89d3834368b79e4))

* fix: Task 1 - add intensity/duration to mood_shift and normalize script output ([`3f6be86`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/3f6be86dbb7c854dc637bb0348e87fbb10bae3e7))

* fix: ensure temp cover cleanup on failure in lay_thong_tin_truyen ([`eeb27cb`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/eeb27cb25489026864176fcc2f0d4262bea3bddd))

* fix: add MAX_RETRIES to LLM parsing in audio_drama.py ([`c8ffe5c`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c8ffe5c8ad5f34c7e9ecabc7c134f4f978eacda8))

* fix: update ElevenLabs SDK usage to v2.x (use text_to_speech.convert) ([`4c52190`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/4c5219077a22b426a277a2a3f1545723567ad30e))

* fix: add JSON sanity fixes and stricter prompt to prevent common LLM syntax errors ([`cbc4f51`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/cbc4f517b81067cff118676e7059b3319fbb380a))

* fix: adjust chunk size to 4k and improve JSON error visibility ([`c7e149c`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c7e149c66c9a0facdccd6fba87196dfcb9aba306))

* fix: improve OpenAIParser chunking and add robust error logging for JSON decoding ([`071da43`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/071da4333f307200e4ed79cb40c4a8c510dbdd86))

* fix: robust JSON parsing in OpenAIParser and update test mocks ([`e68e98f`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/e68e98f021ae3ba5cc449197f869e061ebee5632))

* fix(audio): implement chunked parsing for audio drama, remove fallback, and add interactive retries ([`0cf075e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0cf075eb312f9c7c1b7a467f08330142c097256e))

* fix(audio): refine exporter v2 implementation and fix mock tests ([`faf642d`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/faf642df8aaa9e7b370099824fb4cf80177e8218))

* fix(audio): update default duck_db to -15.0 and improve MixingEngine tests ([`13bb524`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/13bb5242ea03318d0814cd9e840b48305b0c3639))

* fix(bgm): fix BGMManager issues in Task 1 of Audio Drama v2

- Update __init__ to use base_dir='bgm'
- Add .ogg support
- Normalize mood names to lowercase
- Return str from get_random_track ([`d8135aa`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/d8135aad210dc4203bcabdd6bcf07864cdca9810))

* fix(audio): BGMManager.get_random_track should return None if mood is missing ([`fd639d0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/fd639d0e75da1bc30e27361a4299792d22f85906))

* fix: use 'role' instead of 'character' and add safety_settings for Gemini ([`a0df113`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a0df1139cc5847a99754d2c71b15a8cd4961f0fb))

* fix: simple-term-menu ([`dcffada`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/dcffada39131dc1f582196a007c9fb853e995ddc))

### Chores

* chore(release): 0.1.0 [skip ci] ([`4c0bbe0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/4c0bbe0e6d4b05ea1fe777b063e123ccaf4f4761))

* chore: bump project's version in pyproject.toml ([`a4a0a8f`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a4a0a8f1e07c0103ed43213199ae404455dedd1b))

* chore: update project dependencies in pyproject.toml ([`3825c47`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/3825c47b936ce4e2360f11accf345cb781c89d8b))

* chore: replace vieneu with elevenlabs dependency ([`8ad5398`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/8ad5398fb7f97ff643d79a7878effba440ea3852))

* chore: bump project version in pyproject.toml ([`ce37c6c`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ce37c6c38a894f3ebf0c9d47f6b78e21f05bae54))

* chore: update project dependencies in pyproject.toml ([`0189e84`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0189e845503eee7fba5b55b73652f839d3152b3e))

* chore: update project dependencies in pyproject.toml ([`7a2b61e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7a2b61e218631e89c935e011860add87e2200826))

* chore: add *.png to gitignore ([`d2207e2`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/d2207e2d10f169113c5e998f261049ad6ef22c5e))

* chore: ignore .worktrees/ directory ([`da54d0b`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/da54d0b39c1dfb1010c6ec15ec20f668156f830a))

* chore: add verify/ directory to .gitignore ([`7286731`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/72867310a22fe7f4395758dbaa46b37f29b6cf0a))

* chore: update project dependencies in pyproject.toml ([`9e49175`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9e4917549f1f98ab40a4a3bdac1b77306caa9e9b))

* chore: move numpy and vieneu dependencies to optional audio extra ([`aeac9ad`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/aeac9ad35f660a5bf54a12018380b7162b924573))

* chore: ignore demo directory in .gitignore ([`bd7f1a9`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/bd7f1a9dcf60d214a1f89114e86fae440edaeea4))

* chore: add aiosqlite, google-generativeai, and vieneu dependencies and bump Python to 3.10+ ([`f552133`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f552133b6ff4dd16c3cfded21fd49be9a7b2494b))

* chore: add fastapi and uvicorn dependencies ([`07c66d3`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/07c66d304e172534027fae7acbba14cd1f5a4655))

### Documentation

* docs: replace outdated mentions of vieneu with ElevenLabs ([`a3fb3fc`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a3fb3fc0855317c345ef54233456932bd486191e))

* docs: update documentation to reflect ElevenLabs switch and cleanup lockfile ([`1c163b0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/1c163b0cb15a18f9339a741686a47cb6497c7145))

* docs: add ElevenLabs integration implementation plan ([`171d1f4`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/171d1f4a7dcb3a39586d719e243302c349047ac3))

* docs: add ElevenLabs integration design spec ([`27a8ac5`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/27a8ac5aa4db7ed7d6cecbe9a4edb236d4a4b5df))

* docs: update README and GEMINI for audio drama v2 atmospheric immersion ([`a68ad0d`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a68ad0d0a3bb5684bd658f7b76e71fa8bb507b46))

* docs: add implementation plan for audio drama v2 atmospheric immersion ([`0c6c6fa`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0c6c6fa0b2ddf89e6a11acc51ee0dca34f705a7d))

* docs: add design spec for audio drama v2 atmospheric immersion ([`3e174c8`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/3e174c892a127ae6937fc72f19189f284a8959f3))

* docs(plan): add implementation plan for Audio-Drama Generator ([`bc0ba2c`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/bc0ba2cfb973d45314e0c0074089896b64d9976c))

* docs(spec): add design doc for Audio-Drama Generator ([`db25036`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/db25036d397ff282f44ccf8c5801abbb296718ff))

* docs: Update Python version, introduce database management, enhance web server with a download manager, and detail design principles. ([`481f4c8`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/481f4c84bbe7be0b6d00c2f03e13d80b72953201))

### Features

* feat: integrate job worker into web server life cycle ([`ea6fae9`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ea6fae9674dc76b7ec0d569d390ea65cad1e7518))

* feat: add vvrt run command and orchestrator logic ([`76c67e9`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/76c67e95b5b5d06ad1be86b9baf73d8cfde41324))

* feat: initial JobWorker implementation ([`83475b6`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/83475b691f2e16528c4a1bf7237e0abe19618e4f))

* feat: add update_job_status to DatabaseManager ([`0096db4`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0096db4d3d7ef7998a683873aef4fbc018ead9ba))

* feat: define job models and update database schema with WAL mode ([`c8a3790`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c8a3790339ac7754090cbb2b074fdc345268b8eb))

* feat: implement CLI Autonomous Video Studio with frame-accurate rendering ([`1da12d6`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/1da12d6d209313515f55a6a82a17abab34a33bb0))

* feat: add elevenlabs and pydub dependencies and implement audioop compatibility for Python 3.13 ([`2ce9086`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/2ce908644dc78245aa48bc1f58bf52299ea88978))

* feat: implement Freesound integration with OAuth2 authentication and update scraper core for threaded file operations ([`2506a1c`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/2506a1cb6597b1f91e87ed3d6d915ba16e0c27d8))

* feat(web): add user warnings for library folder movement (Task 3) ([`065dc62`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/065dc622103ceb33d58453c8bb30ee0340a7b837))

* feat: cập nhật OPDS download link sang API endpoint (Task 2) ([`9a1ae32`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9a1ae3296af5955aebfae28f2e569fdc28eac137))

* feat(db): add get_novel_by_slug method ([`c968986`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c96898616749b14297ec81f1f4c0088226a39775))

* feat: add OPDS search and pagination support (Task 4) ([`8326428`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/832642810bca027b3ffdb42560116c189adefdd6))

* feat: integrate OPDS routes into FastAPI and add Basic Auth ([`0981561`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0981561788c91d465ad5de0182934d4de9a66f57))

* feat: implement OPDS XML generator module (Task 2) ([`464625b`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/464625b1e90ed43095a80c7927c7927e20cc2f79))

* feat: integrate and polish VVR-Cinema UI ([`62de43b`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/62de43bd8eb328fc2b79063a0a3043be6d38c6b8))

* feat: implement playback & sync logic for VVR-Cinema (Task 3) ([`bda2925`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/bda29251677bbf3e4cc230ed026f36b742ea2b1d))

* feat(cinema): refine UI with playback controls and weather VFX

- Rename #bg-canvas to #cinema-canvas for spec consistency.
- Add volume slider, speed selector, and scene selector placeholder.
- Implement CSS-based weather effects: rain, snow, and fog.
- Style controls for cinematic dark theme.
- Enhance Ken Burns transition smoothness. ([`13c707b`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/13c707bfb777b5a9879dd957469ef8c9d7c04f25))

* feat: initial cinema player UI ([`3028f89`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/3028f89adcc00660d4346fce0df2559aa9ec64b3))

* feat: serve novel assets and manifest API ([`0fa85f5`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0fa85f53dfb5f7626dc91f559b2ecffbda98aed4))

* feat: improve image generation with semaphore and better error handling ([`7292850`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/729285099ff373003a29bfe7aca1f455ae02a090))

* feat: add AI image generator with WebP support ([`86f51ba`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/86f51baa1d7f5ac188af2b8d3c439a265b6ef19b))

* feat: update director prompt and parser for VVR-Cinema visual cues ([`95f6f87`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/95f6f8715358a4ea4e42cf40a8c3f5396eb79092))

* feat: add dynamic BGM refresh and update README with supported formats ([`7fa1be3`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7fa1be3047b676e9b758a571568b27eef502d8fb))

* feat: commit prompt and update .gitignore ([`0feff52`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0feff52aac47699db94cecbb62b115939b6abc7b))

* feat: implement gender-aware voice assignment and externalize prompt loading in VoiceManager and ScriptParser. ([`6cbcfeb`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/6cbcfeb4420d9987eb7fea8b0b5e44db9515ee7b))

* feat: increase chunk size to 30,000 and remove max_tokens constraint in audio drama processing ([`befe948`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/befe948fcd79200df34635116bf63ce8ef0b123b))

* feat: use ElevenLabs for audio generation in exporter ([`9881229`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9881229f4c0cdf8380fa7560785148c1384bdea9))

* feat: update VoiceManager to use ElevenLabs ([`c41c9d0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c41c9d0989f05d4201c481813ade00031083e0a5))

* feat(audio): add support for .flac and .m4a audio formats in BGMManager ([`7e008d2`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7e008d291eac9a823689803fb8d9d15b74ecb032))

* feat: implement MixingEngine for core audio logic with ducking and padding ([`1240878`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/124087831d340fd4def346ac6ea59b8274b2763a))

* feat: upgrade OpenAIParser to support mood shifts in audio drama v2 ([`989cb5f`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/989cb5fe002b72b5c3eb1dbaf616fe6d10ac6813))

* feat(audio): setup BGMManager and add pydub dependency for audio drama v2 immersion ([`3ecd013`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/3ecd01386a1a0263485af66a67f7cbc53eed4ff2))

* feat: implement smart library sync with background update worker, incremental sync, and real-time dashboard updates ([`a128199`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a128199cf39aacf426bf093ed47c2f23433db788))

* feat: implement gender-aware audio drama voice allocation with global caching and thread-safe synchronization ([`53a2c69`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/53a2c698a385a1aeee3d13dc7a732547127a6a4e))

* feat: add VVR_MODEL environment variable support for configurable OpenAI model selection ([`93fbad3`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/93fbad358db709f2e1ce18e84c60999d043e490e))

* feat: replace Gemini with OpenAI API for audio drama generation and update configuration keys ([`702dabd`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/702dabd27054eeee926f5d8d2715fc45f52dd5d1))

* feat: integrate Audio-Drama (AD-MP3) into CLI and Web UI ([`e60d960`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/e60d960735891297602c534d08d63ab6580feec9))

* feat: implement tao_file_audiodrama with checkpointing ([`3cb83fd`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/3cb83fd6bc46051f864dac64b473d04660e28046))

* feat: implement GeminiParser and VoiceManager ([`f715bb5`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f715bb5d0b097ffba9948eefe25d082849f9e217))

* feat: implement character_voices table and DB methods ([`29ba67a`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/29ba67a60398e3c4073737ec9df21f496d636430))

* feat: migrate application data and configuration files to ~/.config/vvr-scraper/ and optimize browser session handling ([`3c818fd`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/3c818fdb002c0a419c685f59a9005dcf2f8c0147))

* feat: update project dependencies and configuration ([`e401a82`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/e401a826c01b76c5f7e0593bb36e968ea748c083))

* feat: Implement views data scraping and display, and enhance cover image retrieval. ([`08f6064`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/08f60646d2b605b812ebe2168c9a16b728cb3e2b))

* feat: Implement download checkpointing and resume functionality, enhance cover image handling, and refine chapter selection logic. ([`a91d052`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a91d05290260342838de9196d930b505c55fcc3b))

* feat: add AI-powered Audiobook (TTS) export using VieNeu

- Implement  in  with chunked processing to handle large texts.
- Add lazy-loading for heavy AI libraries (, ) to maintain fast CLI cold start.
- Integrate MP3 format into Web Dashboard, Interactive CLI, and API.
- Update  with new dependencies and bump version to 1.4.0.
- Enhance documentation in  and .
- Silence hardware/framework warnings for a cleaner terminal experience. ([`351109a`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/351109a97eda921701a17d3e9d4b89fbcef8dc6f))

* feat: add Download Queue support to both CLI and Web modes

- Refactor CLI to process multiple novel slugs sequentially.
- Implement worker-based DownloadManager in the web backend.
- Update argument parsing to handle 'vvrt web' and 'vvrt slug1 slug2' at the top level.
- Add task-specific log isolation in the web UI.
- Bump version to 1.3.0 and update README/GEMINI docs. ([`5f074d5`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/5f074d5a7aa436c74ea7fd5a422cad86a07e4b52))

* feat: add --workers argument to configure download concurrency ([`514f5ff`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/514f5ff75ae79bf9e9212126e15ad440f2f4cb5b))

* feat: update UI to support per-task logs and queued state ([`900b978`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/900b978d3af07fda4bbb45ed35b479ecdace817a))

* feat: isolate logs per task using loguru binding ([`86d20f3`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/86d20f3b43cc81ea9b2adbf48d95410be7848a8d))

* feat: implement worker-based download queue ([`062702d`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/062702d5ebf1102de3701aa612949f537ffb2e7d))

* feat: add FastAPI-powered Web Dashboard (vvrt web)

- Implement FastAPI backend with search, download, and folder browsing APIs.
- Add WebSocket support for real-time log streaming and progress updates.
- Create a modern, responsive vanilla HTML/CSS/JS frontend.
- Integrate "Native Folder Selection" with fallbacks (zenity, kdialog, tkinter).
- Update CLI to support the web sub-command and custom ports.
- Bump version to 1.2.0 and update all documentation (README.md, GEMINI.md). ([`c9d6168`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c9d61687b0958c1799d265396041acc2e4a3680e))

* feat: add modern clean frontend dashboard ([`334b646`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/334b6461ef7e26a943a899aa7f5fe29384d4cb50))

* feat: add download endpoint and task execution logic ([`456d0cd`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/456d0cd192198236064909cd6a6d157fb92d4af9))

* feat: implement websocket log streaming ([`54776ba`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/54776bac402eff4f12cd6be6591bf5c4526de3ba))

* feat: add basic web sub-command and FastAPI server ([`7ebd308`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7ebd3087aec285c19972848be90dc3fc05c6699d))

* feat: add live novel search and authenticated fast-mode scraping

- Implement live interactive search with real-time suggestions using prompt-toolkit.
- Automate slug resolution using MongoDB ID suffix (last 8 characters).
- Add high-speed 'Fast Mode' scraping using httpx and DigitalOcean SSR fallback.
- Extract Bearer tokens from Playwright session to support authenticated SSR requests.
- Improve URL normalization to better match website slug generation logic. ([`135cbfb`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/135cbfb4e3488eac4c4c30cdf56e15cd12d14711))

* feat: add support for genres metadata and original chapter titles

- Extract genres/tags from novel main page and embed as DC:subject in EPUB.
- Use original chapter titles from website instead of slugified URLs.
- Improve filename sanitization to preserve Vietnamese characters for better readability.
- Update Chapter data structure to include both title and URL.
- Update test suite to verify genre extraction and new chapter data format. ([`9b9a436`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9b9a4361a5653dd28d3bf93f3c1fc6056d537a4e))

* feat: add dynamic session capture and support for protected chapters

- Implement manual session capture using non-headless Playwright to bypass Cloudflare and authentication.
- Reuse captured session state (cookies/local storage) for all automated scraping tasks.
- Add support for crawling both published and protected chapters by sharing session state with the tree-building logic.
- Add --login, --refresh-session, and --verbose command-line flags.
- Prompt for manual login if no session is detected.
- Modernize request headers to match recent site requirements.
- Update tests and documentation to reflect new features.
- Update .gitignore to exclude test outputs, documentation, and temporary files. ([`1bf0029`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/1bf00299c3d7c882ad55cca0d9a9e5e9a4e4660b))

* feat: add multi-format export + volume merge support

- Added support for exporting chapters as HTML, Markdown (.md) and plain text (.txt)
- Implemented volume-level content merging into single unified file
- Added menu option to choose:
    • Merge all volumes into one file (epub/pdf/html/md/txt)
    • Export each volume as separate files
- Extended scraper.py logic to build combined content_list per volume
- Kept original EPUB/PDF generation intact
- Expanded output format flexibility across entire scraping flow ([`afb2d69`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/afb2d69c0da36ca49231d28eefd6d45d147d89bf))

### Performance Improvements

* perf: optimize scan_library with directory exclusions ([`e1bfc68`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/e1bfc684d2546123851c88161ceee536b4583445))

* perf: parallelize library sync tree fetching in web.py ([`2d767dc`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/2d767dcf4299419489e850f4cc220de228565631))

### Refactoring

* refactor: use global worker instance as per requirements ([`d35b8bb`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/d35b8bbeabbc81d81071208243c5be922dcdcd6b))

* refactor(web): refine manifest security and static mount defaults ([`7b46852`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7b468527103401ed3f2c4d98acd7c606a463c96c))

* refactor: standardize cinematic manifest schema and alignment data keys ([`42b55ce`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/42b55ceaa24069623ffe6f611519dae91c16b21d))

* refactor: add shared httpx client and semaphore to ImageGenerator ([`b0c26fb`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/b0c26fb9df5db0e0f28e032e5a18432ead3c561b))

### Testing

* test: add comprehensive tests for universal task runner ([`ee9dc52`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ee9dc52e9f27b70d196f62346da647d98df5e6db))

* test: add robustness tests for image generation ([`4aa5d89`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/4aa5d89baee889a66bda6c52e1b9d87bde374594))

### Unknown

* Refactor web UI to ES modules, add Docker configuration, and comprehensive tests

This commit includes:
- Migration of the monolithic app.js to a modular, ES module-based architecture in static/js/.
- Refactoring the single web.py to a package structure with modular routes in vvr_scraper/web/.
- Introduction of Docker and Docker Compose configuration.
- Extended test suites using pytest including tests for new job runner components and web API routes.
- Task runner documentation and new job parser integration. ([`603f50d`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/603f50d1bc35bae4708eb7d7e96c71de749c55e1))

* cli: add MP4 export options and interactive menus ([`38bac32`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/38bac32e98ca427802136e720e2a5e1ef78e8478))

* Refine cinema player for performance and robustness

- Optimized event loop using index pointer (nextEventIndex)
- Cached karaoke word spans to avoid repeated DOM queries
- Implemented robust seekTo(timeMs) with state recovery
- Added visual error feedback and audio error handling
- Improved memory management with proper sync loop control and visibility handler ([`ef6eb64`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ef6eb64cedefbbee69dadceaf1fcf2af77decf52))

* Merge branch 'feat/elevenlabs-integration' into master ([`d3cd5aa`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/d3cd5aa17edca0a60e5882e0041a21a07305c4da))

* nothing ([`e236650`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/e236650070d109c4da760c2962d20c2bf66ef98a))

* Delete some vibe-coded stuff ([`cabd0e9`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/cabd0e9d7b14e6b3e956632e9dade580735f4fd5))

* Merge branch 'master' of https://github.com/tungvn125/Valvrareteam.net-crawler ([`b8c0060`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/b8c00604f8e797238663d5b2f9855f15240ca823))

* nothing ([`5bf90e0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/5bf90e09b23fe06b5615f99a3631a8e971f2d9e0))

* web: implement batch import modal and frontend handler ([`7495c57`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7495c5795df4b1c724f7e10bc98279d36959780b))

* web: implement library tab UI and update sync logic ([`45e2303`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/45e2303e0d2899a8d053f7652ddf34d287d6fe87))

* web: implement update checker, migration scan, and batch import API ([`982246e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/982246ee7c0f7933abe6f2be77017cd913eb36e6))

* web: enhance checkpoints with metadata and integrate DB upserts ([`c5da15e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c5da15e9ef4903fa64bb8bef29a7d68bba23e1af))

* db: implement async sqlite library manager with unique slug constraint ([`803ff35`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/803ff35bbe738f23e32d359f42cbcbcb130ef860))

* web: implement task controls, log history retrieval, and settings modal ([`7a02ecf`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7a02ecf05526abff6547b6657d701ce4055ce809))

* web: refactor UI to sidebar-based dashboard layout ([`ff39d0d`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ff39d0d1c9bae8ee033ed9b313fb3c48391c5b37))

* web: implement CSS variable-based theme system and dark mode toggle ([`a64d9e8`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a64d9e8d69467f0b804fc49f5817fc1e5dfd6cd5))

* web: implement task tracking, log buffering, checkpoints, and control endpoints ([`b3a5bb4`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/b3a5bb4221b4b7daa0d230d65d090081aa928fc0))

* web: implement tree selection modal with search and filtering ([`8b4df39`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/8b4df390f3375533a347038f4e074fa70aa482ad))

* web: implement information preview modal and backend endpoint ([`eb65a9e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/eb65a9e4e71db11b21d2cecbc261a627678cbe11))

* web: add chapter list endpoint and support targeted downloads ([`ad9d124`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ad9d124c485ee67ac24961f25d6b92c1dc67044b))

* scraper: update get_chapter_tree_list for locked chapters and illustrations ([`f582af2`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f582af25009512932abc9779214b69ee16a4cb40))

* scraper: extract total chapters and word count in lay_thong_tin_truyen ([`c0d0e4d`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c0d0e4df3286bdee87da70aea8cc105e4edf3b34))

* models: add total_chapters and word_count to StoryInfo ([`c26d5cb`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c26d5cbd1664adac2772973443d34758165e2577))

* update: system/os requirement + workers agrs ([`33c41f4`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/33c41f4cd67538f450ef817fac4536561821e513))

* rm: debug_sitemap.py ([`e6f28ed`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/e6f28ed0ed1a115fc6321bc437d4d2b4591f1a1c))

* update GEMINI.md ([`9abbd09`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9abbd095a676fefda70154264ec15782b3972178))

* FEAT: PyPi installation ([`ebbd954`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/ebbd954d9c5655e5db6b7f29c8c6946c3cf3b06f))

* Fix some bug ([`9e85915`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9e859155cbca7c92225a296308fbe4f08a590492))

* update GEMINI.md ([`a3daab8`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a3daab86217d7eff2ecdaa4c72a96aa6ca8de8b0))

* add: dynamic live novel search feature ([`0848467`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/084846769c4ccc17989d05f756444553259e330d))

* delete: example_trang_chinh.html bc it useless ([`c6e7dce`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/c6e7dce687f5780dd7e05f6902a25766d0319d46))

* Merge branch 'master' of https://github.com/tungvn125/Valvrareteam.com-crawler ([`7520e95`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7520e954673917675e23facb07b4a40cfdbf4d3a))

* Modify vvrt alias instructions in README

Updated alias instructions for vvrt command in README. ([`59809e0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/59809e005ad919e816517836c4b456492f703609))

* edit ([`baedb29`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/baedb2957d91caaa5d2a1fa5781921d26348a9c9))

* add: setup for linux ([`68be3ad`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/68be3ad0875e2d0dfa508768c1063dbdbd98e29b))

* edit readme for recent update ([`9240b59`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/9240b594bc4c7a962c7b6e80e7c26e9acf44c300))

* create new test ([`8027506`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/802750630ca6dca8574a4291fe966e4223cfa540))

* Improve code, but not add any feature ([`13e0fb8`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/13e0fb8efccb7259ff1f17e394319233fd1d7f1c))

* improve: only install chromium-headless-shell ([`2937f4f`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/2937f4f70188013116539e2b24231a5c3fda956f))

* add: exception for error chapter(block, required login, .... ([`0c992e1`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/0c992e15b8ee2f115d0319d5f0118ab19f359937))

* improve: create folder ([`516d179`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/516d179df1018059b11eb8e455b3910c3b5be048))

* change: rewrite for updates ([`960ba1e`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/960ba1e703f8dc5d6494e1868f2ad4a60eb62ee8))

* add auth(cookies file) ([`7706323`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/770632390cb36415c6039729e49e12f194969285))

* only install chromium-headless-shell ([`5275e0a`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/5275e0af26283876491334b447889f18bfbc8af6))

* add argparse ([`bd2a0a0`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/bd2a0a0a360c93f3849708f81f1a212bfa90ef47))

* add metadata ([`5ab5d77`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/5ab5d775aa7991c8a3edfa82b7887d385be02044))

* playwright:only install chromium ([`f2115a8`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f2115a8b6832c1b3eba8e5c5441ccba99a54b90e))

* add "venv" ([`98b7b09`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/98b7b09705eed96d9bf891d0498ce5dceb8e97ff))

* add "venv" ([`f035f9a`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f035f9af2ef9b414cf3fe016825acf6fdd977aef))

* add choice menu ([`d2ff343`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/d2ff343b17c52c8a4495c99d347ec016b7411cbf))

* create install.sh ([`10b4071`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/10b40719977ea67a512a4016a62c8ea8b02d9b40))

* notthing ([`418058c`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/418058c2a5ef1ed481a04bcc8fab00583668bb7a))

* add simple-term-menu ([`367b359`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/367b359d18c11a680d8831cefecf3ebf275e79ce))

* improve the saving function ([`845668a`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/845668a1560791175530d5a754e3b31aae4642e8))

* add more things to ignore ([`176fc09`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/176fc09633d54d14f2aea6392b7d1015ae5c2702))

* Changed for update ([`fb3b19d`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/fb3b19d8a6e42d935148dea27df6955dffb2ad79))

* add a sorting feature for output files ([`7c5dba1`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/7c5dba142c6e6f572471bf41caa2aa75bef75e97))

* add progress bar ([`68b8a10`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/68b8a10fcfe8a2cd336cf122a8ba8ebc403d33d9))

* fix some typo ([`1fa8d8a`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/1fa8d8aba40ed2f0cc0b4c9901a2aea28447ee94))

* tree map added ([`45478d3`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/45478d30d777badeb83e6f070f2d1e3246e7fec7))

* Add files via upload ([`a8c4890`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/a8c489007ea16bf4fecf6305a9d8356bb7e287e4))

* Initial commit ([`f7a4eb2`](https://github.com/tungvn125/Valvrareteam.net-crawler/commit/f7a4eb2e87e978ce478d08902e45320964de0e0c))

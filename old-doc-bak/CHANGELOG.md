# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.9.1] - 2026-04-10

### Added
- **API Documentation**: Added complete OpenAPI descriptions and summaries to all FastAPI endpoints for better Swagger/Redoc UI integration.
- **Security Check**: Enforced database constraint mapping with column whitelisting to eliminate potential SQL injection vectors.
- **Dependency Tracking**: Introduced parameterized SQL queries across background task handlers to significantly securely deal with SQL data.

### Changed
- **CLI Subcommands**: Fixed inconsistent CLI documentation in README (`vvrt crawl` updated to `vvrt <slug>` and `vvrt serve` updated to `vvrt web`) to match the codebase actual usage.
- **Magic Strings Removed**: Systematically replaced all string-based states (`pending`, `running`, `success`, `failed`, `cancelled`) with type-safe `JobStatus` enums.
- **Linter Cleanup**: Resolved over 138 linting errors, including eliminating dangerous `except:` blocks that suppressed hidden failures (KeyboardInterrupt, SystemExit) and unused variables.
- **Code Deduplication**: Consolidated multiple instances of `resolve_story_url` scattered across `cli.py` and `job_runner.py` into a unified utility function `vvr_scraper/utils.py`.

### Fixed
- Fixed broken pipe exception swallowing in FFmpeg handling when video rendering fails (`raise from e`).
- Fixed delayed task failures due to bad connection polling logic in WebSocket state manager.

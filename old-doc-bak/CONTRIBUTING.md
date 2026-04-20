# Contributing to VVR-Scraper

Thank you for your interest in contributing to VVR-Scraper! To maintain a clear project history and automate our release pipelines, we use **Conventional Commits**.

## Conventional Commits Protocol

This project uses `python-semantic-release` to automate version bumps (MAJOR.MINOR.PATCH) and to generate the `CHANGELOG.md`. **All commits must follow the Conventional Commits format.**

### Commit Message Format

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Types

The `<type>` communicates the nature of your change. It determines how the version number will be bumped and if the commit appears in the changelog.

| Type       | Description                                                                 | Version Bump | Appears in Changelog |
|------------|-----------------------------------------------------------------------------|--------------|-----------------------|
| `feat`     | A new feature.                                                              | MINOR        | Yes                   |
| `fix`      | A bug fix.                                                                  | PATCH        | Yes                   |
| `docs`     | Documentation only changes.                                                 | None         | No                    |
| `style`    | Changes that do not affect the meaning of the code (white-space, etc.).     | None         | No                    |
| `refactor` | A code change that neither fixes a bug nor adds a feature.                  | None         | No                    |
| `perf`     | A code change that improves performance.                                    | PATCH        | Yes                   |
| `test`     | Adding missing tests or correcting existing tests.                          | None         | No                    |
| `chore`    | Changes to the build process or auxiliary tools and libraries.              | None         | No                    |

### Breaking Changes ⚠️

If your commit introduces a breaking change (e.g., changing an API endpoint, modifying a database schema in an incompatible way), you **must** indicate this by appending a `!` after the type/scope, or including a `BREAKING CHANGE:` footer.

**Example 1 (`!` notation):**
```text
feat!: redesign OPDS JSON feed structure
```

**Example 2 (Footer notation):**
```text
chore: drop support for Python 3.9

BREAKING CHANGE: We now use match-case extensively, requiring Python 3.10+.
```

Breaking changes will automatically trigger a **MAJOR** version bump.

### Examples of Good Commits

- `feat(audio): add support for multiple languages in elevenlabs synthesis`
- `fix(db): resolve connection pool leak during parallel scraping`
- `docs: update README with docker-compose instructions`
- `test: implement unit tests for CLI argument parsing`

## Development Workflow

1. Fork the repository and create your branch from `master`.
2. Make your changes and test them locally (`pytest`).
3. Commit using the Conventional Commits format.
4. Push to your fork and submit a Pull Request.

The CI pipeline will verify your formatting and run tests before merging.

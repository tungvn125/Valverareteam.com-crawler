# Issue Remediation Design

## Goal

Execute a focused remediation pass that fixes currently measurable issues and the highest-value technical weaknesses identified in the review, without expanding into a full architectural rewrite.

This pass is intentionally scoped to improve correctness, consistency, and confidence in the riskiest areas of the codebase while preserving the existing product shape and feature set.

## Scope

This remediation pass includes the following work:

1. Make the current quality gate pass.
2. Fix currently visible runtime correctness issues.
3. Improve regression safety in high-risk orchestration areas.
4. Apply targeted architectural fixes with high return on investment.

This remediation pass does not include repo-level cleanup of local artifacts because the user explicitly chose to handle that separately.

## Constraints

The work must follow these constraints:

- Preserve current user-facing functionality unless there is a clear bug.
- Prefer small, local changes over broad redesign.
- Do not expand into a full rewrite of the web state model, exporter architecture, CLI architecture, or job system.
- Focus new tests on high-risk orchestration and API behavior instead of chasing blanket coverage increases.
- Only refactor when the refactor directly supports correctness, consistency, or testability.

## Recommended Approach

The remediation will use a two-phase strategy.

### Approach A: Stabilize-first, refactor-later

Fix all immediately measurable issues first, then stop or defer structural work.

Pros:

- Lowest risk.
- Fastest path to a green quality gate.
- Easy to validate progress.

Cons:

- Leaves some high-value architectural friction in place.
- Improves symptoms more than long-term maintainability.

### Approach B: Targeted structural cleanup

Fix measurable issues while also doing broader targeted refactors in the highest-friction modules.

Pros:

- Larger quality improvement in one pass.
- Better path toward a higher long-term rating.

Cons:

- Higher regression risk.
- Scope can expand quickly.
- Requires more test work to stay safe.

### Approach C: Two-phase remediation

First fix the measurable issues and strengthen tests around high-risk paths. Then apply only the smallest structural changes justified by the stabilized code and test results.

Pros:

- Best balance of safety and quality.
- Avoids refactoring based on intuition alone.
- Creates a clear stop point after the system is stable.

Cons:

- Takes two deliberate passes instead of one large sweep.

### Decision

Use Approach C.

This is the best fit for the agreed priority of a balanced remediation pass. It gives immediate improvement in correctness and quality gates, then allows narrowly scoped structural cleanup where it clearly reduces risk or improves testability.

## Work Areas

### 1. Quality Gate

Primary target:

- `ruff check .` passes.

Expected work:

- Fix current lint failures in files covered by the quality gate.
- Keep behavior unchanged unless the lint issue exposes a real bug or ambiguity.
- Only exclude files from lint if they are clearly scratch/demo material and exclusion is justified by current repository standards.

Non-goals:

- Broad style churn.
- Cosmetic rewrites unrelated to correctness or maintainability.

### 2. Runtime Correctness

Primary targets:

- Current test-time warnings that indicate real correctness or lifecycle problems.
- Inconsistent API error handling.

Expected work:

- Investigate and reduce warnings currently visible during test execution.
- Standardize API failure behavior in `vvr_scraper/web/routes/api.py`.
- Prefer `HTTPException` for API-level error reporting.
- Avoid mixed response styles such as returning tuples or returning arbitrary error payloads where a structured HTTP error is more appropriate.

Decision rule:

- If a warning is purely external or dependency-driven and cannot be fixed safely in scope, document and isolate it rather than forcing a broad dependency or architecture change.

### 3. Regression Safety

Primary targets:

- `vvr_scraper/job_runner.py`
- `vvr_scraper/web/routes/api.py`
- `vvr_scraper/web/routes/correction.py`

Expected work:

- Add tests around high-risk orchestration branches, error paths, and route behavior.
- Increase confidence in real integration points rather than optimizing for raw coverage percentage.
- Prefer tests that protect future refactors in orchestration-heavy modules.

Success condition:

- The targeted modules become measurably safer to change because their important branches and failure behavior are exercised.

### 4. Targeted Architecture Fixes

This pass allows only focused architectural improvements that directly support correctness, consistency, or testability.

#### `vvr_scraper/web/routes/api.py`

Goals:

- Normalize error semantics.
- Make route behavior easier to reason about and test.
- Preserve existing success responses unless a current behavior is clearly broken.

Allowed changes:

- Small helper extraction.
- Consolidation of duplicated error handling.
- Route-local cleanup that reduces branching ambiguity.

#### `vvr_scraper/job_runner.py`

Goals:

- Reduce orchestration complexity enough to improve readability and testability.
- Keep the existing top-level job behavior intact.

Allowed changes:

- Extract local helpers for session bootstrap, chapter selection, export input assembly, and metadata/progress updates.
- Separate steps with clear boundaries inside the file or through small internal helpers.

Non-goals:

- Full service-layer rewrite.
- Replacing the job system design.

#### `vvr_scraper/web/state.py` and state consumers

Goals:

- Reduce the most direct and fragile access patterns to mutable global state.
- Improve testability of key access points without redesigning the entire state model.

Allowed changes:

- Introduce narrower access points or helper wrappers where routes currently reach too deeply into globals.
- Simplify the highest-friction call sites.

Non-goals:

- Full migration to app-scoped dependency injection.
- Full replacement of singleton runtime state.

#### `vvr_scraper/web/routes/correction.py`

Goals:

- Improve clarity and safety in file/path/data error branches.
- Raise confidence through targeted tests.

Allowed changes:

- Local refactors that make save/load/correction/character update flows easier to test.
- Small helper extraction if needed to isolate file discovery or payload validation behavior.

Non-goals:

- Full decomposition of the module into a new subpackage.

## Execution Order

The implementation should proceed in this order:

1. Fix quality gate failures.
2. Standardize API error handling and other immediately visible correctness issues.
3. Add or update targeted tests around affected orchestration and route paths.
4. Apply the smallest structural refactors needed to support correctness and testability.
5. Re-run full verification before claiming the remediation is complete.

This order keeps regressions contained and ensures refactors happen with stronger test coverage in place.

## Verification Strategy

Primary verification commands:

- `ruff check .`
- `pytest`

Focused verification should also be used while iterating in the high-risk modules, especially around:

- API route behavior
- job orchestration behavior
- correction route behavior

Verification policy:

- No change is considered complete without fresh command output confirming the relevant behavior.
- If a warning remains, its source must be understood and explicitly judged in-scope or out-of-scope.

## Completion Criteria

This remediation pass is complete only when all of the following are true:

1. `ruff check .` passes.
2. `pytest` passes.
3. The currently visible runtime warnings are either fixed or explicitly reduced to a well-understood, justified residual set.
4. `vvr_scraper/web/routes/api.py` uses more consistent and intentional error handling.
5. Regression safety is improved in `job_runner.py`, `web/routes/api.py`, and `web/routes/correction.py` through targeted tests.
6. Targeted structural fixes have reduced friction in high-risk orchestration areas without expanding into a full redesign.

## Accepted Residual Debt

The following debt is explicitly allowed to remain after this pass:

- The broader global-state model in the web layer.
- Large-module debt in `cli.py` and `exporter.py`.
- Full architectural decoupling between runtime, routes, and orchestration.
- Broad repository hygiene work unrelated to the code and test issues in scope.

These items remain outside this remediation pass so the work stays bounded and executable.

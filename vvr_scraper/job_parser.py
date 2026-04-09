from .job_models import JobManifest, JobType


class ValidationError(Exception):
    """Raised when job manifest validation fails."""

    pass


def parse_manifest(manifest: JobManifest) -> list[JobType]:
    """
    Parses a JobManifest, validates dependencies and ensures no cycles exist (DAG).
    Returns a list of jobs sorted topologically by their dependencies.
    """
    jobs = manifest.jobs

    # Create a map of alias_id to job for easy lookup
    job_map = {job.alias_id: job for job in jobs if job.alias_id}

    # Check for missing dependencies first
    for job in jobs:
        if job.depends_on:
            for dep in job.depends_on:
                if dep not in job_map:
                    raise ValidationError(f"Dependency '{dep}' not found in manifest")

    # Validate DAG (Cycle detection) and return topological sort
    return get_topologically_sorted_jobs(jobs)


def get_topologically_sorted_jobs(jobs: list[JobType]) -> list[JobType]:
    """
    Uses Kahn's algorithm or DFS to return jobs in topological order.
    """
    adj = {job.alias_id: job.depends_on or [] for job in jobs if job.alias_id}

    visited: set[str] = set()
    rec_stack: set[str] = set()
    sorted_aliases: list[str] = []

    def visit(u: str):
        if u in rec_stack:
            raise ValidationError(f"Cyclic dependency detected involving '{u}'")
        if u not in visited:
            rec_stack.add(u)
            for v in adj.get(u, []):
                visit(v)
            rec_stack.remove(u)
            visited.add(u)
            sorted_aliases.append(u)

    # Process jobs with alias_id
    for job in jobs:
        if job.alias_id and job.alias_id not in visited:
            visit(job.alias_id)

    # Map sorted aliases back to job objects
    job_map = {job.alias_id: job for job in jobs if job.alias_id}
    sorted_jobs = [job_map[alias] for alias in sorted_aliases]

    # Add jobs that don't have an alias_id (they can't be depended on)
    # These can go anywhere in the sorted list, but we'll put them at the end.
    for job in jobs:
        if not job.alias_id:
            # Still need to check if their dependencies are met (already done in parse_manifest)
            sorted_jobs.append(job)

    return sorted_jobs

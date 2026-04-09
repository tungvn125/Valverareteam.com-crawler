import pytest

from vvr_scraper.job_models import JobManifest
from vvr_scraper.job_parser import ValidationError, parse_manifest


def test_parse_manifest_valid_no_deps():
    data = [{"task": "crawl", "payload": {"slug": "test-1"}}, {"task": "crawl", "payload": {"slug": "test-2"}}]
    manifest = JobManifest.model_validate(data)
    # parse_manifest should return the list of jobs if valid
    jobs = parse_manifest(manifest)
    assert len(jobs) == 2
    assert jobs[0].payload.slug == "test-1"
    assert jobs[1].payload.slug == "test-2"


def test_parse_manifest_valid_with_deps():
    data = [
        {"alias_id": "job1", "task": "crawl", "payload": {"slug": "test-1"}},
        {
            "alias_id": "job2",
            "task": "render",
            "payload": {"manifest_path": "m.json", "output_path": "o.mp4"},
            "depends_on": ["job1"],
        },
    ]
    manifest = JobManifest.model_validate(data)
    jobs = parse_manifest(manifest)
    assert len(jobs) == 2
    assert jobs[1].depends_on == ["job1"]


def test_parse_manifest_cyclic_dependency():
    data = [
        {"alias_id": "job1", "task": "crawl", "payload": {"slug": "test-1"}, "depends_on": ["job2"]},
        {"alias_id": "job2", "task": "crawl", "payload": {"slug": "test-2"}, "depends_on": ["job1"]},
    ]
    manifest = JobManifest.model_validate(data)
    with pytest.raises(ValidationError, match="Cyclic dependency detected"):
        parse_manifest(manifest)


def test_parse_manifest_missing_dependency():
    data = [{"alias_id": "job1", "task": "crawl", "payload": {"slug": "test-1"}, "depends_on": ["non-existent"]}]
    manifest = JobManifest.model_validate(data)
    with pytest.raises(ValidationError, match="Dependency 'non-existent' not found"):
        parse_manifest(manifest)


def test_parse_manifest_self_dependency():
    data = [{"alias_id": "job1", "task": "crawl", "payload": {"slug": "test-1"}, "depends_on": ["job1"]}]
    manifest = JobManifest.model_validate(data)
    with pytest.raises(ValidationError, match="Cyclic dependency detected"):
        parse_manifest(manifest)

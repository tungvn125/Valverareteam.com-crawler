from vvr_scraper.job_models import JobManifest
from vvr_scraper.job_parser import parse_manifest


def test_parse_manifest_out_of_order():
    data = [
        {
            "alias_id": "job2",
            "task": "render",
            "payload": {"manifest_path": "m.json", "output_path": "o.mp4"},
            "depends_on": ["job1"],
        },
        {"alias_id": "job1", "task": "crawl", "payload": {"slug": "test-1"}},
    ]
    manifest = JobManifest.model_validate(data)
    # This should work if parse_manifest doesn't care about order
    jobs = parse_manifest(manifest)
    assert len(jobs) == 2
    # But will it work in the runner?
    # Let's see if the cycle detection works when out of order
    # job2 -> job1
    # job1 -> []
    # No cycle, so it should pass.

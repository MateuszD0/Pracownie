from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def workflow(name):
    # BaseLoader preserves GitHub's `on` key instead of YAML 1.1's boolean True.
    return yaml.load((WORKFLOWS / name).read_text(), Loader=yaml.BaseLoader)


def test_daily_scan_includes_weekends_and_uses_full_scope():
    config = workflow("monitor.yml")
    assert config["on"]["schedule"] == [{"cron": "17 6 * * *", "timezone": "Europe/Warsaw"}]
    scan = config["jobs"]["scan"]
    command = next(step for step in scan["steps"] if "SCAN_SCOPE" in step.get("env", {}))
    assert "github.event_name == 'schedule' && 'full'" in command["env"]["SCAN_SCOPE"]


def test_report_publication_does_not_wait_for_pages_environment_approval():
    for name, job in [("monitor.yml", "scan"), ("rebuild-report.yml", "rebuild")]:
        config = workflow(name)
        producer = config["jobs"][job]
        assert "environment" not in producer
        assert config["permissions"] == {"contents": "write", "pages": "read"}
        deployment = config["jobs"]["pages"]
        assert deployment["needs"] == job
        assert "pages_enabled == 'true'" in deployment["if"]
        assert deployment["environment"]["name"] == "github-pages"
        assert any("upload-pages-artifact@" in step.get("uses", "") for step in producer["steps"])
        assert any("deploy-pages@" in step.get("uses", "") for step in deployment["steps"])


def test_automatic_report_rebuild_requires_successful_main_push_tests():
    config = workflow("rebuild-report.yml")
    assert "workflow_dispatch" in config["on"]
    event = config["on"]["workflow_run"]
    assert event["workflows"] == [workflow("tests.yml")["name"]]
    assert event["types"] == ["completed"] and event["branches"] == ["main"]
    gate = config["jobs"]["rebuild"]["if"]
    assert "conclusion == 'success'" in gate
    assert "event == 'push'" in gate
    assert "head_repository.full_name == github.repository" in gate
    assert "!contains(github.event.workflow_run.head_commit.message, '[scan]')" in gate


def test_opt_in_baseline_scan_is_test_gated_and_pages_cannot_lock_report_writers():
    monitor = workflow("monitor.yml")
    gate = monitor["jobs"]["scan"]["if"]
    assert "conclusion == 'success'" in gate and "event == 'push'" in gate
    assert "head_repository.full_name == github.repository" in gate
    assert "contains(github.event.workflow_run.head_commit.message, '[scan]')" in gate
    for name, job in [("monitor.yml", "scan"), ("rebuild-report.yml", "rebuild")]:
        config = workflow(name)
        assert "concurrency" not in config
        assert config["jobs"][job]["concurrency"]["group"] == "pracownie-monitor"
        assert config["jobs"]["pages"]["concurrency"]["group"] == "pracownie-pages"
        checkout = next(s for s in config["jobs"][job]["steps"] if s.get("uses", "").startswith("actions/checkout@"))
        assert checkout["with"]["ref"] == "${{ github.event.workflow_run.head_sha || github.sha }}"
    scan = monitor["jobs"]["scan"]
    deployment = next(s for s in scan["steps"] if s.get("id") == "deployment")
    assert "repair_domains=" in deployment["run"] and "[repair:" in deployment["run"]
    command = next(s for s in scan["steps"] if "REPAIR_DOMAINS" in s.get("env", {}))
    assert "steps.deployment.outputs.repair_domains" in command["env"]["REPAIR_DOMAINS"]

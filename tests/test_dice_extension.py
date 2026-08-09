import json
from pathlib import Path


def test_manifest_loads_dice_reader_without_generic_panel_collision():
    manifest = json.loads(Path("extension/public/manifest.json").read_text(encoding="utf-8"))
    dice_reader = next(
        item for item in manifest["content_scripts"]
        if "dice-content-script.js" in item.get("js", [])
    )
    panel_host = next(
        item for item in manifest["content_scripts"]
        if "panel-host.js" in item.get("js", [])
    )

    assert "https://www.dice.com/*" in dice_reader["matches"]
    assert "https://www.dice.com/*" in panel_host["exclude_matches"]


def test_dice_reader_emits_complete_source_context_and_clears_stale_jobs():
    source = Path("extension/public/dice-content-script.js").read_text(encoding="utf-8")

    assert 'source: "dice"' in source
    assert "/job-detail/" in source
    assert 'get("selectedJobId")' in source
    assert 'querySelectorAll("aside h1, main h1")' in source
    assert 'type: "JOB_CONTEXT"' in source
    assert 'type: "JOB_CONTEXT_CLEARED"' in source
    assert "structuredJob()" in source
    assert "descriptionFromHeading(titleElement)" in source


def test_shared_panel_and_worker_are_source_aware():
    worker = Path("extension/public/service-worker.js").read_text(encoding="utf-8")
    panel = Path("extension/src/panel-main.jsx").read_text(encoding="utf-8")

    assert "OPEN_SOURCE_JOB" in worker
    assert "dice-content-script.js" in worker
    assert "jobContext:${tabId}" in worker
    assert "sourceLabel(item)" in panel
    assert "LinkedIn or Dice job" in panel

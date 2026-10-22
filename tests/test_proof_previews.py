import json

import httpx
from PIL import Image
from test_github import FakeGitHub, prepare

from pracownie.github import GitHubStore, proof_preview_pairs, write_proof_preview
from pracownie.model import Change, Result
from pracownie.report import bundle_report, write_outputs
from pracownie.state import StateStore


def event(domain="studio.pl", page="glowna", **values):
    return {"domain": domain, "page": page, "daily": True, "category": "komunikacja",
            "evidence": {"przed": "before.png", "po": "after.png"}, **values}


def test_preview_pair_prioritizes_business_and_includes_visual_only_pages():
    sales = event(evidence={"przed": "before.png", "po": "after.png",
                            "fragment_przed": "crop-before.png", "fragment_po": "crop-after.png"})
    visual = event("galeriadomow.pl", category="obraz")
    duplicate = event(category="obraz")
    pairs = proof_preview_pairs([sales], [duplicate, visual])
    assert [(p["domain"], p["page"]) for p in pairs] == [("studio.pl", "glowna"), ("galeriadomow.pl", "glowna")]
    assert pairs[0]["before"] == "crop-before.png" and pairs[0]["after"] == "crop-after.png"
    assert pairs[1]["before"] == "before.png" and pairs[1]["after"] == "after.png"


def test_preview_pairs_do_not_publish_half_pairs_or_older_comparisons():
    entries = [event(evidence={"po": "today.png"}), event("old.pl", daily=False),
               event(evidence={"przed": "before.png", "po": "after.png", "fragment_po": "crop-after.png"}),
               event(page="projekt"), event("third.pl")]
    pairs = proof_preview_pairs(entries, [], limit=2)
    assert len(pairs) == 2
    assert pairs[0]["before"] == "before.png" and pairs[0]["after"] == "after.png"
    assert pairs[1]["page"] == "projekt"
    assert proof_preview_pairs(entries, [], limit=0) == []


def test_preview_resize_preserves_full_frame_aspect_ratio_and_original(tmp_path):
    source, target = tmp_path / "source.png", tmp_path / "preview.jpg"
    image = Image.new("RGB", (2000, 3000), "white")
    image.paste("red", (0, 0, 2000, 200))
    image.paste("blue", (0, 2800, 2000, 3000))
    image.save(source)
    original = source.read_bytes()
    write_proof_preview(source, target)
    assert source.read_bytes() == original
    with Image.open(target) as result:
        assert result.format == "JPEG" and result.size == (1000, 1500)
        assert result.getpixel((500, 50))[0] > 240
        assert result.getpixel((500, 1450))[2] > 240


def test_very_tall_preview_fits_jpeg_encoder_without_cropping(tmp_path):
    source, target = tmp_path / "long.png", tmp_path / "preview.jpg"
    Image.new("RGB", (20, 70000), "white").save(source)
    write_proof_preview(source, target)
    with Image.open(target) as result:
        assert result.height <= 65000 and result.width <= 20


def test_publication_reuses_the_same_original_path_for_multiple_pages(tmp_path):
    fake = FakeGitHub()
    remote = GitHubStore("test/monitor", "not-a-real-token", client=httpx.Client(transport=httpx.MockTransport(fake.request)))
    store, output = StateStore(tmp_path / "state"), tmp_path / "reports"
    day, run = "2026-10-22", "2026-10-22T060000-test"
    prepare(store, output, day, run)
    paths = {"przed": day + "/shared-before.png", "po": day + "/shared-after.png"}
    Image.new("RGB", (20, 20), "red").save(output / paths["przed"])
    Image.new("RGB", (20, 20), "blue").save(output / paths["po"])
    before, after = "2026-10-21T06:00:00+00:00", "2026-10-22T06:00:00+00:00"
    results = []
    for domain in ["first.pl", "second.pl"]:
        change = Change("changed", "promocje", "Rabat", "Rabat 10%", "Rabat 20%", before, after, "https://" + domain, "podstawowy")
        results.append(Result(domain, "glowna", "podstawowy", "changed", "https://" + domain, [change],
                              observed_at=after, compared_at=before, data_quality="ok", evidence=paths))
    write_outputs(output, day, results, {"run_id": run, "started_at": after, "finished_at": after, "elapsed_seconds": 0}, {}, ["first.pl", "second.pl"])
    view = json.loads((output / day / "oferty.json").read_text())
    assert len(proof_preview_pairs(view["management"]["items"], view["journal"])) == 2
    archive = output / "report.zip"
    bundle_report(output, day, archive)
    remote.publish(store, output, day, archive, run)
    previews = [a for a in fake.assets.values() if "-dowod-" in a["name"]]
    assert len(previews) == 2
    assert {a["name"].rsplit("-", 1)[-1] for a in previews} == {"przed.jpg", "po.jpg"}

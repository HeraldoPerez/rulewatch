import json
from datetime import date, datetime, timezone

import httpx
import pytest

from rulewatch.fetch import EXIT_BAD_CONFIG, EXIT_FETCH_FAILED, EXIT_OK, main

TODAY = date(2026, 11, 9)
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

CONFIG = """\
- name: small-business-labor
  agencies: [labor-department]
  types: [RULE]

- name: epa-proposed-rules
  agencies: [environmental-protection-agency]
  types: [PRORULE]
"""


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "watches.yml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


@pytest.fixture
def api(load_fixture, labor_pages):
    """Serves Labor results (two pages) or EPA results (one page), by agency."""

    def handler(request):
        agencies = request.url.params.get_list("conditions[agencies][]")
        if "environmental-protection-agency" in agencies:
            return httpx.Response(200, json=dict(load_fixture("epa_proposed_rules"), next_page_url=None))
        return labor_pages(request)

    return handler


def run(config, out, client, *extra):
    return main(
        ["--config", str(config), "--out", str(out), *extra], client=client, today=TODAY, now=NOW
    )


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_writes_one_file_per_watch(tmp_path, config, api, make_client, capsys):
    client, _ = make_client(api)
    out = tmp_path / "data"

    assert run(config, out, client) == EXIT_OK

    assert sorted(p.name for p in out.iterdir()) == [
        "epa-proposed-rules.json",
        "small-business-labor.json",
    ]

    labor = read(out / "small-business-labor.json")
    assert labor["watch"] == {
        "name": "small-business-labor",
        "agencies": ["labor-department"],
        "keywords": [],
        "types": ["RULE"],
    }
    assert labor["fetched_at"] == "2026-11-09T12:00:00+00:00"
    assert labor["since"] == "2026-10-10"
    assert labor["total"] == 3
    assert labor["complete"] is True
    assert [d["document_number"] for d in labor["documents"]] == [
        "2026-22761",
        "2026-22680",
        "2026-22306",
    ]

    epa = read(out / "epa-proposed-rules.json")
    assert [d["comments_close_on"] for d in epa["documents"]] == ["2026-12-07", "2026-12-07"]

    stdout = capsys.readouterr().out
    assert "small-business-labor: 3 documents, 0 with comment periods still open" in stdout
    assert "epa-proposed-rules: 2 documents, 2 with comment periods still open" in stdout


def test_days_sets_the_start_date(tmp_path, config, api, make_client):
    client, requests = make_client(api)

    run(config, tmp_path / "data", client, "--days", "7")

    assert requests[0].url.params["conditions[publication_date][gte]"] == "2026-11-02"


def test_bad_config_stops_before_fetching(tmp_path, make_client, capsys):
    config = tmp_path / "watches.yml"
    config.write_text("- name: a\n  agencies: [labor-department]\n  types: [RULES]\n", encoding="utf-8")
    client, requests = make_client(lambda request: httpx.Response(500))

    assert run(config, tmp_path / "data", client) == EXIT_BAD_CONFIG

    assert "unknown type 'RULES'" in capsys.readouterr().err
    assert requests == []
    assert not (tmp_path / "data").exists()


def test_one_failing_watch_does_not_stop_the_others(
    tmp_path, config, api, make_client, load_fixture, capsys
):
    def handler(request):
        if "labor-department" in request.url.params.get_list("conditions[agencies][]"):
            return httpx.Response(400, json=load_fixture("error_bad_agency"))
        return api(request)

    client, _ = make_client(handler)
    out = tmp_path / "data"
    out.mkdir()
    (out / "small-business-labor.json").write_text('{"from": "yesterday"}', encoding="utf-8")

    assert run(config, out, client) == EXIT_FETCH_FAILED

    assert "small-business-labor: failed" in capsys.readouterr().err
    # The previous run's file is left alone, and the other watch still gets saved.
    assert read(out / "small-business-labor.json") == {"from": "yesterday"}
    assert len(read(out / "epa-proposed-rules.json")["documents"]) == 2
    assert not list(out.glob("*.tmp"))


def test_warns_when_results_were_cut_off(tmp_path, config, load_fixture, make_client, capsys):
    page = load_fixture("epa_proposed_rules")  # count 19, but only 2 per page
    client, _ = make_client(lambda request: httpx.Response(200, json=page), max_pages=1)

    run(config, tmp_path / "data", client)

    assert "only the newest 2 of 19 were saved" in capsys.readouterr().out
    assert read(tmp_path / "data" / "epa-proposed-rules.json")["complete"] is False


def test_days_must_be_positive(tmp_path, config, make_client):
    client, _ = make_client(lambda request: httpx.Response(500))

    with pytest.raises(SystemExit) as caught:
        run(config, tmp_path / "data", client, "--days", "0")

    assert caught.value.code == 2

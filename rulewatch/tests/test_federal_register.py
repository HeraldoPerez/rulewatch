import json
from datetime import date

import httpx
import pytest

from rulewatch.config import Watch
from rulewatch.federal_register import (
    FIELDS,
    USER_AGENT,
    Document,
    FederalRegisterError,
    build_params,
    build_term,
)

LABOR = Watch(name="labor", agencies=("labor-department",))
SINCE = date(2026, 11, 1)


# --- building the query ---------------------------------------------------------


def test_build_term_quotes_phrases_but_not_single_words():
    term = build_term(["small business", "overtime", "PFAS", "emission*", "e-filing"])

    assert term == '"small business" | overtime | PFAS | emission* | "e-filing"'


def test_build_term_without_keywords():
    assert build_term([]) is None


def test_build_params_includes_every_condition():
    watch = Watch(
        name="a",
        agencies=("labor-department", "treasury-department"),
        keywords=("small business",),
        types=("PRORULE", "RULE"),
    )

    params = build_params(watch, SINCE, until=date(2026, 11, 9), per_page=50)

    assert params[:4] == [
        ("per_page", "50"),
        ("order", "newest"),
        ("conditions[publication_date][gte]", "2026-11-01"),
        ("conditions[publication_date][lte]", "2026-11-09"),
    ]
    assert ("conditions[agencies][]", "labor-department") in params
    assert ("conditions[agencies][]", "treasury-department") in params
    assert ("conditions[type][]", "PRORULE") in params
    assert ("conditions[type][]", "RULE") in params
    assert ("conditions[term]", '"small business"') in params
    assert [v for k, v in params if k == "fields[]"] == list(FIELDS)


def test_build_params_leaves_out_unused_conditions():
    keys = {key for key, _ in build_params(LABOR, SINCE)}

    assert "conditions[term]" not in keys
    assert "conditions[type][]" not in keys
    assert "conditions[publication_date][lte]" not in keys


# --- reading documents ----------------------------------------------------------


def test_document_from_api(load_fixture):
    raw = load_fixture("epa_proposed_rules")["results"][0]

    doc = Document.from_api(raw)

    assert doc.document_number == "2026-22592"
    assert doc.type == "Proposed Rule"
    assert doc.publication_date == date(2026, 11, 5)
    assert doc.comments_close_on == date(2026, 12, 7)
    assert doc.effective_on is None
    assert doc.agencies == ("Environmental Protection Agency",)
    assert doc.docket_ids == ("EPA-R03-OAR-2026-1024", "FRL-12072-01-R3")
    assert doc.comment_url.startswith("http://www.regulations.gov/commenton/")


def test_sub_agency_with_only_a_raw_name(load_fixture):
    raw = load_fixture("labor_page1")["results"][0]

    doc = Document.from_api(raw)

    assert doc.agencies == ("Labor Department", "Office of the Secretary")
    assert doc.regulation_id_numbers == ("1290-AA36",)
    assert doc.comments_close_on is None
    assert doc.comment_url is None


def test_comments_open_until_the_end_of_the_closing_day():
    doc = Document(
        document_number="1",
        title="t",
        type="Proposed Rule",
        publication_date=date(2026, 11, 5),
        html_url="https://example.org",
        comments_close_on=date(2026, 12, 7),
    )

    assert doc.comments_open(date(2026, 12, 6))
    assert doc.comments_open(date(2026, 12, 7))
    assert not doc.comments_open(date(2026, 12, 8))


def test_no_comment_period_is_never_open(load_fixture):
    doc = Document.from_api(load_fixture("labor_page1")["results"][0])

    assert not doc.comments_open(date(2026, 11, 9))


def test_to_json_is_serializable(load_fixture):
    doc = Document.from_api(load_fixture("epa_proposed_rules")["results"][0])

    data = json.loads(json.dumps(doc.to_json()))

    assert data["publication_date"] == "2026-11-05"
    assert data["comments_close_on"] == "2026-12-07"
    assert data["effective_on"] is None
    assert data["docket_ids"] == ["EPA-R03-OAR-2026-1024", "FRL-12072-01-R3"]


# --- searching ------------------------------------------------------------------


def test_search_follows_every_page(make_client, labor_pages):
    client, requests = make_client(labor_pages, per_page=2)

    result = client.search(LABOR, SINCE)

    assert [d.document_number for d in result.documents] == [
        "2026-22761",
        "2026-22680",
        "2026-22306",
    ]
    assert result.total == 3
    assert result.complete
    assert len(requests) == 2
    first, second = requests
    assert first.url.params.get_list("conditions[agencies][]") == ["labor-department"]
    assert first.url.params["conditions[publication_date][gte]"] == "2026-11-01"
    assert first.url.params["per_page"] == "2"
    assert "search_after_cursor" in second.url.params
    assert all(r.headers["User-Agent"] == USER_AGENT for r in requests)


def test_search_stops_at_max_pages(make_client, load_fixture):
    page = load_fixture("epa_proposed_rules")  # has a next_page_url
    client, requests = make_client(lambda request: httpx.Response(200, json=page), max_pages=1)

    result = client.search(LABOR, SINCE)

    assert len(result.documents) == 2
    assert result.total == 19
    assert not result.complete
    assert len(requests) == 1


def test_search_with_no_results(make_client):
    # The API leaves out "results" when nothing matches.
    empty = {"description": "Documents matching 'zzqq'", "count": 0}
    client, _ = make_client(lambda request: httpx.Response(200, json=empty))

    result = client.search(LABOR, SINCE)

    assert result.documents == []
    assert result.total == 0
    assert result.complete


def test_search_drops_documents_repeated_across_pages(make_client, load_fixture):
    first = load_fixture("labor_page1")
    repeat = dict(first, next_page_url=None)

    def handler(request):
        return httpx.Response(200, json=repeat if "page" in request.url.params else first)

    client, _ = make_client(handler)

    result = client.search(LABOR, SINCE)

    assert [d.document_number for d in result.documents] == ["2026-22761", "2026-22680"]


# --- errors ---------------------------------------------------------------------


def test_bad_agency_slug(make_client, load_fixture):
    error = load_fixture("error_bad_agency")
    client, _ = make_client(lambda request: httpx.Response(400, json=error))

    with pytest.raises(FederalRegisterError, match="agencies: invalid value") as caught:
        client.search(Watch(name="a", agencies=("not-a-real-agency",)), SINCE)

    assert "check the agency slugs in watches.yml" in str(caught.value)


def test_400_without_details(make_client):
    client, _ = make_client(lambda request: httpx.Response(400, text=""))

    with pytest.raises(FederalRegisterError, match="no details given"):
        client.search(LABOR, SINCE)


def test_server_error(make_client):
    client, _ = make_client(lambda request: httpx.Response(503, text="Service Unavailable"))

    with pytest.raises(FederalRegisterError, match="HTTP 503"):
        client.search(LABOR, SINCE)


def test_network_error(make_client):
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    client, _ = make_client(handler)

    with pytest.raises(FederalRegisterError, match="couldn't reach the Federal Register API"):
        client.search(LABOR, SINCE)


def test_response_that_is_not_json(make_client):
    client, _ = make_client(lambda request: httpx.Response(200, text="<html>maintenance</html>"))

    with pytest.raises(FederalRegisterError, match="didn't return JSON"):
        client.search(LABOR, SINCE)


def test_document_missing_required_fields(make_client):
    broken = {"count": 1, "results": [{"title": "No number or date"}]}
    client, _ = make_client(lambda request: httpx.Response(200, json=broken))

    with pytest.raises(FederalRegisterError, match="couldn't read"):
        client.search(LABOR, SINCE)

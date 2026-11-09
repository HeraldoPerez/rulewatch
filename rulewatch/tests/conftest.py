"""Shared test helpers.

The tests never touch the network. Fixtures in tests/fixtures/ are real Federal
Register API responses, recorded in November 2026.
"""

import json
from pathlib import Path

import httpx
import pytest

from rulewatch.federal_register import FederalRegisterClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def load(name: str) -> dict:
        return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))

    return load


@pytest.fixture
def make_client():
    """Build a client whose requests go to `handler` instead of the network.

    Returns (client, requests), where `requests` fills up with every request made.
    """
    opened = []

    def make(handler, **kwargs):
        requests = []

        def record(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        http = httpx.Client(transport=httpx.MockTransport(record))
        opened.append(http)
        return FederalRegisterClient(http, **kwargs), requests

    yield make
    for http in opened:
        http.close()


@pytest.fixture
def labor_pages(load_fixture):
    """Handler that serves the two recorded pages of Labor Department results."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        return httpx.Response(200, json=load_fixture(f"labor_page{page}"))

    return handler

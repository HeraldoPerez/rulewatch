"""Client for the Federal Register documents API.

Docs: https://www.federalregister.gov/developers/documentation/api/v1
The API is free and needs no key.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import httpx

from .config import Watch

API_URL = "https://www.federalregister.gov/api/v1/documents.json"
USER_AGENT = "RuleWatch (https://github.com/Khalick/rulewatch)"

# Only ask for the fields we use, which keeps responses small.
FIELDS = (
    "document_number",
    "title",
    "type",
    "abstract",
    "publication_date",
    "comments_close_on",
    "effective_on",
    "html_url",
    "pdf_url",
    "comment_url",
    "agencies",
    "docket_ids",
    "regulation_id_numbers",
)

# A keyword that is one plain word (optionally ending in *) is sent as-is so
# the API can match other forms of it. Anything else is sent as a phrase.
PLAIN_WORD = re.compile(r"^\w+\*?$")


class FederalRegisterError(Exception):
    """The API couldn't be reached, rejected the search, or sent something unexpected."""


@dataclass(frozen=True)
class Document:
    document_number: str
    title: str
    type: str  # as the API spells it: "Rule", "Proposed Rule", "Notice", ...
    publication_date: date
    html_url: str
    abstract: str | None = None
    comments_close_on: date | None = None
    effective_on: date | None = None
    pdf_url: str | None = None
    comment_url: str | None = None
    agencies: tuple[str, ...] = ()
    docket_ids: tuple[str, ...] = ()
    regulation_id_numbers: tuple[str, ...] = ()

    @classmethod
    def from_api(cls, raw: dict) -> Document:
        return cls(
            document_number=raw["document_number"],
            title=raw["title"],
            type=raw["type"],
            publication_date=date.fromisoformat(raw["publication_date"]),
            html_url=raw["html_url"],
            abstract=raw.get("abstract"),
            comments_close_on=_optional_date(raw.get("comments_close_on")),
            effective_on=_optional_date(raw.get("effective_on")),
            pdf_url=raw.get("pdf_url"),
            comment_url=raw.get("comment_url"),
            agencies=tuple(_agency_names(raw.get("agencies") or ())),
            docket_ids=tuple(raw.get("docket_ids") or ()),
            regulation_id_numbers=tuple(raw.get("regulation_id_numbers") or ()),
        )

    def comments_open(self, today: date) -> bool:
        """True if the comment period hasn't closed yet (it closes at the end of the day)."""
        return self.comments_close_on is not None and self.comments_close_on >= today

    def to_json(self) -> dict:
        return {
            "document_number": self.document_number,
            "title": self.title,
            "type": self.type,
            "publication_date": self.publication_date.isoformat(),
            "html_url": self.html_url,
            "abstract": self.abstract,
            "comments_close_on": _iso(self.comments_close_on),
            "effective_on": _iso(self.effective_on),
            "pdf_url": self.pdf_url,
            "comment_url": self.comment_url,
            "agencies": list(self.agencies),
            "docket_ids": list(self.docket_ids),
            "regulation_id_numbers": list(self.regulation_id_numbers),
        }


@dataclass(frozen=True)
class SearchResult:
    documents: list[Document]
    total: int  # how many documents the API says match (it caps this at 10,000)
    complete: bool  # False if we stopped at max_pages before the last page


def build_term(keywords: Iterable[str]) -> str | None:
    """Combine keywords into one search term that matches any of them.

    In the API's search syntax a space means AND and "|" means OR.
    """
    parts = [k if PLAIN_WORD.match(k) else f'"{k}"' for k in keywords]
    return " | ".join(parts) or None


def build_params(
    watch: Watch, since: date, until: date | None = None, per_page: int = 100
) -> list[tuple[str, str]]:
    """Query string for the first page of a watch's search, newest first."""
    params = [
        ("per_page", str(per_page)),
        ("order", "newest"),
        ("conditions[publication_date][gte]", since.isoformat()),
    ]
    if until is not None:
        params.append(("conditions[publication_date][lte]", until.isoformat()))
    params += [("conditions[agencies][]", agency) for agency in watch.agencies]
    params += [("conditions[type][]", doc_type) for doc_type in watch.types]
    term = build_term(watch.keywords)
    if term:
        params.append(("conditions[term]", term))
    params += [("fields[]", field) for field in FIELDS]
    return params


class FederalRegisterClient:
    """Searches the Federal Register for a watch's documents.

    Pass your own httpx.Client to control timeouts, or to use a fake transport in tests.
    """

    def __init__(
        self, http: httpx.Client | None = None, *, per_page: int = 100, max_pages: int = 10
    ) -> None:
        self._owns_http = http is None
        self._http = http or httpx.Client(timeout=30.0, follow_redirects=True)
        self.per_page = per_page
        self.max_pages = max_pages

    def __enter__(self) -> FederalRegisterClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def search(self, watch: Watch, since: date, until: date | None = None) -> SearchResult:
        """All documents for a watch published on or after `since`, newest first."""
        url: str = API_URL
        params: list[tuple[str, str]] | None = build_params(watch, since, until, self.per_page)
        documents: list[Document] = []
        seen: set[str] = set()
        total = 0

        for _ in range(self.max_pages):
            data = self._get_json(url, params)
            total = int(data.get("count") or 0)
            for raw in data.get("results") or ():
                document = _parse_document(raw)
                if document.document_number not in seen:
                    seen.add(document.document_number)
                    documents.append(document)

            # next_page_url already carries every condition plus a paging cursor.
            next_url = data.get("next_page_url")
            if not next_url:
                return SearchResult(documents, total, complete=True)
            url, params = next_url, None

        return SearchResult(documents, total, complete=False)

    def _get_json(self, url: str, params: list[tuple[str, str]] | None) -> dict:
        try:
            response = self._http.get(url, params=params, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as exc:
            raise FederalRegisterError(f"couldn't reach the Federal Register API ({exc})") from exc

        if response.status_code == 400:
            raise FederalRegisterError(
                f"the Federal Register API rejected the search: {_describe_errors(response)}"
            )
        if response.is_error:
            raise FederalRegisterError(
                f"the Federal Register API returned HTTP {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise FederalRegisterError("the Federal Register API didn't return JSON") from exc
        if not isinstance(data, dict):
            raise FederalRegisterError("the Federal Register API returned an unexpected response")
        return data


def _parse_document(raw: object) -> Document:
    try:
        return Document.from_api(raw)  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as exc:
        raise FederalRegisterError(
            f"the Federal Register API returned a document we couldn't read ({exc!r})"
        ) from exc


def _describe_errors(response: httpx.Response) -> str:
    """Turn {"errors": {"agencies": "invalid value"}} into readable text."""
    try:
        errors = response.json().get("errors")
    except (ValueError, AttributeError):
        errors = None
    if not isinstance(errors, dict) or not errors:
        return response.text[:200] or "no details given"
    described = "; ".join(f"{key}: {value}" for key, value in errors.items())
    if "agencies" in errors:
        described += " (check the agency slugs in watches.yml)"
    return described


def _agency_names(agencies: Iterable[dict]) -> Iterable[str]:
    # Sub-agencies sometimes come back with only a raw_name, like "Office of the Secretary".
    for agency in agencies:
        name = agency.get("name") or agency.get("raw_name")
        if name:
            yield name


def _optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None

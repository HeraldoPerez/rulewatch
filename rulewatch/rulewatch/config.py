"""Load and check watches.yml.

A watch is a saved search: some agencies, some keywords, or both, plus an
optional list of document types. Every problem in the file is reported at
once, so you can fix them all in one go.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# Codes the Federal Register API accepts for conditions[type][].
# The API silently returns nothing for an unknown code, so we check them here.
DOCUMENT_TYPES = {
    "RULE": "Rule",
    "PRORULE": "Proposed Rule",
    "NOTICE": "Notice",
    "PRESDOCU": "Presidential Document",
}

ALLOWED_KEYS = {"name", "agencies", "keywords", "types"}

# Watch names become file names, and agency slugs look like "labor-department".
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# These characters have a meaning in the API's search syntax.
RESERVED_IN_KEYWORDS = ('"', "|")


class ConfigError(ValueError):
    """watches.yml is missing, isn't valid YAML, or describes an invalid watch."""


@dataclass(frozen=True)
class Watch:
    name: str
    agencies: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    types: tuple[str, ...] = ()

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "agencies": list(self.agencies),
            "keywords": list(self.keywords),
            "types": list(self.types),
        }


def load_watches(path: str | Path) -> list[Watch]:
    """Read and check a watches file."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{path}: file not found") from None
    except OSError as exc:
        raise ConfigError(f"{path}: couldn't read the file ({exc.strerror})") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: not valid YAML\n{exc}") from exc

    return parse_watches(data, source=str(path))


def parse_watches(data: object, source: str = "watches.yml") -> list[Watch]:
    """Check already-parsed YAML and turn it into watches."""
    if not isinstance(data, list) or not data:
        raise ConfigError(f"{source}: expected a list of watches, each starting with '- name:'")

    errors: list[str] = []
    watches: list[Watch] = []
    seen_names: set[str] = set()

    for index, item in enumerate(data, start=1):
        label = f"watch {index}"
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            label += f" ({item['name']})"

        problems: list[str] = []
        watch = _parse_watch(item, problems)
        if watch is not None and watch.name in seen_names:
            problems.append(f"the name '{watch.name}' is used more than once")

        if problems:
            errors.extend(f"{source}: {label}: {problem}" for problem in problems)
        elif watch is not None:
            seen_names.add(watch.name)
            watches.append(watch)

    if errors:
        raise ConfigError("\n".join(errors))
    return watches


def _parse_watch(item: object, problems: list[str]) -> Watch | None:
    if not isinstance(item, dict):
        problems.append("should be a mapping with name, agencies, keywords and types")
        return None

    unknown = sorted(str(key) for key in item if key not in ALLOWED_KEYS)
    if unknown:
        problems.append(
            f"unknown setting {', '.join(unknown)}; use {', '.join(sorted(ALLOWED_KEYS))}"
        )

    name = item.get("name")
    if not isinstance(name, str) or not name:
        problems.append("needs a name")
        name = ""
    elif not SLUG.match(name):
        problems.append(
            f"name '{name}' should use only lowercase letters, numbers and hyphens, "
            "like 'small-business-labor'"
        )

    agencies = _string_list(item.get("agencies"), "agencies", problems)
    for agency in agencies:
        if not SLUG.match(agency):
            problems.append(
                f"agency '{agency}' should be a Federal Register slug, like 'labor-department'"
            )

    keywords = tuple(k.strip() for k in _string_list(item.get("keywords"), "keywords", problems))
    for keyword in keywords:
        if not keyword:
            problems.append("has an empty keyword")
        elif any(ch in keyword for ch in RESERVED_IN_KEYWORDS):
            problems.append(f"keyword '{keyword}' can't contain \" or |")

    types = tuple(t.upper() for t in _string_list(item.get("types"), "types", problems))
    for doc_type in types:
        if doc_type not in DOCUMENT_TYPES:
            problems.append(
                f"unknown type '{doc_type}'; use one of {', '.join(sorted(DOCUMENT_TYPES))}"
            )

    if not agencies and not keywords:
        problems.append("needs at least one agency or keyword, or it would match everything")

    return Watch(name=name, agencies=agencies, keywords=keywords, types=types)


def _string_list(value: object, key: str, problems: list[str]) -> tuple[str, ...]:
    """Accept a list of strings, or a single string as a one-item list."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return tuple(value)
    problems.append(f"{key} should be a list of text values")
    return ()

from pathlib import Path

import pytest

from rulewatch.config import ConfigError, Watch, load_watches, parse_watches

REPO_ROOT = Path(__file__).parent.parent


def test_example_watches_file_is_valid():
    watches = load_watches(REPO_ROOT / "watches.yml")

    assert [w.name for w in watches] == ["small-business-labor", "epa-proposed-rules"]
    assert watches[0] == Watch(
        name="small-business-labor",
        agencies=("labor-department",),
        keywords=("small business", "overtime"),
        types=("PRORULE", "RULE"),
    )


def test_single_values_become_lists_and_types_are_uppercased():
    [watch] = parse_watches(
        [{"name": "osha", "agencies": "labor-department", "keywords": "heat", "types": "prorule"}]
    )

    assert watch.agencies == ("labor-department",)
    assert watch.keywords == ("heat",)
    assert watch.types == ("PRORULE",)


def test_keywords_are_trimmed():
    [watch] = parse_watches([{"name": "a", "keywords": ["  overtime ", "small business"]}])

    assert watch.keywords == ("overtime", "small business")


def test_types_are_optional():
    [watch] = parse_watches([{"name": "a", "agencies": ["labor-department"]}])

    assert watch.types == ()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"name": "a"}, "expected a list of watches"),
        ([], "expected a list of watches"),
        (None, "expected a list of watches"),
        (["just text"], "should be a mapping"),
        ([{"agencies": ["labor-department"]}], "needs a name"),
        ([{"name": "Small Business", "keywords": ["x"]}], "lowercase letters, numbers and hyphens"),
        ([{"name": "a", "keyword": ["x"]}], "unknown setting keyword"),
        ([{"name": "a"}], "needs at least one agency or keyword"),
        ([{"name": "a", "keywords": ["x"], "types": ["RULES"]}], "unknown type 'RULES'"),
        ([{"name": "a", "keywords": ['say "hi"']}], "can't contain"),
        ([{"name": "a", "keywords": ["this | that"]}], "can't contain"),
        ([{"name": "a", "keywords": ["   "]}], "empty keyword"),
        ([{"name": "a", "agencies": ["Labor Department"]}], "Federal Register slug"),
        ([{"name": "a", "agencies": [1, 2]}], "agencies should be a list of text values"),
        (
            [{"name": "a", "keywords": ["x"]}, {"name": "a", "keywords": ["y"]}],
            "the name 'a' is used more than once",
        ),
    ],
)
def test_invalid_watches_are_rejected(data, message):
    with pytest.raises(ConfigError, match=message):
        parse_watches(data)


def test_every_problem_is_reported_at_once():
    with pytest.raises(ConfigError) as caught:
        parse_watches(
            [
                {"name": "ok", "keywords": ["x"]},
                {"name": "Bad Name", "keywords": ["x"]},
                {"name": "b", "types": ["RULES"]},
            ]
        )

    lines = str(caught.value).splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("watches.yml: watch 2 (Bad Name): name")
    assert "watch 3 (b): unknown type 'RULES'" in lines[1]
    assert "watch 3 (b): needs at least one agency or keyword" in lines[2]


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="file not found"):
        load_watches(tmp_path / "nope.yml")


def test_invalid_yaml(tmp_path):
    path = tmp_path / "watches.yml"
    path.write_text("- name: a\n  agencies: [labor-department\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid YAML"):
        load_watches(path)


def test_watch_to_json():
    watch = Watch(name="a", agencies=("labor-department",), keywords=("heat",), types=("RULE",))

    assert watch.to_json() == {
        "name": "a",
        "agencies": ["labor-department"],
        "keywords": ["heat"],
        "types": ["RULE"],
    }

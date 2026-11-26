"""Intents that name the ISS carry a ``.required`` file in every locale.

A ``.required`` lists the words of which at least one must occur in the
request (OVOS-INTENT-2 4.5). ``who_iss`` and ``number_iss`` also hold
templates such as "who is in space right now", so they take no ``.required``.
"""
import json
from pathlib import Path

import pytest
from ovos_spec_tools import expand, utterance_contains

ROOT = Path(__file__).parent.parent
LOCALE_DIR = ROOT / "locale"
GOLDEN_DIR = Path(__file__).parent / "end2end"
REQUIRED_INTENTS = ("where_iss", "when_iss")
CASES = sorted((d.name, intent) for d in LOCALE_DIR.iterdir() if d.is_dir()
               for intent in REQUIRED_INTENTS if (d / f"{intent}.intent").exists())


def _lines(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _keywords(lang, intent):
    path = LOCALE_DIR / lang / f"{intent}.required"
    return _lines(path) if path.exists() else []


def test_every_locale_has_the_intents():
    assert {lang for lang, _ in CASES} == {d.name for d in LOCALE_DIR.iterdir() if d.is_dir()}
    assert len(CASES) == 2 * len(list(LOCALE_DIR.iterdir()))


@pytest.mark.parametrize("lang,intent", CASES)
def test_required_file_is_not_empty(lang, intent):
    assert _keywords(lang, intent), f"{lang}/{intent}.required is missing or empty"


@pytest.mark.parametrize("lang,intent", CASES)
def test_every_sample_holds_a_keyword(lang, intent):
    keywords = _keywords(lang, intent)
    vocabularies = {voc.stem: _lines(voc) for voc in (LOCALE_DIR / lang).glob("*.voc")}
    uncovered = [sample for line in _lines(LOCALE_DIR / lang / f"{intent}.intent")
                 for sample in expand(line, vocabularies)
                 if not utterance_contains(sample, keywords)]
    assert keywords and not uncovered, uncovered[:5]


@pytest.mark.parametrize("lang,intent", CASES)
def test_golden_positives_hold_a_keyword(lang, intent):
    keywords = _keywords(lang, intent)
    golden = GOLDEN_DIR / f"golden_utterances_{lang}.jsonl"
    rows = [json.loads(line) for line in golden.read_text(encoding="utf-8").splitlines() if line.strip()]
    utterances = [row["utterance"] for row in rows if row["intent_label"] == intent]
    missing = [u for u in utterances if not utterance_contains(u, keywords)]
    assert keywords and not missing, missing

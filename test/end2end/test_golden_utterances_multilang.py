"""Multilingual golden-utterance end-to-end coverage for
ovos-skill-iss-location.

Every locale under ``locale/`` gets its own
``golden_utterances_<lang>.jsonl``. Each row's utterance is a direct
mechanical expansion of that locale's own ``where_iss.intent`` /
``when_iss.intent`` / ``who_iss.intent`` / ``number_iss.intent``
padatious template: ``(a|b|c)`` word-choice groups are resolved to one
alternative, ``[optional]`` tokens (including an internal ``a|b``
choice) are kept or dropped. No translation, no drafted prose.

One ``MiniCroft`` is booted per locale (class-scoped, torn down after),
mirroring the other skills' multilang suites in this batch and
ovos-skill-date-time/test/end2end/test_intents_it_it.py on dev.

Run:
    uv run pytest test/end2end/test_golden_utterances_multilang.py -v
"""
import json
from pathlib import Path
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-iss-location.openvoiceos"

PIPELINE = [
    "ovos-adapt-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-medium",
    "ovos-adapt-pipeline-plugin-low",
]

END2END_DIR = Path(__file__).parent

LANGS = [
    "en-US", "ca-ES", "da-DK", "de-DE", "es-ES", "eu-ES", "fr-FR",
    "gl-ES", "it-IT", "kab", "nl-NL", "oc-FR", "pt-BR", "pt-PT",
    "sv-SE",
]

NEGATIVE_UTTERANCES = [
    ("what's the weather like today", "en-US", "ovos-skill-weather.openvoiceos"),
    ("tell me a joke", "en-US", "ovos-skill-icanhazdadjokes.openvoiceos"),
    ("what's my ip address", "en-US", "ovos-skill-ip.openvoiceos"),
]


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


def _expected_names(intent_label: str) -> set:
    base = intent_label[:-len(".intent")] if intent_label.endswith(".intent") else intent_label
    return {f"{SKILL_ID}:{base}", f"{SKILL_ID}:{intent_label}"}


def _matched_names(mc, text, lang, session_id):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(PIPELINE)
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc)
    capture.capture(utterance, timeout=30)
    return [m.data.get("intent_name") for m in capture.finish() if m.msg_type == "ovos.intent.matched"]


KNOWN_BUGS = {}


def _make_locale_test_case(lang):
    rows = _load_rows(lang)
    negatives = [n for n in NEGATIVE_UTTERANCES if n[1] == lang]

    class _LocaleGoldenCase(TestCase):
        LANG = lang

        @classmethod
        def setUpClass(cls):
            cls.minicroft = get_minicroft([SKILL_ID], max_wait=180, lang=lang)

        @classmethod
        def tearDownClass(cls):
            if getattr(cls, "minicroft", None):
                cls.minicroft.stop()

        def _check_row(self, row):
            expected = _expected_names(row["intent_label"])
            names = _matched_names(
                self.minicroft, row["utterance"], row["lang"],
                f"golden-{row['lang']}-{row['intent_label']}-{row['utterance']}",
            )
            matched = any(n in expected for n in names)
            bug_key = (row["lang"], row["utterance"])
            if bug_key in KNOWN_BUGS and not matched:
                self.skipTest(f"known-bug: {KNOWN_BUGS[bug_key]}")
            self.assertTrue(
                matched,
                f"[{row['lang']}] {row['utterance']!r}: expected one of "
                f"{sorted(expected)!r}, got {names!r}",
            )

        def _check_negative(self, text, source_skill):
            names = _matched_names(self.minicroft, text, lang, f"negative-{lang}-{text}")
            claimed = any((n or "").startswith(f"{SKILL_ID}:") for n in names)
            self.assertFalse(
                claimed, f"[{lang}] {text!r} was incorrectly claimed by {SKILL_ID}"
            )

    for i, row in enumerate(rows):
        def _test(self, row=row):
            self._check_row(row)
        _test.__name__ = f"test_golden_{i:03d}_{row['intent_label'].replace('.', '_')}"
        setattr(_LocaleGoldenCase, _test.__name__, _test)

    for i, (text, _lang, source_skill) in enumerate(negatives):
        def _neg_test(self, text=text, source_skill=source_skill):
            self._check_negative(text, source_skill)
        _neg_test.__name__ = f"test_negative_{i:03d}"
        setattr(_LocaleGoldenCase, _neg_test.__name__, _neg_test)

    _LocaleGoldenCase.__name__ = f"TestGolden_{lang.replace('-', '_')}"
    _LocaleGoldenCase.__qualname__ = _LocaleGoldenCase.__name__
    return _LocaleGoldenCase


for _lang in LANGS:
    _cls = _make_locale_test_case(_lang)
    globals()[_cls.__name__] = _cls
del _lang, _cls  # for-loop variables leak into module globals; without this
# deletion pytest also collects a spurious extra test class literally named
# "_cls" (bound to whichever locale ran last), which boots a second,
# redundant MiniCroft for that locale under a different collected name.

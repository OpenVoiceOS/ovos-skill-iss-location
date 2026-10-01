"""m2v-multilingual candidate-default gate for ovos-skill-iss-location (en-US).

Boots the skill under the candidate default engine -- the m2v multilingual
classifier (``OpenVoiceOS/ovos-m2v-intents-multi-128M-v5``) via ovoscope's
``get_m2v_minicroft`` -- and replays a representative slice of this skill's
own golden utterances (``golden_utterances.jsonl``). Padatious stays the
skill's deterministic floor (see ``test_golden_utterances.py``); this gate
validates the candidate model that may replace it as the shipping default.

``get_iss_data`` (three chained network calls: ISS position, astronaut
roster, reverse geocoding) is stubbed to a fixed answer so the effect
assertion checks the skill's own dialog rendering, not network
availability. ``when_iss.intent`` is out of scope here: it downloads a live
TLE file from celestrak.org and runs orbital-mechanics prediction, too slow
and too network-heavy for a routing/effect gate.

Each row asserts both routing (the classifier picks this skill's registered
intent id) and effect (the rendered ``speak`` text carries the stubbed
answer content, not the bare dialog name).

Run:
    uv run pytest test/end2end/test_m2v_gate.py -v
"""
from unittest.mock import patch

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_m2v_minicroft

SKILL_ID = "ovos-skill-iss-location.openvoiceos"
LANG = "en-US"

STUBBED_TOPONYM = "the Pacific Ocean"
STUBBED_LAT = "12.34"
STUBBED_LON = "-56.78"
STUBBED_ASTRONAUTS = [
    {"name": "Jasmin Moghbeli", "craft": "ISS"},
    {"name": "Andreas Mogensen", "craft": "ISS"},
]


def _stub_get_iss_data(self):
    return STUBBED_TOPONYM, STUBBED_LAT, STUBBED_LON, STUBBED_ASTRONAUTS


# One representative utterance per intent (excluding when_iss.intent), plus
# extra where_iss phrasings from the skill's own golden set.
ROWS = [
    {"utterance": "location of the space station", "intent_label": "where_iss"},
    {"utterance": "location of the ISS", "intent_label": "where_iss"},
    {"utterance": "location of the international space station", "intent_label": "where_iss"},
    {"utterance": "I S S aboard people", "intent_label": "who_iss"},
    {"utterance": "I S S aboard how many", "intent_label": "number_iss"},
]


@pytest.fixture(scope="module")
def minicroft():
    mc = get_m2v_minicroft(skill_ids=[SKILL_ID], lang=LANG)
    pipe = mc.intents.pipeline_plugins["ovos-m2v-pipeline"]
    pipe._ensure_model(background_ok=False)
    yield mc
    mc.stop()


def _capture(mc, text, session_id):
    session = Session(session_id)
    session.lang = LANG
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc)
    capture.capture(utterance, timeout=30)
    return capture.finish()


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", ROWS, ids=lambda r: r["utterance"])
def test_m2v_gate(minicroft, row):
    expected_intent = f"{SKILL_ID}:{row['intent_label']}"
    with patch(
        "ovos_skill_iss_location.ISSLocationSkill.get_iss_data",
        _stub_get_iss_data,
    ):
        messages = _capture(minicroft, row["utterance"], f"m2v-{row['utterance']}")

    matched = [m for m in messages if m.msg_type == "ovos.intent.matched"]
    assert matched, (
        f"{row['utterance']!r}: expected ovos.intent.matched, got "
        f"{[m.msg_type for m in messages]!r}"
    )
    names = [m.data.get("intent_name") for m in matched]
    assert expected_intent in names, (
        f"{row['utterance']!r}: expected intent_name {expected_intent!r}, got {names!r}"
    )

    speaks = [m for m in messages if m.msg_type in ("speak", "ovos.utterance.speak")]
    assert speaks, f"{row['utterance']!r}: no speak message captured"
    spoken = speaks[0].data.get("utterance", "")
    assert spoken, f"{row['utterance']!r}: empty spoken text"

    if row["intent_label"] == "where_iss":
        assert "pacific" in spoken.lower(), (
            f"{row['utterance']!r}: stubbed toponym did not reach speech: {spoken!r}"
        )
    elif row["intent_label"] == "who_iss":
        assert "moghbeli" in spoken.lower(), (
            f"{row['utterance']!r}: stubbed astronaut name did not reach speech: {spoken!r}"
        )
    elif row["intent_label"] == "number_iss":
        assert "2" in spoken or "two" in spoken.lower(), (
            f"{row['utterance']!r}: stubbed astronaut count did not reach speech: {spoken!r}"
        )

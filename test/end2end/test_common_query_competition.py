"""Two-skill-competitor end-to-end regression test.

Live ser9 deployment found that "who is on board the space station" and
"how many people are in space" were claimed by common-query skills
(ddg/wolfram-style) instead of this skill's WhoISSIntent/NumberISSIntent,
because those two intents were plain Adapt (``IntentBuilder(...).require(...)``)
and either never reached adapt-high confidence or, for phrasings missing
the "onboard" keyword outright, never matched Adapt at all -- falling
through to common_query, which sits below padatious-high/adapt-high but
above adapt-medium/low in the default pipeline.

This suite boots a full pipeline (stop, padatious/padacioso, adapt,
common_query, fallback) alongside a synthetic "greedy" common-query
competitor that answers every question with high confidence (standing in
for ddg/wolfram without depending on live network access), and asserts
this skill's intents win outright -- the competitor is never even queried,
because the skill's own intent already claimed the utterance at a pipeline
tier above common_query.

Run: pytest test/end2end/test_common_query_competition.py -v
"""
import time
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-iss-location.openvoiceos"
LANG = "en-US"

# Mirrors ovos-core's shipped default pipeline (stop/converse/ocp/padatious/
# adapt-high/fallback-high/adapt-medium/fallback-medium/fallback-low) with
# common_query inserted where OVOS installers put it in production: above
# adapt-medium, below adapt-high/padatious-high. This is the exact ordering
# the live ser9 theft was reproduced against; per the incident report,
# pipeline ordering itself is not touched.
FULL_PIPELINE = [
    "ovos-stop-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-high",
    "ovos-common-query-pipeline-plugin",
    "ovos-adapt-pipeline-plugin-medium",
    "ovos-fallback-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-low",
    "ovos-fallback-pipeline-plugin-low",
]


class _GreedyCommonQueryCompetitor:
    """A minimal stand-in for a ddg/wolfram-style CommonQuery skill.

    Registers itself with the CommonQAService pipeline exactly like a real
    CommonQuerySkill does (an ``ovos.common_query.pong`` announcement), then
    answers every ``question:query`` with a high-confidence canned reply.
    No network access, no real skill class needed -- this is the minimum
    surface CommonQAService actually depends on (see ovos_commonqa.opm).
    """
    SKILL_ID = "test-greedy-common-query.openvoiceos"

    def __init__(self, bus):
        self.bus = bus
        self.queried = []
        bus.on("question:query", self._answer)
        bus.emit(Message("ovos.common_query.pong", {
            "skill_id": self.SKILL_ID,
            "is_classic_cq": False,
        }))

    def _answer(self, message):
        self.queried.append(message.data.get("phrase"))
        phrase = message.data.get("phrase", "")
        # ``question:query`` is a dispatch topic (it contains ``:``), so it
        # has no ``.response`` shorthand counterpart (OVOS-MSG-1 §5.3): the
        # answering component names the answering topic explicitly and
        # derives via ``reply`` instead. ``reply`` still performs the same
        # §5.2 source/destination reversal that ``response`` builds on.
        self.bus.emit(message.reply("question:query.response", {
            "phrase": phrase,
            "skill_id": self.SKILL_ID,
            "answer": f"here is a generic answer about {phrase}",
            "conf": 0.85,
        }))

    def detach(self):
        self.bus.remove("question:query", self._answer)


class TestCommonQueryCompetition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID], max_wait=120)
        cls.competitor = _GreedyCommonQueryCompetitor(cls.minicroft.bus)
        # let the pong registration land before any query is fired
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.competitor.detach()
        cls.minicroft.stop()

    def _run(self, text, session_id):
        session = Session(session_id)
        session.lang = LANG
        session.pipeline = list(FULL_PIPELINE)
        session.blacklisted_intents = []
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": [text], "lang": LANG},
            {"session": session.serialize(), "source": "A", "destination": "B"},
        )
        capture = CaptureSession(self.minicroft)
        capture.capture(utterance, timeout=30)
        return [m.msg_type for m in capture.finish()]

    def _assert_skill_wins(self, text, intent, session_id):
        before = len(self.competitor.queried)
        types = self._run(text, session_id)
        claimed_by_skill = any(
            t.startswith(f"{SKILL_ID}:") for t in types
        )
        claimed_by_competitor = any(
            t.startswith("question:query") for t in types
        )
        self.assertTrue(
            claimed_by_skill,
            f"{text!r} was not claimed by {SKILL_ID} (got {types!r})",
        )
        self.assertFalse(
            claimed_by_competitor or len(self.competitor.queried) > before,
            f"{text!r} was stolen by the common-query competitor before "
            f"{SKILL_ID}'s own intent could claim it (got {types!r})",
        )

    def test_who_is_on_board_not_stolen_by_common_query(self):
        self._assert_skill_wins(
            "who is on board the space station", "who_iss", "cq-competition-who"
        )

    def test_how_many_people_in_space_not_stolen_by_common_query(self):
        self._assert_skill_wins(
            "how many people are in space", "number_iss", "cq-competition-number"
        )

    def test_where_is_iss_still_not_stolen_by_common_query(self):
        # Already known-good (padatious/padacioso), kept here as a control:
        # if this ever starts failing, the regression is pipeline-wide, not
        # specific to the two intents this suite targets.
        self._assert_skill_wins(
            "where is the ISS", "where_iss", "cq-competition-where"
        )


if __name__ == "__main__":
    unittest.main()

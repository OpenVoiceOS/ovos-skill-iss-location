"""End-to-end intent routing tests for the en-US locale.

Each canonical utterance is fired through a real MiniCroft and asserted to
route to the expected intent handler and produce a spoken response.

The skill normally fetches the live ISS position / astronaut list over the
network (api.open-notify.org), which is known to intermittently return an
empty response body -- this suite must not depend on that being up or
well-behaved. ``ISSLocationSkill.get_iss_data`` (the skill's single fetch
seam -- see __init__.py) is patched for the whole class: a canned
happy-path return value by default, overridden with a raised
``ISSDataUnavailable`` for the one API-failure-path test below. Assertions
then cover intent binding and dialog content deterministically, not "did a
real network call happen to succeed".
"""
import re
import unittest
from unittest.mock import patch

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_spec_tools import SpecMessage
from ovoscope import CaptureSession, get_minicroft

from ovos_skill_iss_location import ISSDataUnavailable

SKILL_ID = "ovos-skill-iss-location.openvoiceos"

# canned happy-path return value for get_iss_data(): (toponym, lat, lon, astronauts)
_FAKE_ISS_DATA = (
    "Testland",
    "10.0",
    "20.0",
    [
        {"name": "Test Naut", "craft": "ISS"},
        {"name": "Fixture Kelly", "craft": "ISS"},
        {"name": "Not On The ISS", "craft": "Tiangong"},
    ],
)


def _matches_intent(msg_type: str, skill_id: str, intent_file: str) -> bool:
    """Check whether ``msg_type`` is the matched-intent event for
    ``intent_file`` (eg. ``where_iss.intent``), tolerant of which pipeline
    plugin matched it.

    Different pipeline plugins (padatious vs padacioso) register intents
    under different normalizations of the ``.intent`` filename basename —
    observed variants include the basename with no extension and the
    basename with the extension kept. Rather than pin one wire format
    (which breaks the moment the matching plugin or its version changes),
    compare case-insensitively against the basename with the extension
    stripped from both sides.
    """
    prefix = f"{skill_id}:"
    if not msg_type.startswith(prefix):
        return False
    observed = msg_type[len(prefix):]
    observed_base = observed.rsplit(".", 1)[0] if observed.endswith(".intent") else observed
    expected_base = intent_file.rsplit(".", 1)[0]
    # normalize PascalCase/snake_case to a bare lowercase token for comparison
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    return norm(observed_base) == norm(expected_base)


class TestISSLocationIntentsEnUS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])
        # Stub the skill's one live-network fetch seam for the whole class:
        # happy-path canned data by default, overridden per-test (see
        # test_api_failure_speaks_gracefully) to exercise the failure path.
        # Patched on the already-loaded INSTANCE, not the class: patching
        # the class before MiniCroft instantiates the skill breaks
        # ovos-workshop's method introspection during skill load/intent
        # registration (it expects a real function, not a MagicMock, and
        # raises AttributeError('__name__')).
        skill = cls.minicroft.plugin_skills[SKILL_ID].instance
        cls._get_iss_data_patcher = patch.object(
            skill, "get_iss_data", return_value=_FAKE_ISS_DATA
        )
        cls._get_iss_data_mock = cls._get_iss_data_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._get_iss_data_patcher.stop()
        cls.minicroft.stop()

    def tearDown(self):
        # restore the happy-path default in case a test overrode it
        self._get_iss_data_mock.side_effect = None
        self._get_iss_data_mock.return_value = _FAKE_ISS_DATA

    def _run(self, text, session_id="test-session"):
        session = Session(session_id)
        session.pipeline = [
            "ovos-adapt-pipeline-plugin-high",
            "ovos-padatious-pipeline-plugin-high",
            "ovos-padacioso-pipeline-plugin-high",
            "ovos-adapt-pipeline-plugin-medium",
            "ovos-padacioso-pipeline-plugin-medium",
            "ovos-adapt-pipeline-plugin-low",
        ]
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": [text], "lang": "en-US"},
            {"session": session.serialize(), "source": "A", "destination": "B"},
        )
        capture = CaptureSession(self.minicroft)
        capture.capture(utterance, timeout=30)
        return capture.finish()

    def _assert_intent(self, text, intent, expected_dialog=None):
        messages = self._run(text)
        types = [m.msg_type for m in messages]
        self.assertTrue(
            any(_matches_intent(t, SKILL_ID, intent) for t in types),
            f"no message routed to {SKILL_ID}:{intent} ({types})",
        )
        self.assertIn(SpecMessage.SPEAK, types)
        speak_msgs = [m for m in messages if m.msg_type == SpecMessage.SPEAK]
        # A bare "speak was emitted" assertion is satisfied even when the
        # handler crashed: ovos-workshop's generic exception handler
        # catches it and speaks the "skill.error" dialog (data.utterance
        # == "skill.error", no data.meta.dialog), which trivially passes
        # `assertIn(SpecMessage.SPEAK, types)`. Assert the handler did NOT
        # fall back to that error path, and (where deterministic) that the
        # specific expected dialog fired.
        for m in speak_msgs:
            self.assertNotEqual(
                m.data.get("utterance"), "skill.error",
                f"{text!r} spoke the generic skill.error fallback dialog "
                f"instead of a real response: {m.data}",
            )
        if expected_dialog is not None:
            dialogs = [m.data.get("meta", {}).get("dialog") for m in speak_msgs]
            self.assertIn(
                expected_dialog, dialogs,
                f"{text!r}: expected dialog {expected_dialog!r} among {dialogs!r}",
            )

    def test_where_is_the_iss(self):
        # "location_current" vs "location_unknown" depends on the live
        # geonames reverse-geocode call (a separate, unstubbed fetch) --
        # only the not-skill.error assertion (from _assert_intent) is
        # pinned here.
        self._assert_intent("where is the space station", "where_iss.intent")

    def test_when_is_the_iss_overhead(self):
        self._assert_intent(
            "when is the space station going to be overhead", "when_iss.intent",
            expected_dialog="visible_for",
        )

    def test_who_is_onboard(self):
        self._assert_intent("who is on board the ISS", "who_iss.intent", expected_dialog="who")

    def test_how_many_onboard(self):
        self._assert_intent(
            "how many are on board the ISS", "number_iss.intent", expected_dialog="number"
        )

    def test_api_failure_speaks_gracefully(self):
        """Reproduces the live ser9 finding: api.open-notify.org
        intermittently returns an empty body, which used to raise a raw
        JSONDecodeError out of the handler -- caught by ovos-workshop's
        generic exception handler, which spoke the opaque "skill.error"
        fallback dialog instead of anything meaningful. This must now
        speak the skill's own "api_unavailable" dialog instead, and must
        NOT hit the generic error path (no skill.error speak, no
        handler-error bus event).
        """
        self._get_iss_data_mock.side_effect = ISSDataUnavailable("simulated empty response body")
        messages = self._run("who is on board the ISS", session_id="test-session-api-failure")
        types = [m.msg_type for m in messages]
        speak_msgs = [m for m in messages if m.msg_type == SpecMessage.SPEAK]
        self.assertTrue(speak_msgs, f"no speak response for API failure ({types})")
        dialogs = [m.data.get("meta", {}).get("dialog") for m in speak_msgs]
        utterances = [m.data.get("utterance") for m in speak_msgs]
        self.assertIn(
            "api_unavailable", dialogs,
            f"expected the api_unavailable dialog, got dialogs={dialogs!r} utterances={utterances!r}",
        )
        self.assertNotIn("skill.error", utterances)
        self.assertFalse(
            any("handler.error" in t or "intent.handler.error" in t for t in types),
            f"handler-error event present for a handled API failure ({types})",
        )


if __name__ == "__main__":
    unittest.main()

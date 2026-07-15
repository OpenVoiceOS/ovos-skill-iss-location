"""End-to-end intent routing tests for the en-US locale.

Each canonical utterance is fired through a real MiniCroft and asserted to
route to the expected intent handler and produce a spoken response. The skill
normally fetches the live ISS position / astronaut list over the network, so
assertions cover the intent binding and the presence of a ``speak`` response,
not the dialog content.
"""
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-iss-location.openvoiceos"


class TestISSLocationIntentsEnUS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _run(self, text):
        session = Session("test-session")
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

    def _assert_intent(self, text, intent):
        messages = self._run(text)
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:{intent}", types)
        self.assertTrue(any("speak" in t for t in types))

    def test_where_is_the_iss(self):
        self._assert_intent("where is the space station", "where_iss.intent")

    def test_when_is_the_iss_overhead(self):
        self._assert_intent(
            "when is the space station going to be overhead", "when_iss.intent"
        )

    def test_who_is_onboard(self):
        self._assert_intent("who is on board the ISS", "WhoISSIntent")

    def test_how_many_onboard(self):
        self._assert_intent(
            "how many are on board the ISS", "NumberISSIntent"
        )


if __name__ == "__main__":
    unittest.main()

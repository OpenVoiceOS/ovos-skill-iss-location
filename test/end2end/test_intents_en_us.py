"""E2E intent-routing tests for ovos-skill-iss-location.

These tests validate intent routing only. The skill normally fetches the live
ISS position / astronaut list and does reverse geocoding; without a live
network the handler body may raise (emitting ``mycroft.skill.handler.error``
instead of ``...complete``). To stay deterministic and offline-safe the
assertions verify routing only: the pipeline reaches the skill's intent
activation point and the utterance is closed out via ``ovos.utterance.handled``.
Network/GUI/audio messages and the handler start/complete/error trio are
ignored so the outcome does not depend on a live API.

Run: pytest test/end2end/ -v
"""
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import End2EndTest, get_minicroft

SKILL_ID = "ovos-skill-iss-location.openvoiceos"
LANG = "en-US"

# messages that depend on live network / GUI / audio (or whose presence depends
# on whether the network-backed handler completed or raised) and are not
# relevant to intent routing; ignored so the tests pass offline
IGNORE = [
    "speak",
    "ovos.utterance.speak",
    "recognizer_loop:audio_output_start",
    "recognizer_loop:audio_output_end",
    "mycroft.audio.play_sound",
    "enclosure.mouth.text",
    "gui.value.set",
    "gui.page.show",
    "gui.page_interaction",
    "gui.clear.namespace",
    "mycroft.gui.screen.close",
    "mycroft.skills.abort_question",
    "ovos.skills.converse.force_timeout",
    "mycroft.audio.speech.stop",
    # handler outcome varies with network availability -> ignore the trio
    "mycroft.skill.handler.start",
    "mycroft.skill.handler.complete",
    "mycroft.skill.handler.error",
]


class _IntentRoutingMixin:
    """Shared MiniCroft setup."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _assert_padacioso(self, utterance: str, intent_file: str):
        intent_msg_type = f"{SKILL_ID}:{intent_file}"
        session = Session(f"e2e-en_us-{intent_file}-{hash(utterance)}")
        session.lang = LANG
        session.pipeline = ["ovos-padacioso-pipeline-plugin-medium"]
        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": LANG},
            {"session": session.serialize()},
        )
        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[SKILL_ID],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            source_message=message,
            activation_points=[intent_msg_type],
            test_msg_context=False,
            test_message_number=False,
            ignore_messages=IGNORE,
            expected_messages=[
                message,
                Message(f"{SKILL_ID}.activate", {}, {"skill_id": SKILL_ID}),
                Message(intent_msg_type, {}, {"skill_id": SKILL_ID}),
                Message("ovos.utterance.handled", {}, {"skill_id": SKILL_ID}),
            ],
        )
        test.execute(timeout=60)

    def _assert_adapt(self, utterance: str, intent_label: str):
        intent_msg_type = f"{SKILL_ID}:{intent_label}"
        session = Session(f"e2e-en_us-adapt-{hash(utterance)}")
        session.lang = LANG
        session.pipeline = [
            "ovos-adapt-pipeline-plugin-high",
            "ovos-adapt-pipeline-plugin-medium",
            "ovos-adapt-pipeline-plugin-low",
        ]
        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": LANG},
            {"session": session.serialize()},
        )
        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[SKILL_ID],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            source_message=message,
            activation_points=[intent_msg_type],
            test_msg_context=False,
            test_message_number=False,
            ignore_messages=IGNORE,
            expected_messages=[
                message,
                Message(f"{SKILL_ID}.activate", {}, {"skill_id": SKILL_ID}),
                Message(intent_msg_type, {}, {"skill_id": SKILL_ID}),
                Message("ovos.utterance.handled", {}, {"skill_id": SKILL_ID}),
            ],
        )
        test.execute(timeout=60)


class TestPadacioso1_Where_iss_intent(_IntentRoutingMixin, TestCase):
    """Padacioso intent: where_iss.intent"""

    def test_where_is_the_iss(self):
        self._assert_padacioso(r"where is the ISS", r"where_iss.intent")

    def test_location_of_the_international_space_station(self):
        self._assert_padacioso(r"location of the international space station", r"where_iss.intent")

    def test_tell_me_the_space_station_location(self):
        self._assert_padacioso(r"tell me the space station location", r"where_iss.intent")


class TestPadacioso2_When_iss_intent(_IntentRoutingMixin, TestCase):
    """Padacioso intent: when_iss.intent"""

    def test_when_is_the_iss_passing_over(self):
        self._assert_padacioso(r"when is the ISS passing over", r"when_iss.intent")

    def test_when_is_the_space_station_going_to_be_above(self):
        self._assert_padacioso(r"when is the space station going to be above", r"when_iss.intent")


class TestAdapt3_WhoISSIntent(_IntentRoutingMixin, TestCase):
    """Adapt intent: WhoISSIntent"""

    def test_who_is_on_board_the_iss(self):
        self._assert_adapt(r"who is on board the ISS", r"WhoISSIntent")


class TestAdapt4_NumberISSIntent(_IntentRoutingMixin, TestCase):
    """Adapt intent: NumberISSIntent"""

    def test_how_many_on_board_the_iss(self):
        self._assert_adapt(r"how many on board the ISS", r"NumberISSIntent")

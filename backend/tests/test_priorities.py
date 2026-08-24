import asyncio
import json

import pytest

from app.priorities import (
    FABIO_ACTION_LABEL,
    _enforce_priority_policy,
    _extract_json,
    _eli_agent_text,
    _is_fabio_item,
    _normalize_card,
    _parse_message,
    _rag_sync_ok,
    _synthesize,
    _validate_dashboard_shape,
)
from app.models import PriorityCard


# --- JSON recovery ---------------------------------------------------------

VALID = {"greeting": "Hi", "focus": "Focus", "cards": [{}]}


def test_extract_json_plain():
    assert _extract_json(json.dumps(VALID)) == VALID


def test_extract_json_with_surrounding_prose():
    text = "Here is the dashboard:\n" + json.dumps(VALID) + "\nLet me know if you need changes."
    assert _extract_json(text) == VALID


def test_extract_json_code_fenced():
    text = "```json\n" + json.dumps(VALID) + "\n```"
    assert _extract_json(text) == VALID


def test_extract_json_skips_broken_object_before_valid_one():
    text = "{not json at all} some words " + json.dumps(VALID)
    assert _extract_json(text) == VALID


def test_extract_json_nested_braces_and_trailing_text():
    payload = {"cards": [{"action": {"arguments": {"a": "{b}"}}}]}
    text = json.dumps(payload) + " trailing } garbage {"
    assert _extract_json(text) == payload


def test_extract_json_raises_without_json():
    with pytest.raises(ValueError):
        _extract_json("no structured output here")


class _Block:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Message:
    def __init__(self, blocks):
        self.content = blocks


def test_parse_message_prefers_tool_use_block():
    message = _Message([
        _Block(type="text", text="thinking aloud"),
        _Block(type="tool_use", input=VALID),
    ])
    assert _parse_message(message) == VALID


def test_parse_message_falls_back_to_text():
    message = _Message([_Block(type="text", text="prefix " + json.dumps(VALID))])
    assert _parse_message(message) == VALID


def test_dashboard_shape_safely_coerces_json_string_cards():
    parsed = {"greeting": "Hi", "focus": "Focus", "cards": json.dumps([_card()])}
    assert _validate_dashboard_shape(parsed)["cards"] == [_card()]


def test_dashboard_shape_unwraps_full_dashboard_inside_cards_string():
    nested = {"greeting": "Nested hello", "focus": "Nested focus", "cards": [_card()]}
    parsed = {"greeting": "", "focus": "", "cards": json.dumps(nested)}
    normalized = _validate_dashboard_shape(parsed)
    assert normalized["cards"] == [_card()]
    assert normalized["greeting"] == "Nested hello"
    assert normalized["focus"] == "Nested focus"


@pytest.mark.parametrize("cards", ["not-json", {}, ["not-an-object"], [], [{}] * 7])
def test_dashboard_shape_rejects_invalid_or_unbounded_cards(cards):
    with pytest.raises(ValueError):
        _validate_dashboard_shape({"greeting": "Hi", "focus": "Focus", "cards": cards})


class _FakeClient:
    """Returns queued messages; records how many API calls were made."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.messages = self

    async def create(self, **kwargs):
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_synthesize_recovers_with_one_bounded_retry():
    client = _FakeClient([
        _Message([_Block(type="text", text="Sorry, here you go: not-json {{{")]),
        _Message([_Block(type="text", text=json.dumps(VALID))]),
    ])
    result = asyncio.run(_synthesize(client, "test-model", "prompt"))
    assert result == VALID
    assert client.calls == 2


def test_synthesize_no_retry_when_first_attempt_is_valid():
    client = _FakeClient([_Message([_Block(type="tool_use", input=VALID)])])
    result = asyncio.run(_synthesize(client, "test-model", "prompt"))
    assert result == VALID
    assert client.calls == 1


def test_synthesize_fails_after_single_retry():
    client = _FakeClient([
        _Message([_Block(type="text", text="garbage")]),
        _Message([_Block(type="text", text="still garbage")]),
    ])
    with pytest.raises(ValueError):
        asyncio.run(_synthesize(client, "test-model", "prompt"))
    assert client.calls == 2


# --- Fabio routing ---------------------------------------------------------

def _card(**overrides):
    base = {
        "id": "x",
        "priority": "P1",
        "lane": "now",
        "category": "Personal",
        "title": "Call the school",
        "context": "Follow up on enrollment.",
        "consequence": "Missed deadline.",
        "source": "vault",
        "mission_alignment": "aligned",
        "action": {"label": "Ask Eli Agent to draft the call notes"},
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("title", [
    "Fix the website deployment outage",
    "Debug the Composio integration",
    "Troubleshooting the server",
    "Software upgrade for the practice portal",
    "IT ticket backlog review",
    "Technology stack decision",
])
def test_tech_items_route_to_fabio_as_delegate(title):
    normalized = _normalize_card(_card(title=title, lane="now"))
    assert normalized["lane"] == "delegate"
    assert normalized["action"]["label"] == FABIO_ACTION_LABEL
    assert normalized["action"]["kind"] == "eli_agent_queue"
    assert normalized["action"]["tool_name"] is None


def test_tech_item_in_monitor_lane_stays_monitor():
    normalized = _normalize_card(_card(title="Watch the DNS outage recovery", lane="monitor"))
    assert normalized["lane"] == "monitor"
    assert normalized["action"]["label"] == FABIO_ACTION_LABEL


def test_tech_detected_in_context_not_just_title():
    normalized = _normalize_card(_card(context="The API integration keeps failing during deployment.", lane="protect"))
    assert normalized["lane"] == "delegate"
    assert normalized["action"]["label"] == FABIO_ACTION_LABEL


def test_domain_registrar_item_routes_to_fabio():
    normalized = _normalize_card(_card(
        priority="P4",
        lane="monitor",
        title="Review the GoDaddy verification request",
        context="Confirm whether a domain registrar deadline applies.",
    ))
    assert normalized["lane"] == "monitor"
    assert normalized["action"]["label"] == FABIO_ACTION_LABEL


def test_routing_overrides_model_disagreement():
    card = _card(title="Personally debug the outage tonight", lane="now",
                 action={"label": "Dr. Shaye should SSH in and fix it"})
    normalized = _normalize_card(card)
    assert normalized["lane"] == "delegate"
    assert normalized["action"]["label"] == FABIO_ACTION_LABEL


def test_non_tech_card_is_untouched_by_routing():
    normalized = _normalize_card(_card())
    assert normalized["lane"] == "now"
    assert normalized["action"]["label"] == "Ask Eli Agent to draft the call notes"
    assert normalized["action"]["kind"] == "eli_agent_queue"


def test_priority_classes_map_to_their_canonical_action_lanes():
    assert _normalize_card(_card(priority="P1", lane="protect"))["lane"] == "now"
    assert _normalize_card(_card(priority="P3", lane="now"))["lane"] == "protect"
    assert _normalize_card(_card(priority="P4", lane="now"))["lane"] == "delegate"


def test_daily_selection_rule_caps_high_value_and_admin_and_omits_p5():
    cards = [
        PriorityCard.model_validate(_normalize_card(_card(id=f"high-{index}", priority=priority)))
        for index, priority in enumerate(["P3", "P2", "P1", "P0"])
    ]
    cards.extend(
        PriorityCard.model_validate(_normalize_card(_card(id=f"admin-{index}", priority="P4")))
        for index in range(4)
    )
    cards.append(PriorityCard.model_validate(_normalize_card(_card(id="someday", priority="P5"))))

    selected = _enforce_priority_policy(cards)

    assert [card.priority for card in selected] == ["P0", "P1", "P2", "P4", "P4", "P4"]
    assert all(card.id != "someday" for card in selected)


def test_lowercase_it_pronoun_does_not_trigger_routing():
    card = _card(title="Discuss it with the family", context="Talk it over at dinner.")
    assert not _is_fabio_item(card)
    assert _normalize_card(card)["lane"] == "now"


def test_uppercase_it_department_triggers_routing():
    assert _is_fabio_item(_card(title="Escalate the IT request"))


def test_legacy_agent_name_is_removed_from_all_visible_card_fields():
    normalized = _normalize_card(_card(
        category="Hermes Agent",
        title="Review HERMES update",
        context="Hermes prepared this.",
        consequence="Waiting on hermes agent.",
        source="Hermes vault",
        action={"label": "Ask Hermes to continue"},
    ))
    visible = " ".join(str(normalized[field]) for field in ("category", "title", "context", "consequence", "source"))
    visible += " " + normalized["action"]["label"]
    assert "hermes" not in visible.lower()
    assert "Eli Agent" in visible


@pytest.mark.parametrize("legacy", ["Hermes", "HERMES", "hermes agent", "Hermes Agent"])
def test_eli_agent_text_replaces_legacy_name(legacy):
    assert _eli_agent_text(f"Ask {legacy} now") == "Ask Eli Agent now"


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ("--- retrieval health ---\nRAG queries succeeded: 4/4", True),
        ("--- retrieval health ---\nRAG queries succeeded: 0/4", False),
        ("vault text without a retrieval marker", False),
    ],
)
def test_rag_sync_status_requires_a_successful_retrieval(context, expected):
    assert _rag_sync_ok(context) is expected

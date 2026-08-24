import pytest

from app.integrations import ComposioMCPClient


def test_gmail_write_contract_is_narrow_and_normalized():
    clean = ComposioMCPClient.validate_write(
        "GMAIL_SEND_EMAIL",
        {"recipient_email": "person@example.com", "subject": "Hello", "body": "Plain text", "is_html": True},
    )
    assert clean["user_id"] == "me"
    assert clean["is_html"] is False


def test_gmail_write_rejects_attachments_and_aliases():
    with pytest.raises(ValueError):
        ComposioMCPClient.validate_write(
            "GMAIL_SEND_EMAIL",
            {"recipient_email": "person@example.com", "subject": "Hello", "body": "Text", "attachment": {"s3key": "x"}},
        )


def test_unknown_tool_is_rejected():
    with pytest.raises(ValueError):
        ComposioMCPClient.validate_write("SLACK_SEND_MESSAGE", {"text": "hello"})


def test_calendar_event_becomes_safe_structured_metadata():
    item = ComposioMCPClient._calendar_item(
        {
            "id": "event-1",
            "summary": "Family dinner",
            "start": {"dateTime": "2026-08-24T18:30:00-07:00"},
            "end": {"dateTime": "2026-08-24T20:00:00-07:00"},
            "description": "This private description must never be copied.",
        }
    )

    assert item is not None
    assert item.title == "Family dinner"
    assert item.start == "2026-08-24T18:30:00-07:00"
    assert item.end == "2026-08-24T20:00:00-07:00"
    assert item.id == "event-1"
    assert "private description" not in item.model_dump_json()


def test_calendar_event_without_a_date_or_with_clinical_content_is_omitted():
    assert ComposioMCPClient._calendar_item({"summary": "Undated", "start": {}}) is None
    assert ComposioMCPClient._calendar_item({"summary": "Patient clinic visit", "start": {"date": "2026-08-25"}}) is None

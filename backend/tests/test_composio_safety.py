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

from backend.services.ai.redaction import redact_object, redact_text


def test_redaction_masks_api_keys_and_emails():
    text = "Token sk-1234567890 and email dylan.dog@example.com"
    redacted = redact_text(text)
    assert "sk-1234567890" not in redacted
    assert "d***@example.com" in redacted


def test_redaction_masks_nested_dict_values():
    payload = {
        "Authorization": "Bearer abcdefghijklmn",
        "user": {"email": "victor@example.com"},
    }
    redacted = redact_object(payload)
    assert "Bearer abcdefghijklmn" not in str(redacted)
    assert redacted["user"]["email"] == "v***@example.com"

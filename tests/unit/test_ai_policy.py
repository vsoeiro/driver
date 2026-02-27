from backend.services.ai.policy import PolicyEngine


def test_policy_blocks_excessive_tool_calls():
    policy = PolicyEngine(max_tool_calls=2)
    policy.enforce_tool_budget(2)

    try:
        policy.enforce_tool_budget(3)
    except Exception as exc:
        assert "Tool-call budget exceeded" in str(exc)
    else:
        raise AssertionError("Expected budget exception")


def test_policy_requires_confirmation_for_non_read_tools():
    policy = PolicyEngine(max_tool_calls=3)
    assert policy.require_confirmation_for_permission("read") is False
    assert policy.require_confirmation_for_permission("write") is True

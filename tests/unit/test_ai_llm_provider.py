from backend.services.ai.llm_provider import heuristic_answer, heuristic_plan


def test_heuristic_plan_small_talk_no_tools():
    plan = heuristic_plan("Ola, tudo bem?")
    assert plan.intent == "small_talk"
    assert plan.tool_calls == []
    assert plan.assistant_message


def test_heuristic_answer_items_search_human_readable():
    text = heuristic_answer(
        user_message="Oi",
        tool_summaries=[
            {
                "tool_name": "items.search",
                "arguments": {"q": "Oi"},
                "result": {
                    "total": 2,
                    "items": [
                        {"name": "Dylan Dog 01.cbz"},
                        {"name": "Dylan Dog 02.cbz"},
                    ],
                },
                "error": None,
            }
        ],
    )
    assert "Resultado resumido" not in text
    assert "Encontrei 2 item" in text

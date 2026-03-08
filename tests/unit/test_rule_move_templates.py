from types import SimpleNamespace

from backend.workers.handlers.rules import _render_template, _split_destination_template


def _file_item(extension: str = "cbz"):
    return SimpleNamespace(item_type="file", extension=extension)


def test_split_destination_template_uses_last_segment_as_filename():
    folders, final_name = _split_destination_template(
        template="{{SERIES}}/{{SERIES}} #{{ISSUE NUMBER}}",
        context={"SERIES": "Monstress", "ISSUE_NUMBER": "54"},
        item=_file_item(),
    )

    assert folders == ["Monstress"]
    assert final_name == "Monstress #54.cbz"


def test_split_destination_template_preserves_folder_only_templates_with_trailing_slash():
    folders, final_name = _split_destination_template(
        template="{{SERIES}}/",
        context={"SERIES": "Monstress"},
        item=_file_item(),
    )

    assert folders == ["Monstress"]
    assert final_name is None


def test_split_destination_template_does_not_duplicate_explicit_extension():
    folders, final_name = _split_destination_template(
        template="{{SERIES}} #{{ISSUE_NUMBER}}.{{EXT}}",
        context={"SERIES": "Monstress", "ISSUE_NUMBER": "54", "EXT": "cbz"},
        item=_file_item(),
    )

    assert folders == []
    assert final_name == "Monstress #54.cbz"


def test_render_template_supports_if_blocks_without_else():
    rendered = _render_template(
        "{{SERIES}}{{#if VOLUME}}/{{VOLUME}}{{/if}}/{{ISSUE_NUMBER}}",
        {"SERIES": "Monstress", "VOLUME": "3", "ISSUE_NUMBER": "54"},
    )

    assert rendered == "Monstress/3/54"


def test_render_template_supports_if_else_fallbacks():
    rendered = _render_template(
        "{{SERIES}}/{{#if VOLUME}}{{VOLUME}}{{else}}{{ISSUE_NUMBER}}{{/if}}",
        {"SERIES": "Monstress", "ISSUE_NUMBER": "54", "VOLUME": ""},
    )

    assert rendered == "Monstress/54"


def test_split_destination_template_supports_conditional_folder_segments():
    folders, final_name = _split_destination_template(
        template="{{SERIES}}{{#if VOLUME}}/{{VOLUME}}{{/if}}/{{#if ISSUE_NUMBER}}{{ISSUE_NUMBER}}{{else}}UNKNOWN{{/if}}",
        context={"SERIES": "Monstress", "VOLUME": "", "ISSUE_NUMBER": "54"},
        item=_file_item(),
    )

    assert folders == ["Monstress"]
    assert final_name == "54.cbz"

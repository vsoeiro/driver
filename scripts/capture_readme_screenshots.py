from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_URL = os.environ.get("DRIVER_SCREENSHOT_URL", "http://127.0.0.1:5173")
OUTPUT_DIR = REPO_ROOT / "docs" / "assets" / "screenshots"

ACCOUNTS = [
    {"id": "acc-1", "display_name": "Northwind Ops", "email": "ops@northwind.example", "provider": "onedrive"},
    {"id": "acc-2", "display_name": "Bluebird Studio", "email": "library@bluebird.example", "provider": "google_drive"},
]

CATEGORIES = [
    {
        "id": "cat-comics",
        "name": "Comics",
        "description": "Metadata tuned for comic archives and issue pipelines.",
        "attributes": [
            {"id": "attr-series", "name": "Series", "data_type": "text", "is_required": True, "plugin_field_key": "series_name"},
            {"id": "attr-issue", "name": "Issue", "data_type": "number", "is_required": True, "plugin_field_key": "issue_number"},
            {"id": "attr-volume", "name": "Volume", "data_type": "number", "is_required": False, "plugin_field_key": "volume"},
            {
                "id": "attr-status",
                "name": "Status",
                "data_type": "select",
                "options": {"options": ["Draft", "Ready", "Published"]},
                "is_required": False,
            },
        ],
    },
    {
        "id": "cat-images",
        "name": "Images",
        "description": "Vision-ready catalog for screenshots, covers, and scans.",
        "attributes": [
            {"id": "attr-scene", "name": "Scene", "data_type": "text", "is_required": False},
            {"id": "attr-people", "name": "Contains People", "data_type": "boolean", "is_required": False},
        ],
    },
    {
        "id": "cat-books",
        "name": "Books",
        "description": "Books metadata with author, language, and imprint fields.",
        "attributes": [
            {"id": "attr-author", "name": "Author", "data_type": "text", "is_required": True},
            {
                "id": "attr-language",
                "name": "Language",
                "data_type": "select",
                "options": {"options": ["English", "Portuguese", "Spanish"]},
                "is_required": False,
            },
        ],
    },
]

LIBRARIES = [
    {"key": "comics_core", "name": "Comics Core", "is_active": True, "description": "Comic extraction, cover indexing, and issue tracking."},
    {"key": "images_core", "name": "Images Core", "is_active": True, "description": "Image analysis, tagging, and duplicate discovery."},
    {"key": "books_core", "name": "Books Core", "is_active": True, "description": "Book indexing and metadata mapping."},
]

ALL_ITEMS = [
    {
        "id": "row-1",
        "item_id": "item-1",
        "account_id": "acc-1",
        "parent_id": None,
        "item_type": "folder",
        "name": "Comics",
        "size": 0,
        "modified_at": "2026-03-14T13:10:00Z",
        "created_at": "2026-03-10T10:00:00Z",
        "path": "/Comics",
        "metadata": None,
    },
    {
        "id": "row-2",
        "item_id": "item-2",
        "account_id": "acc-1",
        "parent_id": "item-1",
        "item_type": "file",
        "name": "Saga 001.cbz",
        "size": 51380234,
        "modified_at": "2026-03-14T13:12:00Z",
        "created_at": "2026-03-11T10:00:00Z",
        "path": "/Comics/Saga 001.cbz",
        "metadata": {"category_name": "Comics", "Series": "Saga", "Issue": 1, "Volume": 1, "Status": "Published"},
    },
    {
        "id": "row-3",
        "item_id": "item-3",
        "account_id": "acc-1",
        "parent_id": "item-1",
        "item_type": "file",
        "name": "Saga 002.cbz",
        "size": 52380234,
        "modified_at": "2026-03-14T13:15:00Z",
        "created_at": "2026-03-12T11:00:00Z",
        "path": "/Comics/Saga 002.cbz",
        "metadata": {"category_name": "Comics", "Series": "Saga", "Issue": 2, "Volume": 1, "Status": "Ready"},
    },
    {
        "id": "row-4",
        "item_id": "item-4",
        "account_id": "acc-2",
        "parent_id": None,
        "item_type": "file",
        "name": "Launch Poster.png",
        "size": 830234,
        "modified_at": "2026-03-13T21:00:00Z",
        "created_at": "2026-03-09T14:00:00Z",
        "path": "/Campaign/Launch Poster.png",
        "metadata": {"category_name": "Images", "Scene": "Product launch wall", "Contains People": False},
    },
    {
        "id": "row-5",
        "item_id": "item-5",
        "account_id": "acc-2",
        "parent_id": None,
        "item_type": "file",
        "name": "Design Systems Handbook.epub",
        "size": 7023401,
        "modified_at": "2026-03-12T16:40:00Z",
        "created_at": "2026-03-07T09:30:00Z",
        "path": "/Books/Design Systems Handbook.epub",
        "metadata": {"category_name": "Books", "Author": "A. Rivera", "Language": "English"},
    },
    {
        "id": "row-6",
        "item_id": "item-6",
        "account_id": "acc-1",
        "parent_id": None,
        "item_type": "file",
        "name": "Release Notes.pdf",
        "size": 1830241,
        "modified_at": "2026-03-11T08:45:00Z",
        "created_at": "2026-03-06T15:15:00Z",
        "path": "/Ops/Release Notes.pdf",
        "metadata": None,
    },
]

SIMILAR_REPORT = {
    "groups": [
        {
            "signature": "Saga issue duplicates",
            "items": [
                {"id": "item-2", "item_id": "item-2", "account_id": "acc-1", "name": "Saga 001.cbz", "path": "/Comics/Saga 001.cbz", "size": 51380234},
                {"id": "item-7", "item_id": "item-7", "account_id": "acc-2", "name": "Saga 001 copy.cbz", "path": "/Archive/Saga 001 copy.cbz", "size": 51380234},
            ],
        }
    ],
    "total_groups": 1,
    "total_items": 2,
    "total_pages": 1,
    "page": 1,
}

JOBS = [
    {
        "id": "job-1001",
        "type": "extract_library_comic_assets",
        "status": "RUNNING",
        "created_at": "2026-03-14T13:00:00Z",
        "started_at": "2026-03-14T13:01:00Z",
        "finished_at": None,
        "duration_seconds": 480,
        "retry_count": 0,
        "max_retries": 3,
        "progress_current": 420,
        "progress_total": 1200,
        "queue_position": None,
        "estimated_start_at": None,
        "estimated_wait_seconds": None,
        "payload": {"account_ids": ["acc-1", "acc-2"], "chunk_size": 200},
        "result": None,
        "metrics": {"total": 1200, "success": 408, "failed": 4, "skipped": 8},
    },
    {
        "id": "job-1002",
        "type": "apply_metadata_rule",
        "status": "COMPLETED",
        "created_at": "2026-03-14T12:20:00Z",
        "started_at": "2026-03-14T12:21:00Z",
        "finished_at": "2026-03-14T12:27:00Z",
        "duration_seconds": 362,
        "retry_count": 0,
        "max_retries": 3,
        "progress_current": 98,
        "progress_total": 98,
        "payload": {"rule_id": "rule-rename-saga"},
        "result": {"batch_id": "batch-204", "total": 98, "updated": 93, "skipped": 5},
        "metrics": {"total": 98, "success": 93, "failed": 0, "skipped": 5},
    },
    {
        "id": "job-1003",
        "type": "analyze_library_image_assets",
        "status": "RETRY_SCHEDULED",
        "created_at": "2026-03-14T11:50:00Z",
        "started_at": "2026-03-14T11:51:00Z",
        "finished_at": None,
        "duration_seconds": 120,
        "retry_count": 1,
        "max_retries": 3,
        "next_retry_at": "2026-03-14T13:20:00Z",
        "progress_current": 56,
        "progress_total": 300,
        "payload": {"account_ids": ["acc-2"], "reprocess": False},
        "result": None,
        "metrics": {"total": 300, "success": 54, "failed": 2, "skipped": 0},
    },
    {
        "id": "job-1004",
        "type": "reindex_comic_covers",
        "status": "DEAD_LETTER",
        "created_at": "2026-03-14T09:10:00Z",
        "started_at": "2026-03-14T09:11:00Z",
        "finished_at": "2026-03-14T09:22:00Z",
        "duration_seconds": 668,
        "retry_count": 3,
        "max_retries": 3,
        "dead_lettered_at": "2026-03-14T09:22:00Z",
        "dead_letter_reason": "Remote storage throttled after repeated retries.",
        "progress_current": 180,
        "progress_total": 600,
        "payload": {"library_key": "comics_core"},
        "result": None,
        "metrics": {"total": 600, "success": 175, "failed": 5, "skipped": 0},
    },
    {
        "id": "job-1005",
        "type": "remove_duplicate_files",
        "status": "PENDING",
        "created_at": "2026-03-14T13:08:00Z",
        "started_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "retry_count": 0,
        "max_retries": 2,
        "queue_position": 4,
        "estimated_start_at": "2026-03-14T13:18:00Z",
        "estimated_wait_seconds": 600,
        "progress_current": 0,
        "progress_total": 120,
        "payload": {"group_signature": "Saga issue duplicates"},
        "result": None,
        "metrics": {"total": 120, "success": 0, "failed": 0, "skipped": 0},
    },
]

ATTEMPTS_BY_JOB = {
    "job-1004": [
        {
            "id": "att-1",
            "attempt_number": 1,
            "status": "FAILED",
            "started_at": "2026-03-14T09:11:00Z",
            "completed_at": "2026-03-14T09:13:00Z",
            "duration_seconds": 120,
            "error": "HTTP 429 throttled",
        },
        {
            "id": "att-2",
            "attempt_number": 2,
            "status": "FAILED",
            "started_at": "2026-03-14T09:14:00Z",
            "completed_at": "2026-03-14T09:17:00Z",
            "duration_seconds": 180,
            "error": "HTTP 429 throttled",
        },
    ]
}

RULES = [
    {
        "id": "rule-rename-saga",
        "name": "Normalize Saga issue names",
        "description": "Applies comic metadata and standardized issue naming.",
        "target_category_id": "cat-comics",
        "target_values": {"attr-series": "Saga", "attr-volume": 1},
        "apply_metadata": True,
        "apply_remove_metadata": False,
        "apply_rename": True,
        "rename_template": "{{SERIES}} v{{VOLUME}} #{{ISSUE}}",
        "apply_move": False,
        "include_folders": False,
        "account_id": "acc-1",
        "metadata_filters": [{"source": "path", "operator": "contains", "value": "Saga"}],
        "destination_account_id": None,
        "destination_folder_id": "root",
        "destination_path_template": None,
        "path_prefix": None,
        "path_contains": "Saga",
    },
    {
        "id": "rule-posters",
        "name": "Flag launch campaign posters",
        "description": "Routes final campaign images to the published asset set.",
        "target_category_id": "cat-images",
        "target_values": {"attr-scene": "Launch campaign", "attr-people": False},
        "apply_metadata": True,
        "apply_remove_metadata": False,
        "apply_rename": False,
        "rename_template": None,
        "apply_move": False,
        "include_folders": False,
        "account_id": "acc-2",
        "metadata_filters": [{"source": "path", "operator": "contains", "value": "Poster"}],
        "destination_account_id": None,
        "destination_folder_id": "root",
        "destination_path_template": None,
        "path_prefix": None,
        "path_contains": "Poster",
    },
]

RUNTIME_SETTINGS = {
    "enable_daily_sync_scheduler": True,
    "daily_sync_cron": "0 2 * * *",
    "worker_job_timeout_seconds": 1800,
    "ai_model_default": "gpt-4.1-mini",
    "ai_provider_mode": "openai_compatible",
    "ai_base_url_remote": "https://api.example.ai/v1",
    "ai_api_key_remote": "sk-demo-masked",
    "plugin_settings": [
        {
            "plugin_key": "comics_core",
            "plugin_name": "Comics Core",
            "plugin_description": "Controls extraction, cover indexing, and archive policies.",
            "capabilities": {"supported_input_types": ["number", "text", "folder_target"], "actions": ["reindex_covers"]},
            "fields": [
                {
                    "key": "chunk_size",
                    "label": "Chunk size per job",
                    "input_type": "number",
                    "value": 200,
                    "description": "How many items to pack into each worker job.",
                },
                {
                    "key": "cover_folder",
                    "label": "Cover output folder",
                    "input_type": "folder_target",
                    "value": {"account_id": "acc-1", "folder_path": "/Comics/Covers"},
                    "description": "Where generated covers are stored.",
                },
            ],
        }
    ],
}

OBSERVABILITY = {
    "queue_depth": 18,
    "pending_jobs": 5,
    "running_jobs": 4,
    "retry_scheduled_jobs": 2,
    "throughput_last_hour": 184,
    "throughput_window": 1280,
    "avg_duration_seconds_window": 48,
    "p95_duration_seconds_window": 213,
    "metrics_total_window": 1450,
    "metrics_success_window": 1362,
    "metrics_failed_window": 41,
    "metrics_skipped_window": 47,
    "success_rate_window": 0.939,
    "dead_letter_jobs_window": 3,
    "generated_at": "2026-03-14T13:16:00Z",
    "cache_hit": False,
    "cache_ttl_seconds": 0,
    "period_label": "Last 24h",
    "provider_request_usage": [
        {
            "provider": "microsoft",
            "provider_label": "Microsoft Graph",
            "requests_in_window": 742,
            "max_requests": 1000,
            "window_seconds": 60,
            "utilization_ratio": 0.742,
            "total_requests_since_start": 12842,
            "throttled_responses": 2,
            "docs_url": "https://learn.microsoft.com/graph/throttling",
        },
        {
            "provider": "openai",
            "provider_label": "OpenAI-compatible endpoint",
            "requests_in_window": 188,
            "max_requests": 500,
            "window_seconds": 60,
            "utilization_ratio": 0.376,
            "total_requests_since_start": 2891,
            "throttled_responses": 0,
            "docs_url": "https://platform.openai.com/docs/guides/rate-limits",
        },
    ],
    "integration_health": [
        {"key": "redis", "label": "Redis queue", "status": "ok", "detail": "Healthy pub/sub and enqueue latency under 30ms."},
        {"key": "postgres", "label": "PostgreSQL", "status": "ok", "detail": "Migrations current and pool saturation below 40%."},
        {"key": "vision", "label": "Vision worker", "status": "warning", "detail": "Optional profile disabled on this node."},
    ],
    "dead_letter_jobs": [
        {
            "id": "job-1004",
            "type": "reindex_comic_covers",
            "dead_letter_reason": "Remote storage throttled after repeated retries.",
            "dead_lettered_at": "2026-03-14T09:22:00Z",
            "retry_count": 3,
            "max_retries": 3,
        },
        {
            "id": "job-0888",
            "type": "analyze_library_image_assets",
            "dead_letter_reason": "Image parser timed out on corrupt payload.",
            "dead_lettered_at": "2026-03-14T07:14:00Z",
            "retry_count": 3,
            "max_retries": 3,
        },
    ],
}

SESSIONS = [
    {"id": "session-1", "title": "Triage duplicate Saga issues", "updated_at": "2026-03-14T13:14:00Z", "title_pending": False},
    {"id": "session-2", "title": "Prepare release metadata batch", "updated_at": "2026-03-14T11:20:00Z", "title_pending": False},
]

SESSION_MESSAGES = {
    "session-1": [
        {
            "id": "msg-1",
            "session_id": "session-1",
            "role": "user",
            "content_redacted": "Show me duplicate Saga issues and queue the safe removals.",
            "created_at": "2026-03-14T13:10:00Z",
        },
        {
            "id": "msg-2",
            "session_id": "session-1",
            "role": "tool",
            "content_redacted": json.dumps(
                {
                    "tool_name": "find_similar_files",
                    "status": "completed",
                    "duration_ms": 182,
                    "arguments": {"category": "Comics", "query": "Saga"},
                    "result_summary": {
                        "groups": SIMILAR_REPORT["groups"],
                        "items": [item for group in SIMILAR_REPORT["groups"] for item in group["items"]],
                    },
                }
            ),
            "created_at": "2026-03-14T13:10:01Z",
        },
        {
            "id": "msg-3",
            "session_id": "session-1",
            "role": "assistant",
            "content_redacted": "I found one duplicate group for Saga issue 001 across two providers. I can queue a removal job for the archive copy after your confirmation.",
            "created_at": "2026-03-14T13:10:02Z",
        },
    ],
    "session-2": [
        {
            "id": "msg-4",
            "session_id": "session-2",
            "role": "assistant",
            "content_redacted": "Ready to build a metadata batch for the next release.",
            "created_at": "2026-03-14T11:20:00Z",
        }
    ],
}

PRIVACY_MASK_SCRIPT = """
(() => {
  const emailPattern = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/i;
  for (const node of document.querySelectorAll('body *')) {
    if (node.children.length > 0) continue;
    const text = (node.textContent || '').trim();
    if (!text || !emailPattern.test(text)) continue;
    node.style.filter = 'blur(8px)';
    node.style.userSelect = 'none';
  }
})();
"""

CAPTURES = [
    {"route": "/all-files", "filename": "01-all-files-overview.png"},
    {"route": "/jobs", "filename": "02-jobs-ops-queue.png"},
    {"route": "/rules", "filename": "03-rules-engine.png"},
    {"route": "/ai", "filename": "04-ai-assistant.png", "action": "expand_ai_tool"},
    {"route": "/admin/dashboard", "filename": "05-admin-dashboard.png"},
    {"route": "/admin/settings", "filename": "06-admin-settings.png", "action": "open_metadata_settings"},
]


def svg_asset(title: str, accent: str, subtitle: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#1e293b" />
    </linearGradient>
  </defs>
  <rect width="1200" height="800" fill="url(#bg)" rx="32" />
  <rect x="48" y="48" width="1104" height="704" rx="24" fill="#0b1220" stroke="#334155" />
  <circle cx="140" cy="140" r="52" fill="{accent}" opacity="0.18" />
  <circle cx="1060" cy="180" r="74" fill="{accent}" opacity="0.12" />
  <text x="90" y="170" fill="#f8fafc" font-family="Segoe UI, Arial" font-size="64" font-weight="700">{title}</text>
  <text x="90" y="220" fill="#94a3b8" font-family="Segoe UI, Arial" font-size="28">{subtitle}</text>
  <rect x="90" y="290" width="1020" height="28" rx="14" fill="#1e293b" />
  <rect x="90" y="290" width="520" height="28" rx="14" fill="{accent}" opacity="0.75" />
  <rect x="90" y="360" width="320" height="220" rx="20" fill="#111827" stroke="#334155" />
  <rect x="440" y="360" width="320" height="220" rx="20" fill="#111827" stroke="#334155" />
  <rect x="790" y="360" width="320" height="220" rx="20" fill="#111827" stroke="#334155" />
  <rect x="90" y="610" width="1020" height="80" rx="20" fill="#111827" stroke="#334155" />
</svg>"""


def fulfill_json(route, payload, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))


def install_mocks(page) -> None:
    def handler(route):
        request = route.request
        parsed = urlparse(request.url)
        path_name = parsed.path.removeprefix("/api/v1")
        method = request.method

        if path_name == "/accounts" and method == "GET":
            return fulfill_json(route, {"accounts": ACCOUNTS})
        if path_name == "/metadata/categories" and method == "GET":
            return fulfill_json(route, CATEGORIES)
        if path_name == "/metadata/libraries" and method == "GET":
            return fulfill_json(route, LIBRARIES)
        if path_name == "/items" and method == "GET":
            return fulfill_json(route, {"items": ALL_ITEMS, "total": len(ALL_ITEMS), "total_pages": 1, "page": 1})
        if path_name.startswith("/items/similar-report") and method == "GET":
            return fulfill_json(route, SIMILAR_REPORT)
        if path_name == "/jobs/" and method == "GET":
            return fulfill_json(route, JOBS)

        attempts_match = re.match(r"^/jobs/([^/]+)/attempts$", path_name)
        if attempts_match and method == "GET":
            return fulfill_json(route, ATTEMPTS_BY_JOB.get(attempts_match.group(1), []))

        if path_name == "/metadata/rules" and method == "GET":
            return fulfill_json(route, RULES)
        if path_name == "/metadata/rules/preview" and method == "POST":
            return fulfill_json(route, {"total_matches": 124, "to_change": 117, "already_compliant": 7, "sample_item_ids": ["item-2", "item-3", "item-7"]})
        if path_name == "/admin/settings" and method == "GET":
            return fulfill_json(route, RUNTIME_SETTINGS)
        if path_name == "/admin/observability" and method == "GET":
            return fulfill_json(route, OBSERVABILITY)
        if path_name == "/ai/chat/sessions" and method == "GET":
            return fulfill_json(route, SESSIONS)

        messages_match = re.match(r"^/ai/chat/sessions/([^/]+)/messages$", path_name)
        if messages_match and method == "GET":
            return fulfill_json(route, SESSION_MESSAGES.get(messages_match.group(1), []))

        if "/download/" in path_name and path_name.endswith("/content") and method == "GET":
            return route.fulfill(status=200, content_type="image/svg+xml", body=svg_asset("Driver Asset", "#f59e0b", "Mocked visual used for documentation"))

        return fulfill_json(route, {})

    page.route("**/api/v1/**", handler)


def prepare_page(page, route_path: str) -> None:
    page.goto(f"{FRONTEND_URL}{route_path}", wait_until="networkidle")
    page.wait_for_timeout(600)
    page.add_style_tag(
        content="""
        .app-shell > button,
        .app-shell > div.fixed {
            display: none !important;
        }
        """
    )
    page.evaluate(PRIVACY_MASK_SCRIPT)


def run_capture_action(page, action_name: str | None) -> None:
    if action_name == "expand_ai_tool":
        try:
            page.get_by_role("button", name=re.compile("find_similar_files", re.I)).first.click(timeout=2000)
            page.wait_for_timeout(250)
        except Exception:
            pass
    if action_name == "open_metadata_settings":
        try:
            page.get_by_role("button", name=re.compile("metadata libraries", re.I)).first.click(timeout=2000)
            page.wait_for_timeout(250)
        except Exception:
            pass


def launch_browser(playwright):
    launch_args = {"headless": True, "args": ["--hide-scrollbars"]}
    chrome_candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe"),
        Path(r"C:\Program Files\Google\Chrome Dev\Application\chrome.exe"),
    ]

    for candidate in chrome_candidates:
        if candidate.exists():
            launch_args["executable_path"] = str(candidate)
            break
    else:
        launch_args["channel"] = "chrome"

    try:
        return playwright.chromium.launch(**launch_args)
    except Exception:
        fallback_args = {"headless": True, "args": ["--hide-scrollbars"]}
        return playwright.chromium.launch(**fallback_args)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        context = browser.new_context(
            viewport={"width": 1600, "height": 1180},
            color_scheme="light",
            locale="en-US",
        )
        page = context.new_page()
        page.add_init_script("window.localStorage.setItem('driver-language', 'en');")
        install_mocks(page)

        for capture in CAPTURES:
            prepare_page(page, capture["route"])
            run_capture_action(page, capture.get("action"))
            page.evaluate(PRIVACY_MASK_SCRIPT)
            page.locator(".app-panel").screenshot(path=str(OUTPUT_DIR / capture["filename"]))

        browser.close()

    print(f"Captured {len(CAPTURES)} screenshots to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

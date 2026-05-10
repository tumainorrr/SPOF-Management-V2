import copy
import csv
import io
import json
import os
import textwrap
from datetime import datetime
from urllib.parse import quote, urlsplit, urlunsplit

import pandas as pd
import tkinter as tk
from tkinter import filedialog


DEFAULT_ACTION_CENTER_SETTINGS = {
    "high_duplicate": False,
    "high_versions_mb": 500.0,
    "high_min_mb": None,
    "high_max_mb": None,
    "high_age_years": None,
    "high_total_mb": 1024.0,
    "medium_duplicate": True,
    "medium_versions_mb": 100.0,
    "medium_min_mb": 100.0,
    "medium_max_mb": 1024.0,
    "medium_age_years": None,
    "medium_total_mb": None,
    "low_duplicate": False,
    "low_versions_mb": None,
    "low_min_mb": None,
    "low_max_mb": None,
    "low_age_years": 1.0,
    "low_total_mb": 50.0,
    "very_low_duplicate": False,
    "very_low_versions_mb": None,
    "very_low_min_mb": None,
    "very_low_max_mb": None,
    "very_low_age_years": 3.0,
    "very_low_total_mb": None,
    "pdf_focus_items_limit": 12,
    "pdf_group_duplicate_topics": True,
}

SHAREPOINT_BASE_URL = "https://accor.sharepoint.com"
NULLABLE_FLOAT_SETTING_KEYS = {
    "high_versions_mb",
    "high_min_mb",
    "high_max_mb",
    "high_age_years",
    "high_total_mb",
    "medium_versions_mb",
    "medium_min_mb",
    "medium_max_mb",
    "medium_age_years",
    "medium_total_mb",
    "low_versions_mb",
    "low_min_mb",
    "low_max_mb",
    "low_age_years",
    "low_total_mb",
    "very_low_versions_mb",
    "very_low_min_mb",
    "very_low_max_mb",
    "very_low_age_years",
    "very_low_total_mb",
}


def get_action_center_settings_path(base_dir):
    config_dir = os.path.join(base_dir, "Data", "Config")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "action_center_settings.json")


def _coerce_float(value, default):
    try:
        parsed = float(value)
        if parsed < 0:
            return default
        return parsed
    except Exception:
        return default


def _coerce_nullable_float(value, default):
    if value in (None, ""):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _coerce_float(value, default)


def _coerce_int(value, default, minimum=None, maximum=None):
    try:
        parsed = int(float(value))
    except Exception:
        parsed = default

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _coerce_bool(value, default):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False

    if value is None:
        return default
    return bool(value)


def normalize_action_center_settings(settings):
    source = settings or {}
    normalized = copy.deepcopy(DEFAULT_ACTION_CENTER_SETTINGS)
    legacy_mapped = {}

    if "high_total_size_gb" in source and "high_total_mb" not in source:
        legacy_value = _coerce_nullable_float(source.get("high_total_size_gb"), DEFAULT_ACTION_CENTER_SETTINGS["high_total_mb"])
        legacy_mapped["high_total_mb"] = None if legacy_value is None else legacy_value * 1024
    if "high_versions_size_mb" in source and "high_versions_mb" not in source:
        legacy_mapped["high_versions_mb"] = _coerce_nullable_float(source.get("high_versions_size_mb"), DEFAULT_ACTION_CENTER_SETTINGS["high_versions_mb"])
    if "medium_total_size_min_mb" in source and "medium_min_mb" not in source:
        legacy_mapped["medium_min_mb"] = _coerce_nullable_float(source.get("medium_total_size_min_mb"), DEFAULT_ACTION_CENTER_SETTINGS["medium_min_mb"])
    if "medium_total_size_max_mb" in source and "medium_max_mb" not in source:
        legacy_mapped["medium_max_mb"] = _coerce_nullable_float(source.get("medium_total_size_max_mb"), DEFAULT_ACTION_CENTER_SETTINGS["medium_max_mb"])
    if "medium_versions_size_mb" in source and "medium_versions_mb" not in source:
        legacy_mapped["medium_versions_mb"] = _coerce_nullable_float(source.get("medium_versions_size_mb"), DEFAULT_ACTION_CENTER_SETTINGS["medium_versions_mb"])
    if "low_age_years" in source and "low_age_years" not in legacy_mapped:
        legacy_mapped["low_age_years"] = _coerce_nullable_float(source.get("low_age_years"), DEFAULT_ACTION_CENTER_SETTINGS["low_age_years"])
    if "low_total_size_mb" in source and "low_total_mb" not in source:
        legacy_mapped["low_total_mb"] = _coerce_nullable_float(source.get("low_total_size_mb"), DEFAULT_ACTION_CENTER_SETTINGS["low_total_mb"])
    if "very_low_age_years" in source and "very_low_age_years" not in legacy_mapped:
        legacy_mapped["very_low_age_years"] = _coerce_nullable_float(source.get("very_low_age_years"), DEFAULT_ACTION_CENTER_SETTINGS["very_low_age_years"])

    source = {**legacy_mapped, **source}

    for key, default in DEFAULT_ACTION_CENTER_SETTINGS.items():
        if isinstance(default, bool):
            normalized[key] = _coerce_bool(source.get(key, default), default)
            continue
        if isinstance(default, int):
            normalized[key] = _coerce_int(source.get(key, default), default, minimum=1, maximum=50)
            continue
        if key in NULLABLE_FLOAT_SETTING_KEYS and key in source:
            normalized[key] = _coerce_nullable_float(source.get(key), default)
            continue
        normalized[key] = _coerce_float(source.get(key, default), default)

    for priority_key in ("high", "medium", "low", "very_low"):
        min_key = f"{priority_key}_min_mb"
        max_key = f"{priority_key}_max_mb"
        if (
            normalized[min_key] is not None
            and normalized[max_key] is not None
            and normalized[max_key] < normalized[min_key]
        ):
            normalized[max_key] = normalized[min_key]

    return normalized


def load_action_center_settings(base_dir):
    path = get_action_center_settings_path(base_dir)
    if not os.path.exists(path):
        return normalize_action_center_settings(None)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return normalize_action_center_settings(data)
    except Exception:
        return normalize_action_center_settings(None)


def get_default_action_center_settings():
    return normalize_action_center_settings(None)


def save_action_center_settings(base_dir, settings):
    normalized = normalize_action_center_settings(settings)
    path = get_action_center_settings_path(base_dir)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "path": path,
        "settings": normalized,
    }


def reset_action_center_settings(base_dir):
    defaults = get_default_action_center_settings()
    return save_action_center_settings(base_dir, defaults)


def _sanitize_filename(value):
    safe = str(value or "action_center_report").strip()
    safe = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in safe)
    return safe or "action_center_report"


def _rows_to_dataframe(rows):
    frame = pd.DataFrame(rows or [])
    preferred_columns = [
        "Library",
        "File Name",
        "Extension",
        "Folder Path",
        "Current Size (MB)",
        "Version Count",
        "Versions Size (MB)",
        "Total Size (MB)",
        "Last Datetime of Original Version",
        "First Datetime of History Version",
        "Age (Years)",
        "Priority",
        "Recommended Action",
        "Reason",
    ]

    available = [column for column in preferred_columns if column in frame.columns]
    remaining = [column for column in frame.columns if column not in available]
    if available or remaining:
        frame = frame[available + remaining]

    return frame


def _build_summary_frame(summary, meta):
    rows = []
    meta = meta or {}
    summary = summary or {}

    for key, value in [
        ("Department", meta.get("deptName", "-")),
        ("Category", meta.get("category", "-")),
        ("Exported At", meta.get("exportedAt", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))),
        ("Search", meta.get("searchTerm", "")),
        ("Priority Filter", meta.get("priorityFilter", "All")),
        ("Action Filter", meta.get("actionFilter", "All")),
        ("Matched Rows", summary.get("matchedRows", 0)),
        ("High", summary.get("highCount", 0)),
        ("Medium", summary.get("mediumCount", 0)),
        ("Low", summary.get("lowCount", 0)),
        ("Very Low", summary.get("veryLowCount", 0)),
        ("Duplicate Items", summary.get("duplicateCount", 0)),
        ("Duplicate Groups", summary.get("duplicateGroups", 0)),
    ]:
        rows.append({"Metric": key, "Value": value})

    return pd.DataFrame(rows)


def _escape_pdf_text(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _pdf_text(value):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _pdf_wrap(value, width):
    return textwrap.wrap(_pdf_text(value), width=width) or [""]


def _pdf_ellipsize(value, width):
    text = _pdf_text(value)
    if len(text) <= width:
        return text
    return text[:max(0, width - 3)].rstrip() + "..."


def _coerce_number(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def _parse_action_center_datetime(value):
    if not value:
        return None

    text = str(value).strip()
    if not text or text == "-":
        return None

    patterns = [
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y, %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y, %H:%M:%S",
    ]
    for pattern in patterns:
        try:
            return datetime.strptime(text, pattern)
        except Exception:
            continue
    return None


def _format_pdf_datetime(value):
    parsed = _parse_action_center_datetime(value)
    if parsed:
        return parsed.strftime("%d %b %Y %H:%M")
    text = str(value or "").strip()
    return text or "-"


def _format_pdf_size_mb(value):
    size_mb = _coerce_number(value)
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} GB"
    return f"{size_mb:.2f} MB"


def _build_sharepoint_folder_url(folder_path):
    raw = str(folder_path or "").strip()
    if not raw:
        return ""

    if raw.startswith("http://") or raw.startswith("https://"):
        parts = urlsplit(raw)
        return urlunsplit((
            parts.scheme,
            parts.netloc,
            quote(parts.path, safe="/:%"),
            parts.query,
            parts.fragment,
        ))

    if raw.startswith("/"):
        return f"{SHAREPOINT_BASE_URL}{quote(raw, safe='/%')}"

    return raw.replace(" ", "%20")


def _priority_rank(value):
    return {
        "High": 0,
        "Medium": 1,
        "Low": 2,
        "Very Low": 3,
    }.get(str(value or ""), 9)


def _build_duplicate_subitem_layout(item):
    summary_lines = _pdf_wrap(
        (
            f"- {item['file_name']} | {_format_pdf_size_mb(item['total_size_mb'])} | "
            f"Last Original: {_format_pdf_datetime(item['last_original'])}"
        ),
        74,
    )
    path_lines = _pdf_wrap(f"Path: {item['folder_path']}", 74)
    has_open_link = bool(item.get("folder_url"))
    height = (len(summary_lines) * 11) + (len(path_lines) * 11) + (18 if has_open_link else 0) + 9
    return {
        "summary_lines": summary_lines,
        "path_lines": path_lines,
        "has_open_link": has_open_link,
        "height": height,
    }


def _build_pdf_overview(rows, summary):
    rows = rows or []
    summary = summary or {}

    total_size_mb = sum(_coerce_number(row.get("Total Size (MB)")) for row in rows)
    versions_size_mb = sum(_coerce_number(row.get("Versions Size (MB)")) for row in rows)
    duplicate_count = summary.get("duplicateCount")
    if duplicate_count is None:
        duplicate_count = sum(1 for row in rows if str(row.get("Duplicate Candidate", "")).lower() == "yes")

    last_original_dates = [
        parsed
        for parsed in (
            _parse_action_center_datetime(row.get("Last Datetime of Original Version"))
            for row in rows
        )
        if parsed
    ]

    return {
        "matched_rows": int(summary.get("matchedRows", len(rows) or 0)),
        "high_count": int(summary.get("highCount", 0)),
        "medium_count": int(summary.get("mediumCount", 0)),
        "low_count": int(summary.get("lowCount", 0)),
        "very_low_count": int(summary.get("veryLowCount", 0)),
        "duplicate_count": int(duplicate_count or 0),
        "duplicate_groups": int(summary.get("duplicateGroups", 0)),
        "total_size_mb": total_size_mb,
        "versions_size_mb": versions_size_mb,
        "oldest_last_original": min(last_original_dates) if last_original_dates else None,
        "newest_last_original": max(last_original_dates) if last_original_dates else None,
    }


def _build_single_pdf_focus_block(row):
    duplicate_candidate = str(row.get("Duplicate Candidate", "")).lower() == "yes"
    return {
        "type": "single",
        "priority": row.get("Priority") or "-",
        "priority_rank": _priority_rank(row.get("Priority")),
        "duplicate_candidate": duplicate_candidate,
        "duplicate_count": int(_coerce_number(row.get("Duplicate Count")) or (2 if duplicate_candidate else 0)),
        "total_size_mb": _coerce_number(row.get("Total Size (MB)")),
        "versions_size_mb": _coerce_number(row.get("Versions Size (MB)")),
        "age_years": _coerce_number(row.get("Age (Years)")),
        "last_original": row.get("Last Datetime of Original Version") or "-",
        "recommended_action": row.get("Recommended Action") or "-",
        "reason": row.get("Reason") or "-",
        "title": row.get("File Name") or "-",
        "folder_path": row.get("Folder Path") or "-",
        "folder_url": _build_sharepoint_folder_url(row.get("Folder Path")),
        "items": [],
    }


def _build_grouped_duplicate_pdf_focus_block(group_key, rows):
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            -_coerce_number(row.get("Total Size (MB)")),
            -_coerce_number(row.get("Versions Size (MB)")),
            row.get("File Name") or "",
        ),
    )
    primary_row = ordered_rows[0]
    highest_priority_row = min(ordered_rows, key=lambda row: _priority_rank(row.get("Priority")))
    oldest_last_original = [
        parsed
        for parsed in (
            _parse_action_center_datetime(row.get("Last Datetime of Original Version"))
            for row in ordered_rows
        )
        if parsed
    ]

    subitems = []
    for row in ordered_rows:
        subitems.append({
            "file_name": row.get("File Name") or "-",
            "folder_path": row.get("Folder Path") or "-",
            "folder_url": _build_sharepoint_folder_url(row.get("Folder Path")),
            "total_size_mb": _coerce_number(row.get("Total Size (MB)")),
            "last_original": row.get("Last Datetime of Original Version") or "-",
        })

    duplicate_title = primary_row.get("File Name") or "Duplicate Group"
    return {
        "type": "duplicate_group",
        "group_key": group_key,
        "priority": highest_priority_row.get("Priority") or "High",
        "priority_rank": _priority_rank(highest_priority_row.get("Priority")),
        "duplicate_candidate": True,
        "duplicate_count": len(ordered_rows),
        "total_size_mb": sum(_coerce_number(row.get("Total Size (MB)")) for row in ordered_rows),
        "versions_size_mb": sum(_coerce_number(row.get("Versions Size (MB)")) for row in ordered_rows),
        "age_years": max(_coerce_number(row.get("Age (Years)")) for row in ordered_rows),
        "last_original": (
            min(oldest_last_original).strftime("%d-%m-%Y %H:%M:%S")
            if oldest_last_original else primary_row.get("Last Datetime of Original Version") or "-"
        ),
        "recommended_action": "Review duplicate candidates",
        "reason": f"{len(ordered_rows)} files share the same duplicate signature and are grouped into one PDF topic.",
        "title": f"Duplicate Group ({len(ordered_rows)} files) - {duplicate_title}",
        "folder_path": "",
        "folder_url": "",
        "items": subitems,
    }


def _build_pdf_focus_blocks(rows, settings, limit_results=True):
    rows = rows or []
    settings = settings or {}
    focus_limit = _coerce_int(settings.get("pdf_focus_items_limit", 12), 12, minimum=1, maximum=50)
    group_duplicates = _coerce_bool(settings.get("pdf_group_duplicate_topics", True), True)

    if not group_duplicates:
        blocks = [_build_single_pdf_focus_block(row) for row in rows]
    else:
        duplicate_groups = {}
        single_blocks = []
        for row in rows:
            duplicate_group = str(row.get("Duplicate Group") or "").strip()
            is_duplicate = str(row.get("Duplicate Candidate", "")).lower() == "yes"
            if is_duplicate and duplicate_group:
                duplicate_groups.setdefault(duplicate_group, []).append(row)
            else:
                single_blocks.append(_build_single_pdf_focus_block(row))

        blocks = []
        for group_key, grouped_rows in duplicate_groups.items():
            if len(grouped_rows) > 1:
                blocks.append(_build_grouped_duplicate_pdf_focus_block(group_key, grouped_rows))
            else:
                blocks.append(_build_single_pdf_focus_block(grouped_rows[0]))
        blocks.extend(single_blocks)

    blocks.sort(
        key=lambda block: (
            block["priority_rank"],
            0 if block["type"] == "duplicate_group" else 1,
            -block["total_size_mb"],
            -block["versions_size_mb"],
            -block["age_years"],
            _pdf_text(block["title"]).lower(),
        )
    )
    if limit_results:
        return blocks[:focus_limit]
    return blocks


def _create_pdf_page():
    return {"commands": [], "annotations": []}


def _pdf_add_rect(page, x, y, width, height, fill_rgb=None, stroke_rgb=None, line_width=1):
    commands = [f"{line_width} w"]
    if fill_rgb:
        commands.append(f"{fill_rgb[0]:.3f} {fill_rgb[1]:.3f} {fill_rgb[2]:.3f} rg")
    if stroke_rgb:
        commands.append(f"{stroke_rgb[0]:.3f} {stroke_rgb[1]:.3f} {stroke_rgb[2]:.3f} RG")

    mode = "B" if fill_rgb and stroke_rgb else "f" if fill_rgb else "S"
    commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re {mode}")
    page["commands"].append("\n".join(commands))


def _pdf_add_text(page, x, y, text, font="F1", size=10, rgb=(0.12, 0.16, 0.24)):
    safe_text = _escape_pdf_text(_pdf_text(text))
    page["commands"].append(
        "\n".join([
            "BT",
            f"/{font} {size} Tf",
            f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg",
            f"1 0 0 1 {x:.2f} {y:.2f} Tm",
            f"({safe_text}) Tj",
            "ET",
        ])
    )


def _pdf_add_link(page, x, y, width, height, url):
    if not url:
        return

    escaped_url = _escape_pdf_text(url)
    page["annotations"].append(
        f"<< /Type /Annot /Subtype /Link /Rect [{x:.2f} {y:.2f} {x + width:.2f} {y + height:.2f}] "
        f"/Border [0 0 0] /A << /S /URI /URI ({escaped_url}) >> >>"
    )


def _pdf_add_action_link_button(page, x, y, width, height, label, url):
    _pdf_add_rect(
        page,
        x,
        y,
        width,
        height,
        fill_rgb=(0.97, 0.98, 1.00),
        stroke_rgb=(0.79, 0.84, 0.93),
        line_width=0.8,
    )
    text_x = x + max(10, (width - (len(_pdf_text(label)) * 4.2)) / 2)
    text_y = y + 5
    _pdf_add_text(page, text_x, text_y, label, font="F2", size=8.5, rgb=(0.20, 0.30, 0.48))
    _pdf_add_link(page, x, y, width, height, url)


def _draw_pdf_summary(page, meta, overview, focus_count, total_rows, group_duplicates):
    exported_at = meta.get("exportedAt", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    priority_filter = meta.get("priorityFilter", "All")
    action_filter = meta.get("actionFilter", "All")
    search_term = meta.get("searchTerm", "")

    _pdf_add_text(page, 42, 800, "SPOF Action Center", font="F2", size=24, rgb=(0.11, 0.20, 0.43))
    _pdf_add_text(page, 42, 780, "Clean PDF summary for sharing by email", size=11, rgb=(0.35, 0.42, 0.56))

    _pdf_add_rect(page, 40, 708, 515, 56, fill_rgb=(0.95, 0.97, 1.00), stroke_rgb=(0.82, 0.87, 0.95))
    _pdf_add_text(page, 56, 744, f"Department: {meta.get('deptName', '-')}", font="F2", size=12)
    _pdf_add_text(page, 56, 726, f"Category: {meta.get('category', '-')}", size=10, rgb=(0.28, 0.34, 0.46))
    _pdf_add_text(page, 320, 744, f"Exported: {exported_at}", size=10, rgb=(0.28, 0.34, 0.46))
    _pdf_add_text(page, 320, 726, f"Filters: Priority {priority_filter} | Action {action_filter}", size=10, rgb=(0.28, 0.34, 0.46))

    if search_term:
        search_label = f"Search: {search_term}"
        for index, line in enumerate(_pdf_wrap(search_label, 56)[:2]):
            _pdf_add_text(page, 56, 710 - (index * 14), line, size=10, rgb=(0.28, 0.34, 0.46))

    cards = [
        ("Matched Items", str(overview["matched_rows"]), _format_pdf_size_mb(overview["total_size_mb"])),
        ("Version Footprint", _format_pdf_size_mb(overview["versions_size_mb"]), f"Duplicates: {overview['duplicate_count']}"),
        (
            "Date Coverage",
            overview["oldest_last_original"].strftime("%d %b %Y") if overview["oldest_last_original"] else "-",
            (
                f"Latest: {overview['newest_last_original'].strftime('%d %b %Y')}"
                if overview["newest_last_original"] else "Latest: -"
            ),
        ),
    ]

    card_x_positions = [40, 217, 394]
    for x, (title, value, subtext) in zip(card_x_positions, cards):
        _pdf_add_rect(page, x, 622, 161, 70, fill_rgb=(1.00, 1.00, 1.00), stroke_rgb=(0.85, 0.89, 0.94))
        _pdf_add_text(page, x + 16, 673, title, size=10, rgb=(0.46, 0.53, 0.65))
        _pdf_add_text(page, x + 16, 648, value, font="F2", size=18, rgb=(0.10, 0.15, 0.28))
        _pdf_add_text(page, x + 16, 630, subtext, size=9, rgb=(0.35, 0.42, 0.56))

    _pdf_add_rect(page, 40, 548, 515, 56, fill_rgb=(1.00, 1.00, 1.00), stroke_rgb=(0.85, 0.89, 0.94))
    _pdf_add_text(page, 56, 582, "Priority Overview", font="F2", size=12)
    _pdf_add_text(
        page,
        56,
        560,
        (
            f"High {overview['high_count']} | Medium {overview['medium_count']} | "
            f"Low {overview['low_count']} | Very Low {overview['very_low_count']} | "
            f"Duplicate Groups {overview['duplicate_groups']}"
        ),
        size=10,
        rgb=(0.28, 0.34, 0.46),
    )

    _pdf_add_text(page, 42, 520, "Focus Items", font="F2", size=16, rgb=(0.11, 0.20, 0.43))
    focus_note = f"This PDF highlights the top {focus_count} topics out of {total_rows} matched rows."
    _pdf_add_text(page, 42, 500, focus_note, size=10, rgb=(0.35, 0.42, 0.56))
    summary_line = "Duplicate matches are grouped into one topic." if group_duplicates else "Duplicate rows are shown individually."
    _pdf_add_text(page, 42, 486, summary_line, size=10, rgb=(0.35, 0.42, 0.56))
    _pdf_add_text(page, 42, 472, "Use Excel or CSV export when you need the full row-level dataset.", size=10, rgb=(0.35, 0.42, 0.56))


def _estimate_pdf_focus_block_height(block):
    if block["type"] != "duplicate_group":
        return 112

    visible_subitems = min(3, len(block["items"]))
    total_height = 126
    for item in block["items"][:visible_subitems]:
        total_height += _build_duplicate_subitem_layout(item)["height"]
    if len(block["items"]) > visible_subitems:
        total_height += 18
    return total_height


def _draw_pdf_focus_block(page, block, index, top_y):
    block_height = _estimate_pdf_focus_block_height(block)
    bottom_y = top_y - block_height
    _pdf_add_rect(page, 40, bottom_y, 515, block_height, fill_rgb=(1.00, 1.00, 1.00), stroke_rgb=(0.87, 0.90, 0.95))

    priority = block["priority"]
    recommended_action = block["recommended_action"]
    reason = block["reason"]
    duplicate_text = "Yes" if block["duplicate_candidate"] else "No"
    duplicate_count = int(block["duplicate_count"])

    title_lines = _pdf_wrap(f"{index}. [{priority}] {block['title']}", 50)[:2]
    for line_index, line in enumerate(title_lines):
        _pdf_add_text(page, 54, top_y - 22 - (line_index * 13), line, font="F2", size=12)

    detail_y = top_y - 50
    if block["type"] == "single":
        path_lines = _pdf_wrap(f"Path: {block['folder_path']}", 60)[:2]
        for line_index, line in enumerate(path_lines):
            _pdf_add_text(page, 54, detail_y - (line_index * 12), line, size=9, rgb=(0.35, 0.42, 0.56))
    else:
        _pdf_add_text(page, 54, detail_y, f"Grouped Duplicate Topic: {duplicate_count} files", size=9, rgb=(0.35, 0.42, 0.56))

    metrics_text = (
        f"Total: {_format_pdf_size_mb(block['total_size_mb'])} | "
        f"Versions: {_format_pdf_size_mb(block['versions_size_mb'])} | "
        f"Age: {block['age_years']:.1f} yrs"
    )
    _pdf_add_text(page, 54, top_y - 79, metrics_text, size=9)

    last_original_text = _format_pdf_datetime(block["last_original"])
    action_text = f"Action: {recommended_action} | Last Original: {last_original_text}"
    _pdf_add_text(page, 54, top_y - 92, action_text, size=9)

    reason_line = _pdf_wrap(f"Reason: {reason}", 78)[0]
    duplicate_suffix = f" | Duplicate: {duplicate_text}"
    if duplicate_count > 1:
        duplicate_suffix += f" ({duplicate_count})"
    _pdf_add_text(page, 54, top_y - 104, f"{reason_line}{duplicate_suffix}", size=9, rgb=(0.35, 0.42, 0.56))

    if block["type"] == "single" and block["folder_url"]:
        _pdf_add_action_link_button(
            page,
            430,
            top_y - 56,
            110,
            18,
            "Open folder",
            block["folder_url"],
        )

    if block["type"] == "duplicate_group":
        subitem_y = top_y - 124
        visible_subitems = block["items"][:3]
        for sub_index, item in enumerate(visible_subitems, start=1):
            layout = _build_duplicate_subitem_layout(item)
            current_y = subitem_y
            for summary_line in layout["summary_lines"]:
                _pdf_add_text(page, 68, current_y, summary_line, size=8.5, rgb=(0.20, 0.26, 0.38))
                current_y -= 11

            path_y = current_y - 1
            for path_line in layout["path_lines"]:
                _pdf_add_text(page, 82, path_y, path_line, size=8, rgb=(0.40, 0.46, 0.58))
                path_y -= 11

            if layout["has_open_link"]:
                _pdf_add_action_link_button(
                    page,
                    430,
                    path_y - 10,
                    110,
                    18,
                    "Open folder",
                    item["folder_url"],
                )

            subitem_y -= layout["height"]

        hidden_count = len(block["items"]) - len(visible_subitems)
        if hidden_count > 0:
            _pdf_add_text(page, 68, subitem_y, f"+ {hidden_count} more duplicate files in this group", size=8.5, rgb=(0.40, 0.46, 0.58))

    return bottom_y - 12


def _build_action_center_pdf(rows, summary, meta, settings):
    meta = meta or {}
    settings = settings or {}
    overview = _build_pdf_overview(rows, summary)
    focus_blocks = _build_pdf_focus_blocks(rows, settings)
    group_duplicates = _coerce_bool(settings.get("pdf_group_duplicate_topics", True), True)

    pages = []
    current_page = _create_pdf_page()
    pages.append(current_page)
    _draw_pdf_summary(current_page, meta, overview, len(focus_blocks), len(rows), group_duplicates)

    current_y = 458
    for index, block in enumerate(focus_blocks, start=1):
        required_height = _estimate_pdf_focus_block_height(block)
        if current_y - required_height < 70:
            current_page = _create_pdf_page()
            pages.append(current_page)
            _pdf_add_text(current_page, 42, 800, "SPOF Action Center", font="F2", size=20, rgb=(0.11, 0.20, 0.43))
            _pdf_add_text(current_page, 42, 778, "Focus Items (continued)", size=11, rgb=(0.35, 0.42, 0.56))
            current_y = 742

        current_y = _draw_pdf_focus_block(current_page, block, index, current_y)

    return _render_pdf_document(pages)


def _render_pdf_document(pages):
    objects = []
    font_regular_obj_num = 1
    font_bold_obj_num = 2
    pages_obj_num = 3
    next_obj_num = 4
    page_entries = []

    objects.append((font_regular_obj_num, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objects.append((font_bold_obj_num, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"))

    for page in pages or [_create_pdf_page()]:
        annotation_obj_nums = []
        for annotation in page["annotations"]:
            annotation_obj_nums.append(next_obj_num)
            objects.append((next_obj_num, annotation.encode("latin-1", errors="replace")))
            next_obj_num += 1

        stream = "\n".join(page["commands"]).encode("latin-1", errors="replace")
        content_obj_num = next_obj_num
        page_obj_num = next_obj_num + 1
        next_obj_num += 2

        objects.append((content_obj_num, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
        page_entries.append((page_obj_num, content_obj_num, annotation_obj_nums))

    kids = " ".join(f"{page_obj_num} 0 R" for page_obj_num, _, _ in page_entries)
    objects.append((pages_obj_num, f"<< /Type /Pages /Kids [{kids}] /Count {len(page_entries)} >>".encode("latin-1")))

    for page_obj_num, content_obj_num, annotation_obj_nums in page_entries:
        annots_fragment = ""
        if annotation_obj_nums:
            annots_refs = " ".join(f"{annotation_obj_num} 0 R" for annotation_obj_num in annotation_obj_nums)
            annots_fragment = f" /Annots [{annots_refs}]"

        page_bytes = (
            f"<< /Type /Page /Parent {pages_obj_num} 0 R "
            f"/MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_regular_obj_num} 0 R /F2 {font_bold_obj_num} 0 R >> >> "
            f"/Contents {content_obj_num} 0 R{annots_fragment} >>"
        ).encode("latin-1")
        objects.append((page_obj_num, page_bytes))

    catalog_obj_num = next_obj_num
    objects.append((catalog_obj_num, f"<< /Type /Catalog /Pages {pages_obj_num} 0 R >>".encode("latin-1")))
    objects.sort(key=lambda item: item[0])

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]

    for obj_num, payload in objects:
        offsets.append(buffer.tell())
        buffer.write(f"{obj_num} 0 obj\n".encode("latin-1"))
        buffer.write(payload)
        buffer.write(b"\nendobj\n")

    xref_start = buffer.tell()
    buffer.write(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("latin-1"))

    buffer.write(
        (
            f"trailer\n<< /Size {len(offsets)} /Root {catalog_obj_num} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF"
        ).encode("latin-1")
    )
    return buffer.getvalue()


def export_action_center_report(base_dir, payload):
    payload = payload or {}
    export_format = str(payload.get("format", "csv")).lower()
    rows = payload.get("rows") or []
    summary = payload.get("summary") or {}
    meta = payload.get("meta") or {}
    settings = normalize_action_center_settings(payload.get("settings") or {})

    if export_format not in {"csv", "xlsx", "pdf"}:
        return {"success": False, "error": "Unsupported export format."}

    if not rows:
        return {"success": False, "error": "No rows available for export."}

    export_dir = os.path.join(base_dir, "Data", "Exports")
    os.makedirs(export_dir, exist_ok=True)

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    extension = {
        "csv": ".csv",
        "xlsx": ".xlsx",
        "pdf": ".pdf",
    }[export_format]
    filetypes = {
        "csv": [("CSV Files", "*.csv")],
        "xlsx": [("Excel Files", "*.xlsx")],
        "pdf": [("PDF Files", "*.pdf")],
    }[export_format]

    suggested_name = _sanitize_filename(payload.get("fileNameBase") or "action_center_report") + extension
    file_path = filedialog.asksaveasfilename(
        title="Export Action Center Report",
        initialdir=export_dir,
        initialfile=suggested_name,
        defaultextension=extension,
        filetypes=filetypes + [("All Files", "*.*")],
    )
    root.destroy()

    if not file_path:
        return {"success": False, "cancelled": True}

    note = None
    try:
        frame = _rows_to_dataframe(rows)

        if export_format == "csv":
            frame.to_csv(file_path, index=False, encoding="utf-8-sig")
        elif export_format == "xlsx":
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                frame.to_excel(writer, sheet_name="ActionData", index=False)
                _build_summary_frame(summary, meta).to_excel(writer, sheet_name="Summary", index=False)
        else:
            all_focus_topics = _build_pdf_focus_blocks(rows, settings, limit_results=False)
            with open(file_path, "wb") as handle:
                handle.write(_build_action_center_pdf(rows, summary, meta, settings))
            focus_limit = settings.get("pdf_focus_items_limit", 12)
            if len(all_focus_topics) > focus_limit:
                note = f"PDF export is optimized for email sharing and highlights the top {focus_limit} topics only. Use Excel or CSV for full detail."

        return {
            "success": True,
            "path": file_path,
            "format": export_format,
            "note": note,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}

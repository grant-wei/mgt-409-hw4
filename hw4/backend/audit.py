from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_PATH = Path(__file__).resolve().parents[1] / "output" / "audit_trail.json"
_LOCK = threading.Lock()
_SENSITIVE_VALUE = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9_-]{8,}|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|"
    r"(?:api[_ -]?key|password(?:\s+is)?|passwd|secret|token)\s*[:=]?\s*[^\s,;]+)"
)


def _safe_text(value: Any, limit: int = 120) -> str:
    text = str(value)
    text = _SENSITIVE_VALUE.sub("[REDACTED]", text)
    return text[:limit]


def _product_summary(value: Any, *, include_sizes: bool = False) -> dict[str, Any] | None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict) or "product_id" not in value:
        return None
    summary: dict[str, Any] = {
        "product_id": _safe_text(value.get("product_id")),
        "name": _safe_text(value.get("name")),
    }
    if isinstance(value.get("price"), (int, float)):
        summary["price"] = value["price"]
    sizes = value.get("sizes")
    if include_sizes and isinstance(sizes, list):
        summary["sizes"] = [
            {
                "size": _safe_text(item.get("size")),
                "quantity": item.get("quantity"),
                "in_stock": item.get("in_stock"),
            }
            for item in sizes[:12]
            if isinstance(item, dict)
        ]
    return summary


def _tool_args(tool_name: str, args: Any) -> dict[str, Any]:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {"summary": _safe_text(args)}
    if not isinstance(args, dict):
        return {"summary": _safe_text(args)}

    # Keep only documented tool parameters so personal context or provider
    # metadata cannot accidentally enter the audit file.
    allowed = {
        "search_products": {"search_term", "max_results"},
        "get_product_details": {"product_id"},
    }.get(tool_name, set())
    return {
        key: (_safe_text(value) if isinstance(value, str) else value)
        for key, value in args.items()
        if key in allowed and isinstance(value, (str, int, float, bool, type(None)))
    }


def _tool_result(value: Any, tool_name: str) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, list):
        products = [summary for item in value if (summary := _product_summary(item))]
        return {"count": len(value), "products": products[:3]}
    product = _product_summary(value, include_sizes=tool_name == "get_product_details")
    if product is not None:
        return {"product": product}
    if value is None:
        return {"found": False}
    if isinstance(value, (str, int, float, bool)):
        return {"value": _safe_text(value)} if isinstance(value, str) else {"value": value}
    return {"type": type(value).__name__}


def tool_calls_from(result: Any) -> list[dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    for message in result.all_messages():
        for part in getattr(message, "parts", []):
            part_type = type(part).__name__
            if part_type == "ToolCallPart":
                call_id = str(getattr(part, "tool_call_id", ""))
                name = str(getattr(part, "tool_name", "unknown"))
                if name == "final_result":
                    continue
                calls[call_id] = {
                    "tool_name": name,
                    "args": _tool_args(name, getattr(part, "args", {})),
                    "result": {"status": "called"},
                }
            elif part_type == "ToolReturnPart":
                call_id = str(getattr(part, "tool_call_id", ""))
                if call_id in calls:
                    calls[call_id]["result"] = _tool_result(getattr(part, "content", None), calls[call_id]["tool_name"])
    return list(calls.values())


def write_audit_entry(entry: dict[str, Any]) -> None:
    """Append one run record without discarding any earlier records."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = AUDIT_PATH.with_suffix(AUDIT_PATH.suffix + ".lock")
    with _LOCK, lock_path.open("a+b") as lock_file:
        try:
            import msvcrt

            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        except ImportError:
            pass
        try:
            if AUDIT_PATH.exists():
                existing = json.loads(AUDIT_PATH.read_text(encoding="utf-8").lstrip("\ufeff"))
                if not isinstance(existing, list):
                    raise ValueError("audit_trail.json must contain a JSON array")
            else:
                existing = []
            existing.append(entry)
            payload = json.dumps(existing, ensure_ascii=False, indent=2) + "\n"
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=AUDIT_PATH.parent,
                prefix="audit_trail.", suffix=".tmp", delete=False,
            ) as temp_file:
                temp_file.write(payload)
                temp_path = Path(temp_file.name)
            os.replace(temp_path, AUDIT_PATH)
        finally:
            try:
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except ImportError:
                pass


def new_entry(*, tool_calls: list[dict[str, Any]], result: dict[str, Any], stop_reason: str) -> dict[str, Any]:
    return {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "tool_name": "PydanticAI shop_agent",
        "args": {
            "tool_calls": tool_calls,
            "request_limit": 8,
            "tool_call_limit": 8,
            "timeout_seconds": 75,
        },
        "result": result,
        "stop_reason": stop_reason,
    }

"""Shared utility helpers."""

from __future__ import annotations

import json


def sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _find_first_json_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False

        for idx in range(start, len(text)):
            char = text[idx]

            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]

        start = text.find("{", start + 1)

    return None


def extract_json(response: str) -> dict:
    response = response.strip()
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    json_str = _find_first_json_object(response)
    if not json_str:
        raise ValueError(f"Unable to extract JSON from response: {response}")

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}; extracted={json_str}") from exc
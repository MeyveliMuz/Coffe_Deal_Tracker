"""Kullanıcının kahve tercihleri — asistanın sohbetler arası hafızası.

`data/ai_preferences.json`: [{kind: like|dislike|note, text, ts}]. Asistan
`remember_preference` / `forget_preference` araçlarıyla yazar; her sohbette
sistem talimatına eklenir. Dosya git dışında (data/).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.core.config import default_db_path

KINDS = ("like", "dislike", "note")
MAX_ITEMS = 40


def _path() -> Path:
    return Path(default_db_path()).parent / "ai_preferences.json"


def load() -> list[dict]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return [d for d in data if isinstance(d, dict) and d.get("text")]
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-MAX_ITEMS:], ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def remember(kind: str, text: str) -> list[dict]:
    kind = kind if kind in KINDS else "note"
    text = " ".join(str(text).split())[:200]
    items = [d for d in load() if d["text"].lower() != text.lower()]
    if text:
        items.append({"kind": kind, "text": text, "ts": datetime.now().isoformat(timespec="seconds")})
        _save(items)
    return items


def forget(text: str) -> tuple[int, list[dict]]:
    """`text` geçen tercihleri sil (büyük/küçük harf duyarsız alt dize)."""
    t = str(text).lower().strip()
    items = load()
    keep = [d for d in items if t and t not in d["text"].lower()]
    if len(keep) != len(items):
        _save(keep)
    return len(items) - len(keep), keep


def as_text() -> str:
    items = load()
    if not items:
        return "(henüz kayıtlı tercih yok)"
    label = {"like": "SEVER", "dislike": "SEVMEZ", "note": "NOT"}
    return "\n".join(f"- {label.get(d['kind'], 'NOT')}: {d['text']}" for d in items)

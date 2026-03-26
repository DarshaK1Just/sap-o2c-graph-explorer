from __future__ import annotations

import os
import sqlite3
from typing import Any

import httpx


def _get_schema_brief(con: sqlite3.Connection) -> dict[str, list[str]]:
    tables = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    out: dict[str, list[str]] = {}
    for t in tables:
        # Skip SQLite internals
        if t.startswith("sqlite_"):
            continue
        cols = [r["name"] for r in con.execute(f'PRAGMA table_info("{t}")').fetchall()]
        # Brief: keep first N columns; enough for LLM grounding
        out[t] = cols[:30]
    return out


SYSTEM_PROMPT = """You are a data analyst assistant for an SAP Order-to-Cash dataset.
You MUST:
- Answer only using the provided database schema.
- Generate a SINGLE SQLite SELECT query (read-only) that answers the user's question.
- Use only tables that exist in the schema.
- Return JSON only: {"sql": "..."} (no markdown, no explanation).

If the user asks something unrelated to the dataset/domain, return: {"sql": null}
"""


def _build_user_prompt(question: str, schema: dict[str, list[str]]) -> str:
    return (
        "User question:\n"
        f"{question}\n\n"
        "SQLite schema (tables -> columns):\n"
        + "\n".join([f"- {t}: {', '.join(cols)}" for t, cols in schema.items()])
        + "\n\n"
        "Important relationships hints (from the dataset):\n"
        "- sales_order_headers.salesOrder joins sales_order_items.salesOrder\n"
        "- outbound_delivery_items.referenceSdDocument -> sales_order_headers.salesOrder\n"
        "- billing_document_items.referenceSdDocument -> outbound_delivery_headers.deliveryDocument\n"
        "- billing_document_headers.accountingDocument is related to journal_entry_items_ar.accountingDocument\n"
        "- journal_entry_items_ar.referenceDocument -> billing_document_headers.billingDocument\n"
        "\nReturn JSON only."
    )


async def llm_generate_sql(con: sqlite3.Connection, question: str) -> str | None:
    provider = (os.getenv("O2C_LLM_PROVIDER") or "").lower().strip()
    if not provider:
        return None

    schema = _get_schema_brief(con)
    user_prompt = _build_user_prompt(question, schema)

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        model = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
        if not api_key:
            return None
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
    elif provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct")
        if not api_key:
            return None
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
    else:
        # Keep providers minimal for this submission; templates still work without keys.
        return None

    timeout = float(os.getenv("O2C_LLM_TIMEOUT_SEC", "20"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    # OpenAI-style response
    content = data["choices"][0]["message"]["content"]
    # content must be JSON like {"sql": "..."} or {"sql": null}
    import json

    obj = json.loads(content)
    sql = obj.get("sql")
    if not sql:
        return None
    if not isinstance(sql, str):
        return None
    return sql


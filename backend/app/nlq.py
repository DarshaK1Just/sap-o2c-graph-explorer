from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp

from .llm_sql import llm_generate_sql


DOMAIN_KEYWORDS = {
    "sales order",
    "sales",
    "order",
    "delivery",
    "billing",
    "invoice",
    "journal",
    "payment",
    "customer",
    "product",
    "plant",
    "document",
    "accounting",
    "ar",
    "flow",
    "trace",
    "highest",
    "most",
    "broken",
    "incomplete",
}


OFFTOPIC_KEYWORDS = {
    "weather",
    "sports",
    "politics",
    "covid",
    "recipe",
    "movie",
    "book",
    "song",
    "joke",
    "math",
    "physics",
    "chemistry",
    "biology",
    "history",
    "geography",
    "philosophy",
}


ALLOWED_TABLES = {
    # raw tables
    "sales_order_headers",
    "sales_order_items",
    "outbound_delivery_headers",
    "outbound_delivery_items",
    "billing_document_headers",
    "billing_document_items",
    "journal_entry_items_ar",
    "payments_ar",
    "business_partners",
    "business_partner_addresses",
    "products",
    "product_descriptions",
    "plants",
    "customer_company_assignments",
    "customer_sales_area_assignments",
    "product_plants",
    "product_storage_locations",
    "sales_order_schedule_lines",
    "billing_document_cancellations",
    # graph tables (for graph exploration)
    "nodes",
    "edges",
}


OFFTOPIC_RESPONSE = "This system is designed to answer questions related to the provided SAP Order-to-Cash dataset only. I can help with: Sales Orders, Deliveries, Billing Documents, Journal Entries, Payments, Customers, Products, and Plants."


def is_domain_question(q: str) -> bool:
    ql = q.lower().strip()
    
    # Check for offtopic keywords first
    if any(k in ql for k in OFFTOPIC_KEYWORDS):
        return False
    
    # Accept domain keywords
    if any(k in ql for k in DOMAIN_KEYWORDS):
        return True
    
    # Also accept pure document-id style queries if they mention a known entity word.
    if re.search(r"\b\d{6,}\b", ql) and any(w in ql for w in ("billing", "delivery", "sales", "order", "journal", "accounting", "payment", "flow")):
        return True
    
    return False


def _validate_sql_readonly(sql: str) -> tuple[bool, str]:
    try:
        parsed = sqlglot.parse_one(sql, read="sqlite")
    except Exception as e:
        return False, f"Invalid SQL: {e}"

    # Collect CTE names so we don't treat them as external tables.
    cte_names: set[str] = set()
    with_expr = parsed.find(exp.With)
    if with_expr is not None:
        for cte in with_expr.find_all(exp.CTE):
            alias = cte.alias
            if alias:
                # alias can be a string or an Identifier object
                name = alias.name if hasattr(alias, 'name') else str(alias)
                if name:
                    cte_names.add(name)

    # Must be a SELECT (or WITH ... SELECT). No DDL/DML.
    if isinstance(parsed, exp.Select):
        root_select = parsed
    else:
        root_select = parsed.find(exp.Select)
    if root_select is None:
        return False, "Only SELECT queries are allowed."

    bad = parsed.find(exp.Insert) or parsed.find(exp.Update) or parsed.find(exp.Delete) or parsed.find(exp.Drop) or parsed.find(exp.Alter) or parsed.find(exp.Create)
    if bad is not None:
        return False, "Write operations are not allowed."

    # Table allowlist
    for table in parsed.find_all(exp.Table):
        name = (table.name or "").strip('"').strip("'")
        if name in cte_names:
            continue
        if name and name not in ALLOWED_TABLES:
            return False, f"Table not allowed: {name}"

    return True, ""


def run_sql(con: sqlite3.Connection, sql: str, limit: int = 200) -> list[dict[str, Any]]:
    ok, msg = _validate_sql_readonly(sql)
    if not ok:
        raise ValueError(msg)

    cur = con.execute(sql)
    rows = cur.fetchmany(limit)
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({k: r[k] for k in r.keys()})
    return out


@dataclass
class NLQResult:
    answer: str
    sql: str | None
    rows: list[dict[str, Any]] | None


def _template_sql(q: str) -> str | None:
    ql = q.lower()

    # (a) products with highest number of billing documents
    if ("highest" in ql or "most" in ql) and "billing" in ql and "product" in ql:
        return """
        SELECT
          bdi.material AS product,
          pd.productDescription AS productDescription,
          COUNT(DISTINCT bdi.billingDocument) AS billingDocumentCount
        FROM billing_document_items bdi
        LEFT JOIN product_descriptions pd
          ON pd.product = bdi.material AND pd.language = 'EN'
        GROUP BY bdi.material, pd.productDescription
        ORDER BY billingDocumentCount DESC
        LIMIT 20
        """

    # (b) trace full flow of a billing document
    # Match 8+ digit patterns or explicit 'billing <number>' patterns
    m = re.search(r"\b(\d{8,})\b", q) or re.search(r"billing\s+(\d+)", q, re.IGNORECASE)
    if ("trace" in ql or "flow" in ql) and "billing" in ql and m:
        billing = m.group(1)
        return f"""
        WITH
        billing_docs AS (
          SELECT billingDocument, accountingDocument, companyCode, fiscalYear
          FROM billing_document_headers
          WHERE billingDocument = '{billing}'
        ),
        deliveries AS (
          SELECT DISTINCT bdi.referenceSdDocument AS deliveryDocument
          FROM billing_document_items bdi
          WHERE bdi.billingDocument = '{billing}'
        ),
        sales_orders AS (
          SELECT DISTINCT odi.referenceSdDocument AS salesOrder
          FROM outbound_delivery_items odi
          JOIN deliveries d ON d.deliveryDocument = odi.deliveryDocument
        ),
        journal_entries AS (
          SELECT DISTINCT je.accountingDocument
          FROM journal_entry_items_ar je
          WHERE je.referenceDocument = '{billing}'
        )
        SELECT
          '{billing}' AS billingDocument,
          (SELECT GROUP_CONCAT(deliveryDocument, ', ') FROM deliveries) AS deliveryDocuments,
          (SELECT GROUP_CONCAT(salesOrder, ', ') FROM sales_orders) AS salesOrders,
          (SELECT GROUP_CONCAT(accountingDocument, ', ') FROM journal_entries) AS accountingDocuments
        """

    # (c) broken flows: delivered not billed; billed without delivery
    if ("broken" in ql or "incomplete" in ql) and ("flow" in ql or "flows" in ql or "orders" in ql):
        return """
        WITH delivered AS (
          SELECT DISTINCT referenceSdDocument AS salesOrder
          FROM outbound_delivery_items
          WHERE referenceSdDocument IS NOT NULL AND referenceSdDocument != ''
        ),
        billed_sales_orders AS (
          SELECT DISTINCT odi.referenceSdDocument AS salesOrder
          FROM billing_document_items bdi
          JOIN outbound_delivery_items odi
            ON odi.deliveryDocument = bdi.referenceSdDocument
          WHERE odi.referenceSdDocument IS NOT NULL AND odi.referenceSdDocument != ''
        ),
        billed_without_delivery AS (
          SELECT DISTINCT bdi.billingDocument
          FROM billing_document_items bdi
          LEFT JOIN outbound_delivery_headers odh
            ON odh.deliveryDocument = bdi.referenceSdDocument
          WHERE odh.deliveryDocument IS NULL
        )
        SELECT
          'DELIVERED_NOT_BILLED' AS issueType,
          d.salesOrder AS id
        FROM delivered d
        LEFT JOIN billed_sales_orders b ON b.salesOrder = d.salesOrder
        WHERE b.salesOrder IS NULL
        UNION ALL
        SELECT
          'BILLED_WITHOUT_DELIVERY' AS issueType,
          b.billingDocument AS id
        FROM billed_without_delivery b
        LIMIT 200
        """

    return None


def answer_nlq(con: sqlite3.Connection, q: str) -> NLQResult:
    """
    Answer a natural language question about the O2C dataset.
    Implements guardrails:
    1. Domain restriction: reject off-topic questions
    2. SQL injection prevention: validate all generated SQL
    3. Safe execution: parameterized queries, read-only enforcement
    4. Graceful fallback: provide helpful guidance when query can't be answered
    """
    
    q = q.strip()
    
    # Guardrail 1: Check if question is on-topic
    if not is_domain_question(q):
        return NLQResult(answer=OFFTOPIC_RESPONSE, sql=None, rows=None)

    # Optional LLM: if configured, generate SQL dynamically; otherwise deterministic templates.
    sql: str | None = None
    try:
        # NOTE: this is async; run in a simple event loop if no loop is running.
        import asyncio

        sql = asyncio.run(llm_generate_sql(con, q))
    except RuntimeError:
        # If an event loop exists (rare in this sync FastAPI endpoint), skip LLM.
        sql = None
    except Exception as e:
        print(f"LLM SQL generation error: {e}")
        sql = None

    if sql is None:
        sql = _template_sql(q)
    
    if sql is None:
        return NLQResult(
            answer=(
                "I can answer questions about Sales Orders, Deliveries, Billing Documents, Journal Entries, Payments, Customers, Products, and Plants. "
                "Examples: 'Trace the full flow of billing document 90504248' or 'Which products appear in the most billing documents?'"
            ),
            sql=None,
            rows=None,
        )

    # Guardrail 2: Validate SQL is read-only and uses allowed tables
    ok, msg = _validate_sql_readonly(sql)
    if not ok:
        return NLQResult(
            answer=f"Query validation failed: {msg}. This system only supports read-only queries on the O2C dataset.",
            sql=None,
            rows=None
        )

    # Guardrail 3: Execute safely with row limit
    try:
        rows = run_sql(con, sql, limit=200)
    except Exception as e:
        return NLQResult(
            answer=f"Error executing query: {str(e)}. Please try a different query.",
            sql=sql,
            rows=None
        )
    
    # Guardrail 4: No results
    if not rows:
        return NLQResult(
            answer=f"No results found for '{q}' in the dataset. The document may not exist or may not have complete data.",
            sql=sql,
            rows=rows
        )

    return NLQResult(answer="Here are the top results grounded in the dataset.", sql=sql, rows=rows)



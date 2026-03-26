from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import orjson

from .db import init_db


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield orjson.loads(line)


def _union_keys(rows: Iterable[dict[str, Any]], sample_limit: int = 2000) -> set[str]:
    keys: set[str] = set()
    for i, r in enumerate(rows):
        keys.update(r.keys())
        if i + 1 >= sample_limit:
            break
    return keys


def _to_sqlite_value(v: Any) -> Any:
    # Keep everything as TEXT except numbers; simplest + robust for inconsistent schemas.
    if v is None:
        return None
    if isinstance(v, (str, int, float)):
        return v
    return json.dumps(v, ensure_ascii=False)


def _sanitize_ident(name: str) -> str:
    # conservative: lowercase, keep alnum + underscore only
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    s = "".join(out)
    if s and s[0].isdigit():
        s = f"c_{s}"
    return s


@dataclass(frozen=True)
class DatasetTable:
    dataset_name: str  # directory name
    table_name: str  # sqlite table name
    id_fields: tuple[str, ...]  # used to create node ids


TABLES: list[DatasetTable] = [
    DatasetTable("sales_order_headers", "sales_order_headers", ("salesOrder",)),
    DatasetTable("sales_order_items", "sales_order_items", ("salesOrder", "salesOrderItem")),
    DatasetTable("outbound_delivery_headers", "outbound_delivery_headers", ("deliveryDocument",)),
    DatasetTable("outbound_delivery_items", "outbound_delivery_items", ("deliveryDocument", "deliveryDocumentItem")),
    DatasetTable("billing_document_headers", "billing_document_headers", ("billingDocument",)),
    DatasetTable("billing_document_items", "billing_document_items", ("billingDocument", "billingDocumentItem")),
    DatasetTable("journal_entry_items_accounts_receivable", "journal_entry_items_ar", ("companyCode", "fiscalYear", "accountingDocument", "accountingDocumentItem")),
    DatasetTable("payments_accounts_receivable", "payments_ar", ("companyCode", "fiscalYear", "accountingDocument", "accountingDocumentItem")),
    DatasetTable("business_partners", "business_partners", ("businessPartner",)),
    DatasetTable("business_partner_addresses", "business_partner_addresses", ("businessPartner", "addressId")),
    DatasetTable("products", "products", ("product",)),
    DatasetTable("product_descriptions", "product_descriptions", ("product", "language")),
    DatasetTable("plants", "plants", ("plant",)),
    DatasetTable("customer_company_assignments", "customer_company_assignments", ("customer", "companyCode")),
    DatasetTable("customer_sales_area_assignments", "customer_sales_area_assignments", ("customer", "salesOrganization", "distributionChannel", "organizationDivision")),
    DatasetTable("product_plants", "product_plants", ("product", "plant")),
    DatasetTable("product_storage_locations", "product_storage_locations", ("product", "plant", "storageLocation")),
    DatasetTable("sales_order_schedule_lines", "sales_order_schedule_lines", ("salesOrder", "salesOrderItem", "scheduleLine")),
    DatasetTable("billing_document_cancellations", "billing_document_cancellations", ("billingDocument",)),
]


def ingest_all(con, dataset_root: Path) -> None:
    init_db(con)
    for t in TABLES:
        dataset_dir = dataset_root / t.dataset_name
        if not dataset_dir.exists():
            continue
        ingest_dataset_table(con, dataset_dir=dataset_dir, table_name=t.table_name)


def ingest_dataset_table(con, dataset_dir: Path, table_name: str) -> None:
    jsonl_files = sorted(dataset_dir.glob("*.jsonl"))
    if not jsonl_files:
        return

    # Discover columns.
    keys: set[str] = set()
    for fp in jsonl_files:
        keys.update(_union_keys(_iter_jsonl(fp), sample_limit=2000))
    cols = sorted({_sanitize_ident(k) for k in keys})
    col_map = {k: _sanitize_ident(k) for k in keys}

    con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    con.execute(
        f'CREATE TABLE "{table_name}" (\n'
        + ",\n".join([f'  "{c}" TEXT' for c in cols])
        + "\n)"
    )

    insert_cols = cols
    placeholders = ",".join(["?"] * len(insert_cols))
    col_list = ",".join([f'"{c}"' for c in insert_cols])
    insert_sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'

    for fp in jsonl_files:
        batch: list[tuple[Any, ...]] = []
        for r in _iter_jsonl(fp):
            row_dict = {col_map.get(k, _sanitize_ident(k)): _to_sqlite_value(v) for k, v in r.items()}
            batch.append(tuple(row_dict.get(c) for c in insert_cols))
            if len(batch) >= 2000:
                con.executemany(insert_sql, batch)
                batch.clear()
        if batch:
            con.executemany(insert_sql, batch)


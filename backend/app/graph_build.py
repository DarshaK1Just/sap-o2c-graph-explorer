from __future__ import annotations

import json
import sqlite3
from typing import Any


def _node_id(*parts: Any) -> str:
    return ":".join([str(p) for p in parts if p is not None and str(p) != ""])


def _put_node(con: sqlite3.Connection, node_type: str, node_id: str, label: str, metadata: dict[str, Any]) -> None:
    con.execute(
        """
        INSERT OR REPLACE INTO nodes(node_type, node_id, label, metadata_json)
        VALUES (?, ?, ?, ?)
        """,
        (node_type, node_id, label, json.dumps(metadata, ensure_ascii=False)),
    )


def _put_edge(con: sqlite3.Connection, src_type: str, src_id: str, rel: str, dst_type: str, dst_id: str) -> None:
    con.execute(
        "INSERT INTO edges(src_type, src_id, rel, dst_type, dst_id) VALUES (?,?,?,?,?)",
        (src_type, src_id, rel, dst_type, dst_id),
    )


def rebuild_graph(con: sqlite3.Connection) -> None:
    # Clear graph tables only (keep raw data tables).
    con.execute("DELETE FROM edges")
    con.execute("DELETE FROM nodes")

    # --- Customers / Business Partners ---
    for r in con.execute(
        'SELECT businessPartner AS businessPartner, businessPartnerName AS name, businessPartnerIsBlocked AS blocked FROM business_partners'
    ):
        bp = r["businessPartner"]
        if not bp:
            continue
        _put_node(con, "Customer", bp, f"Customer {bp}", {"businessPartner": bp, "name": r["name"], "blocked": r["blocked"]})

    for r in con.execute(
        "SELECT businessPartner, addressId, cityName, region, country, postalCode, streetName FROM business_partner_addresses"
    ):
        bp = r["businessPartner"]
        addr_id = r["addressId"]
        if not bp or not addr_id:
            continue
        addr_node = _node_id(bp, addr_id)
        _put_node(
            con,
            "Address",
            addr_node,
            f"Address {addr_id}",
            dict(r),
        )
        _put_edge(con, "Customer", bp, "HAS_ADDRESS", "Address", addr_node)

    # --- Products ---
    for r in con.execute("SELECT product, productOldId, productGroup, baseUnit FROM products"):
        pid = r["product"]
        if not pid:
            continue
        _put_node(con, "Product", pid, f"Product {pid}", dict(r))

    for r in con.execute("SELECT product, language, productDescription FROM product_descriptions"):
        pid = r["product"]
        if not pid:
            continue
        _put_edge(con, "Product", pid, "HAS_DESCRIPTION", "ProductDescription", _node_id(pid, r["language"] or ""))
        _put_node(
            con,
            "ProductDescription",
            _node_id(pid, r["language"] or ""),
            r["productDescription"] or f"Description {pid}",
            dict(r),
        )

    # --- Plants ---
    for r in con.execute("SELECT plant, plantName, salesOrganization, distributionChannel, division FROM plants"):
        plant = r["plant"]
        if not plant:
            continue
        _put_node(con, "Plant", plant, r["plantName"] or f"Plant {plant}", dict(r))

    # --- Sales Orders ---
    for r in con.execute(
        "SELECT salesOrder, soldToParty, salesOrganization, distributionChannel, organizationDivision, creationDate, totalNetAmount, transactionCurrency FROM sales_order_headers"
    ):
        so = r["salesOrder"]
        if not so:
            continue
        _put_node(con, "SalesOrder", so, f"Sales Order {so}", dict(r))
        if r["soldToParty"]:
            _put_edge(con, "Customer", r["soldToParty"], "PLACED", "SalesOrder", so)

    for r in con.execute(
        "SELECT salesOrder, salesOrderItem, material, requestedQuantity, requestedQuantityUnit, netAmount, transactionCurrency, productionPlant, storageLocation FROM sales_order_items"
    ):
        so = r["salesOrder"]
        item = r["salesOrderItem"]
        if not so or not item:
            continue
        so_item = _node_id(so, item)
        _put_node(con, "SalesOrderItem", so_item, f"SO Item {so}-{item}", dict(r))
        _put_edge(con, "SalesOrder", so, "HAS_ITEM", "SalesOrderItem", so_item)
        if r["material"]:
            _put_edge(con, "SalesOrderItem", so_item, "MATERIAL", "Product", r["material"])
        if r["productionPlant"]:
            _put_edge(con, "SalesOrderItem", so_item, "PRODUCED_AT", "Plant", r["productionPlant"])

    # --- Deliveries ---
    for r in con.execute("SELECT deliveryDocument, creationDate, shippingPoint FROM outbound_delivery_headers"):
        d = r["deliveryDocument"]
        if not d:
            continue
        _put_node(con, "Delivery", d, f"Delivery {d}", dict(r))

    for r in con.execute(
        "SELECT deliveryDocument, deliveryDocumentItem, plant, storageLocation, referenceSdDocument, referenceSdDocumentItem, actualDeliveryQuantity, deliveryQuantityUnit FROM outbound_delivery_items"
    ):
        d = r["deliveryDocument"]
        di = r["deliveryDocumentItem"]
        if not d or not di:
            continue
        d_item = _node_id(d, di)
        _put_node(con, "DeliveryItem", d_item, f"Delivery Item {d}-{di}", dict(r))
        _put_edge(con, "Delivery", d, "HAS_ITEM", "DeliveryItem", d_item)
        if r["plant"]:
            _put_edge(con, "DeliveryItem", d_item, "FROM_PLANT", "Plant", r["plant"])
        # key O2C linkage: Delivery -> SalesOrder (+ item)
        if r["referenceSdDocument"]:
            _put_edge(con, "Delivery", d, "FULFILLS", "SalesOrder", r["referenceSdDocument"])
            if r["referenceSdDocumentItem"]:
                _put_edge(con, "DeliveryItem", d_item, "FULFILLS_ITEM", "SalesOrderItem", _node_id(r["referenceSdDocument"], r["referenceSdDocumentItem"]))

    # --- Billing ---
    for r in con.execute(
        "SELECT billingDocument, billingDocumentDate, totalNetAmount, transactionCurrency, soldToParty, accountingDocument, companyCode, fiscalYear FROM billing_document_headers"
    ):
        b = r["billingDocument"]
        if not b:
            continue
        _put_node(con, "BillingDocument", b, f"Billing {b}", dict(r))
        if r["soldToParty"]:
            _put_edge(con, "Customer", r["soldToParty"], "BILLED", "BillingDocument", b)
        if r["accountingDocument"]:
            je = _node_id(r["companyCode"], r["fiscalYear"], r["accountingDocument"])
            _put_node(con, "AccountingDocument", je, f"Accounting Doc {r['accountingDocument']}", {"companyCode": r["companyCode"], "fiscalYear": r["fiscalYear"], "accountingDocument": r["accountingDocument"]})
            _put_edge(con, "BillingDocument", b, "POSTED_AS", "AccountingDocument", je)

    for r in con.execute(
        "SELECT billingDocument, billingDocumentItem, material, billingQuantity, billingQuantityUnit, netAmount, transactionCurrency, referenceSdDocument, referenceSdDocumentItem FROM billing_document_items"
    ):
        b = r["billingDocument"]
        bi = r["billingDocumentItem"]
        if not b or not bi:
            continue
        b_item = _node_id(b, bi)
        _put_node(con, "BillingItem", b_item, f"Billing Item {b}-{bi}", dict(r))
        _put_edge(con, "BillingDocument", b, "HAS_ITEM", "BillingItem", b_item)
        if r["material"]:
            _put_edge(con, "BillingItem", b_item, "MATERIAL", "Product", r["material"])
        # key O2C linkage: Billing references a Delivery (in this dataset)
        if r["referenceSdDocument"]:
            _put_edge(con, "BillingDocument", b, "BILLS_DELIVERY", "Delivery", r["referenceSdDocument"])
            if r["referenceSdDocumentItem"]:
                _put_edge(con, "BillingItem", b_item, "BILLS_DELIVERY_ITEM", "DeliveryItem", _node_id(r["referenceSdDocument"], r["referenceSdDocumentItem"]))

    # --- Journal Entry items (AR) ---
    for r in con.execute(
        "SELECT companyCode, fiscalYear, accountingDocument, accountingDocumentItem, referenceDocument, customer, postingDate, amountInTransactionCurrency, transactionCurrency, clearingAccountingDocument FROM journal_entry_items_ar"
    ):
        je = _node_id(r["companyCode"], r["fiscalYear"], r["accountingDocument"])
        jei = _node_id(je, r["accountingDocumentItem"])
        _put_node(con, "JournalEntryItem", jei, f"JE Item {r['accountingDocument']}-{r['accountingDocumentItem']}", dict(r))
        _put_edge(con, "AccountingDocument", je, "HAS_LINE", "JournalEntryItem", jei)
        if r["customer"]:
            _put_edge(con, "Customer", r["customer"], "HAS_JE_ITEM", "JournalEntryItem", jei)
        if r["referenceDocument"]:
            _put_edge(con, "JournalEntryItem", jei, "REFERS_TO_BILLING", "BillingDocument", r["referenceDocument"])
        if r["clearingAccountingDocument"]:
            clearing = _node_id(r["companyCode"], r["fiscalYear"], r["clearingAccountingDocument"])
            _put_node(con, "ClearingDocument", clearing, f"Clearing {r['clearingAccountingDocument']}", {"companyCode": r["companyCode"], "fiscalYear": r["fiscalYear"], "accountingDocument": r["clearingAccountingDocument"]})
            _put_edge(con, "JournalEntryItem", jei, "CLEARED_BY", "ClearingDocument", clearing)

    # --- Payments (AR) ---
    for r in con.execute(
        "SELECT companyCode, fiscalYear, accountingDocument, accountingDocumentItem, customer, clearingAccountingDocument, clearingDate, amountInTransactionCurrency, transactionCurrency FROM payments_ar"
    ):
        pay_doc = _node_id(r["companyCode"], r["fiscalYear"], r["accountingDocument"])
        pay_item = _node_id(pay_doc, r["accountingDocumentItem"])
        _put_node(con, "PaymentItem", pay_item, f"Payment {r['accountingDocument']}-{r['accountingDocumentItem']}", dict(r))
        _put_edge(con, "PaymentDocument", pay_doc, "HAS_LINE", "PaymentItem", pay_item)
        _put_node(con, "PaymentDocument", pay_doc, f"Payment Doc {r['accountingDocument']}", {"companyCode": r["companyCode"], "fiscalYear": r["fiscalYear"], "accountingDocument": r["accountingDocument"]})
        if r["customer"]:
            _put_edge(con, "Customer", r["customer"], "MADE_PAYMENT", "PaymentDocument", pay_doc)
        if r["clearingAccountingDocument"]:
            clearing = _node_id(r["companyCode"], r["fiscalYear"], r["clearingAccountingDocument"])
            _put_edge(con, "PaymentItem", pay_item, "CLEARS", "ClearingDocument", clearing)


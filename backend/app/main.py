from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db import connect, get_db_path, init_db
from .graph_build import rebuild_graph
from .ingest import ingest_all
from .nlq import NLQResult, answer_nlq


DATASET_ROOT_DEFAULT = str(Path(__file__).resolve().parents[2] / "sap-o2c-data")


app = FastAPI(title="O2C Context Graph API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    sql: str | None = None
    rows: list[dict[str, Any]] | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db": str(get_db_path())}


@app.post("/admin/rebuild")
def admin_rebuild(dataset_root: str | None = None) -> dict[str, Any]:
    # No auth required per assignment, but keep it under /admin.
    root = Path(dataset_root or os.getenv("O2C_DATASET_ROOT", DATASET_ROOT_DEFAULT))
    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Dataset root not found: {root}")
    with connect() as con:
        init_db(con)
        ingest_all(con, root)
        rebuild_graph(con)
        stats = con.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]
        edges = con.execute("SELECT COUNT(*) AS n FROM edges").fetchone()["n"]
    return {"ok": True, "dataset_root": str(root), "nodes": stats, "edges": edges}


@app.get("/graph/node")
def get_node(node_type: str, node_id: str) -> dict[str, Any]:
    with connect() as con:
        row = con.execute(
            "SELECT node_type, node_id, label, metadata_json FROM nodes WHERE node_type = ? AND node_id = ?",
            (node_type, node_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Node not found")
        return {
            "type": row["node_type"],
            "id": row["node_id"],
            "label": row["label"],
            "metadata": json.loads(row["metadata_json"]),
        }


@app.get("/graph/neighbors")
def neighbors(node_type: str, node_id: str, limit: int = 200) -> dict[str, Any]:
    with connect() as con:
        edges = con.execute(
            """
            SELECT src_type, src_id, rel, dst_type, dst_id
            FROM edges
            WHERE (src_type = ? AND src_id = ?) OR (dst_type = ? AND dst_id = ?)
            LIMIT ?
            """,
            (node_type, node_id, node_type, node_id, limit),
        ).fetchall()

        # return nodes referenced by these edges
        node_keys = {(node_type, node_id)}
        for e in edges:
            node_keys.add((e["src_type"], e["src_id"]))
            node_keys.add((e["dst_type"], e["dst_id"]))

        nodes: list[dict[str, Any]] = []
        for t, i in node_keys:
            r = con.execute(
                "SELECT node_type, node_id, label, metadata_json FROM nodes WHERE node_type = ? AND node_id = ?",
                (t, i),
            ).fetchone()
            if r:
                nodes.append(
                    {"type": r["node_type"], "id": r["node_id"], "label": r["label"], "metadata": json.loads(r["metadata_json"])}
                )

        return {
            "center": {"type": node_type, "id": node_id},
            "nodes": nodes,
            "edges": [
                {"src": {"type": e["src_type"], "id": e["src_id"]}, "rel": e["rel"], "dst": {"type": e["dst_type"], "id": e["dst_id"]}}
                for e in edges
            ],
        }


@app.get("/graph/search")
def search(q: str, limit: int = 25) -> list[dict[str, Any]]:
    ql = f"%{q.lower()}%"
    with connect() as con:
        rows = con.execute(
            """
            SELECT node_type, node_id, label
            FROM nodes
            WHERE lower(label) LIKE ?
               OR lower(node_id) LIKE ?
            LIMIT ?
            """,
            (ql, ql, limit),
        ).fetchall()
        return [{"type": r["node_type"], "id": r["node_id"], "label": r["label"]} for r in rows]


@app.get("/graph/seed")
def seed() -> dict[str, Any]:
    """
    Pick a "good starting node" to visualize: the node with the highest degree
    (most incident edges). This avoids a blank canvas after init.
    """
    with connect() as con:
        r = con.execute(
            """
            WITH deg AS (
              SELECT src_type AS node_type, src_id AS node_id, COUNT(*) AS d
              FROM edges
              GROUP BY src_type, src_id
              UNION ALL
              SELECT dst_type AS node_type, dst_id AS node_id, COUNT(*) AS d
              FROM edges
              GROUP BY dst_type, dst_id
            ),
            summed AS (
              SELECT node_type, node_id, SUM(d) AS degree
              FROM deg
              GROUP BY node_type, node_id
            )
            SELECT node_type, node_id, degree
            FROM summed
            ORDER BY degree DESC
            LIMIT 1
            """
        ).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="No seed node available (graph is empty).")
        return {"type": r["node_type"], "id": r["node_id"], "degree": r["degree"]}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        if not req.message or not req.message.strip():
            return ChatResponse(
                answer="Please provide a query. I can answer questions about Sales Orders, Deliveries, Billing Documents, Journal Entries, Payments, Customers, Products, and Plants.",
                sql=None,
                rows=None
            )
        with connect() as con:
            res: NLQResult = answer_nlq(con, req.message)
            return ChatResponse(answer=res.answer, sql=res.sql, rows=res.rows)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return ChatResponse(
            answer=f"Error processing query: {str(e)}. Please try a different query about Sales Orders, Deliveries, Billing Documents, Journal Entries, or Payments.",
            sql=None,
            rows=None
        )


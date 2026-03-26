from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def get_db_path() -> Path:
    # Default inside backend/.data so it doesn't clutter the repo root.
    p = os.getenv("O2C_DB_PATH", str(Path(__file__).resolve().parents[1] / ".data" / "o2c.sqlite"))
    return Path(p)


def _ensure_parent_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(db_path: Path | None = None) -> sqlite3.Connection:
    dbp = db_path or get_db_path()
    _ensure_parent_dir(dbp)
    con = sqlite3.connect(str(dbp))
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        yield con
        con.commit()
    finally:
        con.close()


def init_db(con: sqlite3.Connection) -> None:
    # Nodes: unique (type,id), plus a label and raw JSON for inspector.
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes (
          node_type TEXT NOT NULL,
          node_id   TEXT NOT NULL,
          label     TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          PRIMARY KEY (node_type, node_id)
        )
        """
    )

    # Edges: typed relationships, stored as a simple adjacency list.
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS edges (
          src_type TEXT NOT NULL,
          src_id   TEXT NOT NULL,
          rel      TEXT NOT NULL,
          dst_type TEXT NOT NULL,
          dst_id   TEXT NOT NULL
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_type, src_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_type, dst_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_edges_rel ON edges(rel)")

    # Raw entity tables are created dynamically by ingestion (one table per dataset folder).


from __future__ import annotations

import os
from pathlib import Path

from app.db import connect, init_db
from app.graph_build import rebuild_graph
from app.ingest import ingest_all


def main() -> None:
    dataset_root = Path(os.getenv("O2C_DATASET_ROOT", str(Path(__file__).resolve().parents[1] / "sap-o2c-data")))
    if not dataset_root.exists():
        raise SystemExit(f"Dataset root not found: {dataset_root}")

    with connect() as con:
        init_db(con)
        ingest_all(con, dataset_root)
        rebuild_graph(con)
        nodes = con.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]
        edges = con.execute("SELECT COUNT(*) AS n FROM edges").fetchone()["n"]
    print(f"Rebuilt DB. nodes={nodes} edges={edges}")


if __name__ == "__main__":
    main()


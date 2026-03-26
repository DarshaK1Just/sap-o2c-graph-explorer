# SAP Order-to-Cash Context Graph + Grounded Chat (Submission Pack)

This repo turns the provided `sap-o2c-data/` JSONL dataset into:

- A **context graph** (nodes + edges) representing the Order-to-Cash flow
- An interactive **graph UI** (expand nodes, inspect metadata)
- A **chat interface** that answers **dataset-grounded** questions by translating NL → **safe, read-only SQL**
- **Guardrails** that reject off-topic prompts

---

## Architecture (high level)

- **Storage**: SQLite (single file) created locally at `backend/.data/o2c.sqlite`
- **Ingestion**: Streams JSONL partitions into one raw SQLite table per dataset folder
- **Graph model**: Materialized into `nodes` and `edges` tables for fast graph exploration
- **API**: FastAPI
- **UI**: React + Cytoscape.js

### Core O2C edges modeled

- **Customer → SalesOrder**: `PLACED`
- **SalesOrder → SalesOrderItem**: `HAS_ITEM`
- **SalesOrderItem → Product**: `MATERIAL`
- **SalesOrderItem → Plant**: `PRODUCED_AT`
- **Delivery → SalesOrder**: `FULFILLS` (via `outbound_delivery_items.referenceSdDocument`)
- **BillingDocument → Delivery**: `BILLS_DELIVERY` (via `billing_document_items.referenceSdDocument`)
- **JournalEntryItem → BillingDocument**: `REFERS_TO_BILLING` (via `journal_entry_items_ar.referenceDocument`)
- **Payments → ClearingDocument**: `CLEARS` (via `payments_ar.clearingAccountingDocument`)

---

## How to run locally (Windows PowerShell)

### 1) Backend (FastAPI)

From the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt

# Build SQLite + graph (required once)
.\.venv\Scripts\python backend\rebuild_db.py

# Start API
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Backend endpoints:

- `GET /health`
- `POST /admin/rebuild` (re-ingest + rebuild graph)
- `GET /graph/search?q=...`
- `GET /graph/neighbors?node_type=...&node_id=...`
- `POST /chat` body: `{ "message": "..." }`

### 2) Frontend (React)

In a new terminal:

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open: `http://127.0.0.1:5173`

---

## Guardrails

The chat endpoint:

- **Rejects off-topic prompts** with:  
  `"This system is designed to answer questions related to the provided SAP Order-to-Cash dataset only."`
- Only executes **read-only SQL**.
- Blocks SQL that references tables outside an **allowlist**.

---

## Optional: Real LLM-powered NL → SQL (dynamic)

By default, the chat uses safe deterministic SQL templates.
To enable **dynamic NL→SQL**, set one of these providers (free tiers available):

### Groq

```powershell
$env:O2C_LLM_PROVIDER="groq"
$env:GROQ_API_KEY="YOUR_KEY"
# optional
$env:GROQ_MODEL="llama-3.1-70b-versatile"
```

### OpenRouter

```powershell
$env:O2C_LLM_PROVIDER="openrouter"
$env:OPENROUTER_API_KEY="YOUR_KEY"
# optional
$env:OPENROUTER_MODEL="meta-llama/llama-3.1-70b-instruct"
```

The backend still enforces:
- **SELECT-only**
- **table allowlist**
- off-topic rejection

---

## Example queries to try

- **Top products by billing-doc count**:  
  “Which products are associated with the highest number of billing documents?”
- **Trace an end-to-end flow**:  
  “Trace the full flow of billing document 90504248”
- **Broken / incomplete flows**:  
  “Identify sales orders that have broken or incomplete flows”

---

## Submission checklist (you fill)

- **Working demo link**: (deploy backend + frontend, then paste here)
- **Public GitHub repo**: (push this folder)
- **README**: you’re reading it
- **AI coding session logs**: put exports into `ai_session_logs/`

---

## AI session logs

Add your Cursor export transcript(s) here:

- `ai_session_logs/cursor_export.md`


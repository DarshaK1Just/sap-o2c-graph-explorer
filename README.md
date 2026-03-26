# SAP Order-to-Cash Context Graph + Grounded Chat

A full-stack AI assistant for exploring SAP Order-to-Cash business processes through natural language. Built with React, FastAPI, and SQLite.

🔗 **[Live Demo](https://replit.com/@DarshaKakani/sap-o2c-graph-explorer)** | 📦 **[GitHub Repo](https://github.com/DarshaK1Just/sap-o2c-graph-explorer)**

**Try example queries:**

- "Trace the full flow of billing document 90504248"
- "Which products are in the most billing documents?"
- "Show me broken or incomplete flows"

---

## ⚡ Quick Start (5 minutes)

### Prerequisites

- Python 3.10+
- Node.js 18+

### Setup & Run

**1) Install & build database**

```powershell
# Clone and enter repo
git clone https://github.com/DarshaK1Just/sap-o2c-graph-explorer.git
cd sap-o2c-graph-explorer

# Create Python environment
python -m venv .venv
.\.venv\Scripts\activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Build database (ingests sap-o2c-data/ JSONL files)
python backend/rebuild_db.py
```

**2) Start backend (Terminal 1)**

```powershell
# Keep Python environment active
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

✅ API running at `http://127.0.0.1:8000`  
📖 Docs at `http://127.0.0.1:8000/docs`

**3) Start frontend (Terminal 2)**

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

✅ Frontend running at `http://127.0.0.1:5173`

**4) Open in browser**

```
http://127.0.0.1:5173
```

---

## 📁 Project Structure

```
sap-o2c-graph-explorer/
├── frontend/                      # React + Vite + D3.js UI
│   └── src/
│       ├── App.tsx               # Main React component
│       ├── App.css               # Layout & styling
│       └── components/D3Graph.tsx # Force-directed graph
│
├── backend/                       # FastAPI + SQLite
│   └── app/
│       ├── main.py               # HTTP endpoints
│       ├── nlq.py                # NL→SQL pipeline + guardrails
│       ├── db.py                 # Database initialization
│       └── graph_build.py        # Graph construction
│
├── sap-o2c-data/                 # Raw JSONL datasets (21 tables)
│   ├── sales_order_headers/
│   ├── billing_documents/
│   └── [16 other entity types]
│
├── sessions/                      # AI coding session logs
│   ├── README.md
│   └── SESSION_TRANSCRIPT.md
│
└── Documentation files
    ├── SUBMISSION.md              # Architecture & design decisions
    ├── QUICKSTART.md              # Deployment guide
    └── CHECKLIST.md               # Verification checklist
```

---

## 🏗️ Architecture

**Storage**: SQLite at `backend/.data/o2c.sqlite`  
**Graph Model**: Materialized `nodes` and `edges` tables (1,698 nodes, 3,381 edges)  
**API**: FastAPI with 7 endpoints  
**UI**: React + D3.js force-directed visualization

### O2C Business Process Edges

- **Customer → SalesOrder**: `PLACED`
- **SalesOrder → Delivery**: `FULFILLS`
- **Delivery → BillingDocument**: `BILLS_DELIVERY`
- **BillingDocument → JournalEntry**: `REFERS_TO_BILLING`
- **Product, Plant, Customer** connections fully modeled

---

## 📚 API Endpoints

Once backend runs at `http://127.0.0.1:8000`:

| Endpoint                                     | Method | Purpose                  |
| -------------------------------------------- | ------ | ------------------------ |
| `/health`                                    | GET    | Health check             |
| `/graph/search?q=...`                        | GET    | Search nodes by name/ID  |
| `/graph/neighbors?node_type=...&node_id=...` | GET    | Get adjacent nodes       |
| `/graph/node?node_type=...&node_id=...`      | GET    | Get node metadata        |
| `/chat`                                      | POST   | NL query → SQL → results |
| `/admin/rebuild`                             | POST   | Re-ingest all JSONL data |

**Example:**

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Trace billing document 90504248"}'
```

---

## 🛡️ Guardrails & Safety

3-layer protection:

1. **Domain Restriction**
   - Keyword-based on-topic/off-topic detection
   - Rejects non-O2C queries with helpful message

2. **SQL Injection Prevention**
   - sqlglot AST parsing & validation
   - Table allowlist (20 O2C entities only)
   - SELECT-only enforcement

3. **Execution Safety**
   - Max 200 rows per query
   - Error masking
   - Graceful fallback if LLM unavailable

**Verified by**: `test_api.py` (all tests pass)

---

## 🤖 Optional: Dynamic LLM Mode

Default: Safe **template-based SQL**

To enable **dynamic NL→SQL** generation:

```powershell
# Groq (recommended - free tier available)
$env:O2C_LLM_PROVIDER = "groq"
$env:GROQ_API_KEY = "gsk_..."

# Or OpenRouter
$env:O2C_LLM_PROVIDER = "openrouter"
$env:OPENROUTER_API_KEY = "sk-or-..."
```

**All guardrails remain enforced** with LLM enabled.

---

## 📖 Documentation

| File                                                                 | Purpose                     |
| -------------------------------------------------------------------- | --------------------------- |
| **[SUBMISSION.md](SUBMISSION.md)**                                   | Full architecture deep-dive |
| **[QUICKSTART.md](QUICKSTART.md)**                                   | Detailed setup & deployment |
| **[CHECKLIST.md](CHECKLIST.md)**                                     | Submission verification     |
| **[sessions/SESSION_TRANSCRIPT.md](sessions/SESSION_TRANSCRIPT.md)** | AI development process      |

---

## 🧪 Testing

Run automated test suite:

```powershell
python test_api.py
```

Verifies:

- ✅ Database (21 tables, 1,698 nodes, 3,381 edges)
- ✅ Domain detection (on-topic vs off-topic)
- ✅ SQL generation & execution
- ✅ Guardrail enforcement

---

## 📦 Tech Stack

| Component      | Technology                               |
| -------------- | ---------------------------------------- |
| **Frontend**   | React 18 + Vite 6.4 + D3.js + TypeScript |
| **Backend**    | FastAPI 0.115.6 + uvicorn                |
| **Database**   | SQLite3 (single-file)                    |
| **NL→SQL**     | sqlglot (validation) + optional LLM      |
| **Deployment** | Railway, Render, Vercel, AWS             |

---

## 🚀 Live Demo & Deployment

**Already Deployed:**

- 🎉 **[Replit Live Demo](https://replit.com/@DarshaKakani/sap-o2c-graph-explorer)** ← Try it now!

**Deploy Your Own:**
See [QUICKSTART.md](QUICKSTART.md) for:

- Railway (5 min, recommended)
- Render (5 min, free tier)
- Vercel + separate backend
- Self-hosted (AWS/DigitalOcean)

---

## 🎯 Example Queries

```
"Trace the full flow of billing document 90504248"
↓
Generated SQL + graph navigation + results

"Which products appear in the most billing documents?"
↓
Aggregation query with TOP N results

"Show me broken or incomplete flows"
↓
Anomaly detection: delivered-not-billed, billed-without-delivery

"What is the weather?"
↓
Rejected: "This system is designed for SAP Order-to-Cash queries only"
```

---

## 📄 License

Open source. Use freely.

---

## 👨‍💻 Built with AI Assistance

Developed with GitHub Copilot, demonstrating:

- ✅ Rapid full-stack prototyping
- ✅ End-to-end feature implementation
- ✅ Production-ready guardrails
- ✅ Comprehensive documentation

See [sessions/SESSION_TRANSCRIPT.md](sessions/SESSION_TRANSCRIPT.md) for detailed development process.

---

**Questions?** See [SUBMISSION.md](SUBMISSION.md) architecture section.

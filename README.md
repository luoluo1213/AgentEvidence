# AgentEvidence

AgentEvidence is an independently runnable FastAPI research backend with a React
research workspace. The backend wraps the project's custom event-driven
multi-agent runtime. It uses SQLite + SQLAlchemy for knowledge chunks, Chroma for
vector retrieval, an OpenAI-compatible chat provider, and a separately configured
OpenAI-compatible embedding provider.

## Setup

Use Python 3.10 or newer in a virtual environment:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` locally with real server-side provider credentials. Never expose it to
the frontend or commit it.

## Run

Start the backend from the repository root:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

OpenAPI is available at `http://127.0.0.1:8000/docs`. The stable application API is
under `/api/v1`.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
./scripts/demo_api.ps1
```

## Test

```powershell
python -m unittest discover -s tests -v
```

HTTP tests use fake research providers and isolated temporary SQLite/upload storage.
They do not claim that external chat or embedding endpoints are live.

## Frontend

The frontend requires Node.js 20 or newer. Start it in a second terminal:

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
pnpm install
pnpm run dev
```

Open `http://127.0.0.1:5173`. The only public frontend setting is
`VITE_API_BASE_URL`; keep all provider credentials on the backend. npm can be used
instead of pnpm when it is installed:

```powershell
npm install
npm run dev
```

Build and test the frontend with:

```powershell
pnpm run test
pnpm run build
```

See [API contract](docs/api_contract.md), [backend audit](docs/phase1_backend_audit.md),
[Phase 1 delivery report](docs/phase1_delivery_report.md), and
[Phase 2 frontend delivery report](docs/phase2_frontend_delivery.md).

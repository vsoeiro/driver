# OneDrive CBR Management

Aplicacao full-stack para conectar contas (Microsoft e Google), navegar arquivos e executar jobs assincromos de organizacao/sincronizacao.

## Stack

- Backend: FastAPI + SQLAlchemy + Alembic
- Worker: Redis + ARQ
- Frontend: React + Vite + Tailwind
- Banco: PostgreSQL (producao) ou SQLite (desenvolvimento)

## Pre-requisitos

- Python 3.12+
- Node.js 18+
- `uv` instalado

## Configuracao

1. Copie `env.example` para `.env`.
2. Preencha credenciais OAuth e segredos.
3. Ajuste `DATABASE_URL`.

Variaveis principais:

- `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_TENANT_ID`, `MS_REDIRECT_URI`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `SECRET_KEY`, `ENCRYPTION_KEY`
- `DATABASE_URL`
- `REDIS_URL`, `REDIS_QUEUE_NAME`, `WORKER_CONCURRENCY`
- `WORKER_JOB_TIMEOUT_SECONDS` (timeout por job no worker ARQ; default 1800s)
- `ENABLE_DAILY_SYNC_SCHEDULER`, `DAILY_SYNC_CRON`
- `AI_ENABLED`, `AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL`, `AI_TEMPERATURE`, `AI_TIMEOUT_SECONDS`

## Rodando o backend

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## Rodando worker (ARQ)

```bash
uv run arq backend.workers.arq_worker.WorkerSettings
```

Sem Docker (Windows), para instalar Redis local:

```bash
powershell -ExecutionPolicy Bypass -File .\scripts\install_redis_windows.ps1
```

Endpoints uteis:

- Health: `http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/docs`
- Admin runtime settings: `http://localhost:5173/admin/settings` (frontend) -> `GET/PUT /api/v1/admin/settings`
- AI health: `GET /api/v1/ai/health`
- AI schema suggestion: `POST /api/v1/ai/suggest-category-schema`
- AI metadata extraction: `POST /api/v1/ai/extract-metadata`

## Rodando o frontend

```bash
cd frontend
npm ci
npm run dev
```

Se seu PowerShell bloquear `npm.ps1`, use:

```bash
npm.cmd run dev --workspaces=false
```

## Testes

Backend:

```bash
uv run pytest -q
```

Frontend:

```bash
cd frontend
npm.cmd run lint --workspaces=false
npm.cmd run build --workspaces=false
```

## Migracao para Supabase (PostgreSQL)

1. Configure `SUPABASE_DATABASE_URL` com a connection string Postgres do Supabase.
2. Execute:

```bash
pwsh ./scripts/migrate_to_supabase.ps1 -SupabaseUrl "postgresql://user:pass@host:5432/postgres"
```

O script:
- roda `alembic upgrade head` no banco destino;
- migra os dados do `sqlite:///./database.db` para o Supabase.

Opcional (dry-run do plano de tabelas):

```bash
uv run python scripts/migrate_sqlite_to_supabase.py --dry-run --postgres-url "postgresql://..."
```

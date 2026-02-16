# OneDrive CBR Management

Aplicacao full-stack para conectar contas (Microsoft e Google), navegar arquivos e executar jobs assincromos de organizacao/sincronizacao.

## Stack

- Backend: FastAPI + SQLAlchemy + Alembic
- Worker: fila em banco e processador em background
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
- `ENABLE_DAILY_SYNC_SCHEDULER`, `DAILY_SYNC_CRON`

## Rodando o backend

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Endpoints uteis:

- Health: `http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/docs`
- Admin runtime settings: `http://localhost:5173/admin/settings` (frontend) -> `GET/PUT /api/v1/admin/settings`

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

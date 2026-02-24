<p align="center">
  <img src="docs/assets/driver-logo.svg" alt="Driver - Cloud Operations Manager" width="560" />
</p>

# Driver - Cloud Operations Manager

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-Frontend-61DAFB?logo=react&logoColor=0A192F)
![Redis](https://img.shields.io/badge/Redis-Queue-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Vibe Coded](https://img.shields.io/badge/Vibe%20Coded-Yes-F43F5E)

A full-stack application to connect cloud storage providers, browse file libraries, and run asynchronous operations (sync, upload, metadata, rules) with operational observability.

> Warning: this app is intentionally vibe coded. If the vibes are good, ship it. If the vibes are cursed, check the logs first.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Screenshots](#screenshots)
4. [Stack](#stack)
5. [Prerequisites](#prerequisites)
6. [Configuration](#configuration)
7. [Running with Docker](#running-with-docker-recommended)
8. [Running locally](#running-locally)
9. [Queues and workers](#queues-and-workers-light-default-heavy)
10. [Optional Comics Module (Extra)](#optional-comics-module-extra)
11. [Useful commands](#useful-commands)
12. [Troubleshooting](#troubleshooting)

## Overview

With Driver, you can:

- connect multiple cloud accounts (Microsoft, Google, and Dropbox)
- browse and search files in one place
- apply metadata in bulk, recursively, and via rules
- monitor jobs and attempts with retry/dead-letter flows
- track operational health in the Admin dashboard
- optionally enable comics-focused workflows as an extra module

## Architecture

![Architecture Diagram](docs/assets/architecture-diagram.svg)

## Screenshots

### Home
![Home](imgs/01-home.png)

### File Library
![File Library](imgs/02-file-library.png)

### Jobs
![Jobs](imgs/03-jobs.png)

### Metadata
![Metadata](imgs/04-metadata.png)

### Admin Dashboard
![Admin Dashboard](imgs/05-admin-dashboard.png)

## Stack

- Backend: FastAPI + SQLAlchemy + Alembic
- Workers: ARQ + Redis
- Frontend: React + Vite + Tailwind
- Database: PostgreSQL (recommended)

## Prerequisites

- Python 3.12+
- Node.js 18+
- `uv`
- Docker Desktop (optional, for Compose-based execution)

## Configuration

1. Copy `env.example` to `.env`.
2. Fill in OAuth credentials and secrets.
3. Set `DATABASE_URL` (PostgreSQL recommended).

### Required (core)

- `SECRET_KEY`
- `ENCRYPTION_KEY`
- `DATABASE_URL`
- `REDIS_URL`

### Required (at least one provider)

Microsoft provider:
- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET`
- `MS_REDIRECT_URI`

Google provider:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`

Dropbox provider:
- `DROPBOX_CLIENT_ID`
- `DROPBOX_CLIENT_SECRET`
- `DROPBOX_REDIRECT_URI`

You can run with only Microsoft, only Google, or only Dropbox. You do not need all providers.

### Optional (recommended defaults exist)

- `MS_TENANT_ID` (defaults to `common`)
- `REDIS_QUEUE_NAME` (defaults to `driver:jobs`)
- `WORKER_CONCURRENCY`
- `WORKER_JOB_TIMEOUT_SECONDS`
- `ENABLE_DAILY_SYNC_SCHEDULER`
- `RUN_SCHEDULER_IN_API`
- `SCHEDULER_DISTRIBUTED_LOCK_ENABLED`
- `SCHEDULER_LOCK_KEY`
- `SCHEDULER_LOCK_TTL_SECONDS`
- `DAILY_SYNC_CRON`
- comics-related vars (`COMIC_*`) if you enable the optional comics module

### Official provider documentation

- Microsoft Entra app registration:
  `https://learn.microsoft.com/entra/identity-platform/quickstart-register-app`
- Microsoft Graph permissions reference:
  `https://learn.microsoft.com/graph/permissions-reference`
- Google OAuth consent screen:
  `https://developers.google.com/workspace/guides/configure-oauth-consent`
- Google OAuth 2.0 for web server apps:
  `https://developers.google.com/identity/protocols/oauth2/web-server`
- Dropbox OAuth guide:
  `https://developers.dropbox.com/oauth-guide`
- Dropbox app console:
  `https://www.dropbox.com/developers/apps`

## Running with Docker (recommended)

```bash
docker compose up -d --build --remove-orphans
```

Services:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- Redis: `localhost:6379`
- Workers: `worker-light`, `worker-default`, `worker-heavy`

Logs:

```bash
docker compose logs -f backend
docker compose logs -f worker-light
docker compose logs -f worker-default
docker compose logs -f worker-heavy
```

Stop:

```bash
docker compose down
```

## Running locally

### Backend

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd src/frontend
npm.cmd ci --workspaces=false
npm.cmd run dev --workspaces=false
```

### Workers (via Docker Compose)

```bash
docker compose up -d worker-light worker-default worker-heavy
docker compose logs -f worker-light
docker compose logs -f worker-default
docker compose logs -f worker-heavy
docker compose stop worker-light worker-default worker-heavy
```

### Dedicated scheduler process (recommended in multi-instance deployments)

```bash
uv run python -m backend.workers.scheduler_worker
```

## Queues and workers (light/default/heavy)

Current strategy:

- `light`: short/frequent jobs (higher concurrency)
- `default`: medium jobs
- `heavy`: heavy/long jobs (lower concurrency)

Current Compose profile:

- `worker-light`: `WORKER_CONCURRENCY=8`, `DB_POOL_SIZE=3`
- `worker-default`: `WORKER_CONCURRENCY=3`, `DB_POOL_SIZE=2`
- `worker-heavy`: `WORKER_CONCURRENCY=1`, `DB_POOL_SIZE=1`
- backend API: `DB_POOL_SIZE=6`

This helps keep fast jobs responsive while preventing heavy jobs from monopolizing resources.

## Optional Comics Module (Extra)

The comics feature set is an optional extra. You can use this project purely as a cloud file operations manager.

When enabled, comics workflows can act as a manager for:

- cover extraction
- metadata mapping for comic files
- library-level comic processing jobs

If you do not need it, keep comics queue concurrency low or disable comics-oriented routes/jobs in your deployment policy.

## Useful commands

### Backend

```bash
uv run pytest -q
```

### Frontend

```bash
cd src/frontend
npm.cmd run lint --workspaces=false
npm.cmd run build --workspaces=false
```

### Important endpoints

- Health: `http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/docs`
- Admin settings API: `GET/PUT /api/v1/admin/settings`

## Troubleshooting

### 1) `npx.ps1` blocked in PowerShell

Use `npx.cmd`/`npm.cmd`:

```powershell
npm.cmd run dev --workspaces=false
```

### 2) Old worker containers

When changing services in compose, use:

```bash
docker compose up -d --build --remove-orphans
```

### 3) Worker is not processing jobs

Checklist:

- Redis is running (`docker compose logs -f redis`)
- worker has the correct `WORKER_QUEUE_NAME`
- backend uses the built-in job type queue policy aligned with active workers

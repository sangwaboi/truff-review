# Universal AI Code Reviewer — Shared Context Document

> **Purpose**: This file is the shared knowledge base between **Antigravity (IDE agent)** and **Copilot CLI (terminal agent)**. Both agents read and update this file to stay synchronized. The human operator is **Vishvendra (sangwaboi)**.

> **Last Updated**: 2026-04-13T07:00:00+05:30
> **Updated By**: Copilot CLI

---

## 1. PROJECT IDENTITY

| Field | Value |
|-------|-------|
| **Project** | Universal AI Code Reviewer |
| **Repo** | https://github.com/absolutely-ai/truff-review.git |
| **Local Path** | `/Users/vishvendrasangwa/turff-review` |
| **Language** | Python 3.11 (Docker) / Python 3.9 (local mac) |
| **Framework** | FastAPI |
| **GCP Project** | `code-review-493116` |
| **GCP Region** | `us-central1` |
| **Service Account** | `universal-reviewer@code-review-493116.iam.gserviceaccount.com` |
| **AI Model** | `gemini-3.1-pro` (Vertex AI) |

---

## 2. WHAT THIS PROJECT DOES

A **stateless, event-driven microservice** that:
1. Receives GitHub PR webhook events (`POST /webhook`)
2. Validates HMAC-SHA256 signatures using secrets from GCP Secret Manager
3. Returns `HTTP 202` immediately (satisfies GitHub's 10-second timeout)
4. In a **background task**: authenticates as a GitHub App, gathers PR diffs, filters noise, sends context to Vertex AI (Gemini), and posts **batched** inline review comments back to the PR

### The Request Lifecycle
```
GitHub fires webhook → FastAPI receives → HMAC verify → Event filter
    → HTTP 202 returned to GitHub (< 200ms)
    → Background task starts:
        → JWT auth → Installation Token
        → Fetch PR files + diffs
        → Noise filter (skip .lock, dist/, node_modules/, etc.)
        → Vertex AI inference (structured JSON output)
        → Single pr.create_review() call with all comments batched
```

---

## 3. FILE STRUCTURE (COMPLETE)

```
turff-review/
├── app/
│   ├── __init__.py          # Package init
│   ├── main.py              # FastAPI app: POST /webhook + GET /health
│   ├── security.py          # HMAC-SHA256 signature verification (compare_digest)
│   ├── secrets.py           # GCP Secret Manager client (LRU cached)
│   ├── github_auth.py       # JWT generation (RS256) + Installation Token exchange
│   ├── context.py           # PR diff extraction + noise filtering
│   ├── inference.py         # Vertex AI inference via google-genai SDK
│   ├── reviewer.py          # Background task orchestrator (batched reviews)
│   └── prompt_config.py     # Modular prompt config (3 strictness levels)
├── requirements.txt         # Dependencies
├── Dockerfile               # Cloud Run container (python:3.11-slim)
├── .dockerignore
├── .gitignore
├── README.md
└── Context.md               # ← THIS FILE (shared context between agents)
```

---

## 4. DEPENDENCIES (requirements.txt)

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
google-cloud-secret-manager>=2.22.0
google-genai>=1.14.0              # NOT the deprecated google-cloud-aiplatform
PyGithub>=2.6.0
PyJWT[crypto]>=2.10.0
requests>=2.32.0
pydantic>=2.10.0
```

### Why google-genai and NOT google-cloud-aiplatform?
The `vertexai.generative_models` module inside `google-cloud-aiplatform` was **deprecated June 24, 2025** and is scheduled for removal June 24, 2026. Google's official replacement is the `google-genai` SDK (`from google import genai`).

---

## 5. GCP SECRETS (CONFIRMED)

All three secrets exist in GCP Secret Manager under project `code-review-493116`:

| Secret ID | Purpose | Value (partial) |
|-----------|---------|-----------------|
| `github-app-id` | GitHub App ID (integer) | `3356708` |
| `github-private-key` | GitHub App `.pem` private key | (in GCP) |
| `github-webhook-secret` | HMAC webhook signing secret | `byqwe9-kavJum-bankoh...` |

These are fetched at runtime via `app/secrets.py` using `google.cloud.secretmanager`. Results are LRU-cached per container lifecycle.

---

## 6. KEY ARCHITECTURAL DECISIONS

### 6.1 Batched Review Comments (CRITICAL)
- **DO NOT** use individual `pr.create_review_comment()` calls
- **DO** use a single `pr.create_review(event="COMMENT", comments=[...])` call
- **Why**: If a PR has 12 issues and you fire 12 rapid sequential requests, GitHub's secondary abuse limits will temporarily shadowban the App
- **Implementation**: `app/reviewer.py` builds a `review_comments` list and submits once

### 6.2 Background Task Architecture
- FastAPI's `BackgroundTasks` is used (not Celery, not threads)
- The webhook endpoint returns 202 BEFORE processing starts
- This satisfies GitHub's strict 10-second webhook timeout rule

### 6.3 Noise Filtering
- `app/context.py` filters these BEFORE hitting Vertex AI:
  - **Extensions**: `.lock`, `.csv`, `.svg`, `.png`, `.jpg`, `.map`, `.min.js`, `.min.css`, etc.
  - **Filenames**: `package-lock.json`, `yarn.lock`, `poetry.lock`, `Cargo.lock`, `go.sum`, etc.
  - **Directories**: `dist/`, `build/`, `node_modules/`, `.next/`, `vendor/`, `__pycache__/`, etc.
- If ALL files are filtered out → pipeline aborts, no Vertex AI call (saves compute budget)

### 6.4 Prompt Strictness Levels
- Configurable in `app/prompt_config.py` via `ACTIVE_STRICTNESS`
- Options: `STRICT`, `MODERATE` (current default), `LENIENT`
- Prompt is grounded in Ozumax's architecture: PostgreSQL + Redis, N+1 queries, high-throughput logistics

### 6.5 Python 3.9 Compatibility
- Local Mac runs Python 3.9.6 (system python)
- Docker uses Python 3.11-slim
- All files use `from __future__ import annotations` for deferred type evaluation
- FastAPI parameters use `Optional[str]` instead of `str | None` because FastAPI evaluates annotations at runtime even with `__future__` imports

---

## 7. WHAT HAS BEEN COMPLETED

### Build Phase ✅
- [x] All 9 Python modules written and validated
- [x] AST syntax validation passed on all files
- [x] Full import chain works (all 8 modules import without errors)
- [x] Noise filter unit tests (8 assertions passed)
- [x] Prompt assembly validation (repo name, diff, strictness, domain context)
- [x] Pydantic ReviewComment model validation
- [x] `venv` created with all deps installed locally
- [x] Code pushed to GitHub

### Local Testing Phase ✅
- [x] GCP Auth: `gcloud auth application-default login` (authenticated as `cmo@theozu.com`)
- [x] IAM Fix: Granted `claude-vertex@agen8-486719.iam.gserviceaccount.com` `roles/secretmanager.secretAccessor` on all 3 secrets
- [x] Uvicorn: Started on `http://127.0.0.1:8080` (PID: 17646)
- [x] Health endpoint: `{"status":"healthy","service":"universal-ai-reviewer"}`
- [x] ngrok: Tunnel active at `https://pauletta-coercionary-unglacially.ngrok-free.dev`
- [x] HMAC verification: Working correctly (rejects invalid signatures)
- [x] Manual webhook test with proper HMAC: Returns `202 Accepted`
- [x] Repo transferred to `absolutely-ai` org

### What Has NOT Been Done Yet ❌
- [ ] **CRITICAL**: GitHub App webhook URL was pointing to `https://www.agen8.io/webhook` (wrong!)
  - User updated it but we haven't confirmed it's now pointing to ngrok URL
- [ ] Confirm GitHub App is installed on `absolutely-ai/truff-review`
- [ ] End-to-end test: Real PR event from GitHub should trigger full pipeline
- [ ] Verify Vertex AI inference works end-to-end
- [ ] Cloud Run deployment (DO NOT deploy yet — validate locally first)

---

## 8. CURRENT INFRASTRUCTURE

| Component | Value |
|-----------|-------|
| **Uvicorn** | Running on `http://127.0.0.1:8080` (PID: 17646) |
| **ngrok URL** | `https://pauletta-coercionary-unglacially.ngrok-free.dev` |
| **Webhook URL** | Should be `https://pauletta-coercionary-unglacially.ngrok-free.dev/webhook` |
| **GitHub App** | `truff-review` under absolutely-ai org |
| **App ID** | `3356708` |
| **Installation ID** | `3356708` (same as app_id for org-level installation) |

---

## 9. DEBUGGING DISCOVERIES

### Discovery 1: Wrong Webhook URL
The GitHub App's webhook URL was configured to `https://www.agen8.io/webhook` (an old Vercel URL) instead of the ngrok tunnel. All webhook deliveries were going to Vercel and returning 404.

**Fix**: User updated the webhook URL in GitHub App settings.

### Discovery 2: IAM Permission Issue
The `claude-vertex@agen8-486719.iam.gserviceaccount.com` service account (used via `GOOGLE_APPLICATION_CREDENTIALS`) did not have access to the secrets in `code-review-493116` project.

**Fix**: Granted `roles/secretmanager.secretAccessor` on all 3 secrets to `claude-vertex` SA.

### Discovery 3: Webhook Secret Mismatch
If the webhook secret in GitHub App settings doesn't match the `github-webhook-secret` in GCP, GitHub will fail deliveries silently.

**Current secret in GCP**: `byqwe9-kavJum-bankoh...`

### Discovery 4: Manual HMAC Test Works
When sending a test request with proper HMAC signature, the endpoint correctly returns:
```json
{"message":"Accepted","status":"processing in background","event":"pull_request","action":"opened"}
HTTP 202
```

But the background task failed with: `Malformed webhook payload — missing key: 'installation'`

This is because my manual test payload was simplified and didn't include the full GitHub webhook structure with `installation` object.

### Discovery 5: URL TLD Mismatch (.app vs .dev) ⚠️ CRITICAL
**Found by**: Antigravity (Session 3)

The ngrok tunnel runs on `.ngrok-free.dev` but the GitHub App webhook settings show `.ngrok-free.app`:

| Where | URL |
|-------|-----|
| **ngrok actual** | `https://pauletta-coercionary-unglacially.ngrok-free.dev` |
| **GitHub setting** (screenshot) | `https://pauletta-coercionary-unglacially.ngrok-free.app/webhook` |

**Fix**: Update GitHub App webhook URL to exactly:
```
https://pauletta-coercionary-unglacially.ngrok-free.dev/webhook
```

### Discovery 6: GitHub Redeliveries Don't Change URLs
**Found by**: Antigravity (Session 3)

GitHub webhook "Redeliver" replays the delivery to the URL that was configured **at the time of the original event**. Old deliveries went to `agen8.io`. Clicking Redeliver sends them back to `agen8.io` — NOT to the new ngrok URL.

**Fix**: After fixing the webhook URL, you must trigger a **new event** (push a commit to PR #2 or open a new PR). Do NOT use "Redeliver" — it will always use the old URL.

---

## 10. ENVIRONMENT INFO

| Item | Value |
|------|-------|
| **OS** | macOS |
| **Local Python** | 3.9.6 (system) |
| **Docker Python** | 3.11-slim |
| **Venv Location** | `/Users/vishvendrasangwa/turff-review/venv` |
| **Venv Activate** | `source /Users/vishvendrasangwa/turff-review/venv/bin/activate` |
| **GCP Auth** | Application Default Credentials active (cmo@theozu.com) |
| **GitHub CLI** | Authenticated as sangwaboi |
| **GitHub Repo** | https://github.com/absolutely-ai/truff-review.git |
| **Test Branch** | `test-e2e-1776042386` |
| **Test PR** | https://github.com/absolutely-ai/truff-review/pull/2 |

---

## 11. CHANGE LOG

### Session 1 (2026-04-13, Antigravity)
1. **Created entire project from scratch** — 14 files, 1166 lines
2. **Corrected PRD's deprecated SDK** — `google-cloud-aiplatform` → `google-genai`
3. **Corrected PyGithub API** — `commit_id` (string) → `commit` (Commit object)
4. **Fixed Python 3.9 compat** — `str | None` → `Optional[str]` with `from __future__ import annotations`
5. **Implemented batched reviews** — single `pr.create_review()` instead of N × `create_review_comment()`
6. **Updated model** — `gemini-3.1-pro-preview` → `gemini-3.1-pro` (stable)
7. **Pushed to GitHub** — https://github.com/absolutely-ai/truff-review.git
8. **Validated** — all imports, noise filter, prompt assembly, Pydantic models pass

### Session 2 (Copilot CLI — 2026-04-13, 06:30-07:00 IST)

**Status**: Local testing infrastructure ready. Webhook endpoint working. **Waiting for user to confirm webhook URL is correct and GitHub App is installed on repo.**

**What Was Done**:
1. **GCP Auth**: Ran `gcloud auth application-default login` — authenticated as `cmo@theozu.com`
2. **IAM Fix**: Granted `claude-vertex@agen8-486719.iam.gserviceaccount.com` `roles/secretmanager.secretAccessor` on all 3 secrets in `code-review-493116`
3. **Uvicorn**: Started successfully on `http://127.0.0.1:8080` (PID: 17646)
4. **Health Check**: `curl localhost:8080/health` → `{"status":"healthy"}`
5. **ngrok**: Tunnel active at `https://pauletta-coercionary-unglacially.ngrok-free.dev`
6. **Webhook URL discovery**: Found it was pointing to `https://www.agen8.io/webhook` (Vercel) — user corrected
7. **Manual HMAC test**: Endpoint correctly returns 202 Accepted with proper signature
8. **Repo transfer**: Changed remote from `sangwaboi/truff-review` to `absolutely-ai/truff-review`
9. **Test PR created**: https://github.com/absolutely-ai/truff-review/pull/2

**Current Problem**:
- GitHub is not sending webhook requests to ngrok tunnel
- Possible causes:
  1. Webhook URL still not updated correctly
  2. GitHub App not installed on `absolutely-ai/truff-review`
  3. Webhook secret mismatch

**Next Steps for Antigravity (or next CLI session)**:
1. Verify webhook URL in GitHub App is exactly: `https://pauletta-coercionary-unglacially.ngrok-free.app/webhook`
2. Verify webhook secret matches: `byqwe9-kavJum-bankoh...`
3. Verify GitHub App is installed on `absolutely-ai/truff-review` repo
4. If webhook still not reaching, check "Recent Deliveries" in GitHub App settings
5. Once real webhook arrives with `installation` key, full E2E pipeline should execute

### Session 3 (Antigravity — 2026-04-13, 07:05 IST)

**Status**: Diagnosed two root causes for webhooks not reaching ngrok.

**Findings**:
1. **URL TLD mismatch**: GitHub has `.ngrok-free.app` but ngrok is on `.ngrok-free.dev` — different domains!
2. **Redelivery misunderstanding**: GitHub redeliveries replay to the ORIGINAL URL, not the current one — user was redelivering to `agen8.io`
3. **Confirmed**: Uvicorn (PID 17646) and ngrok are both still running and healthy

**Action Required from User**:
1. Go to GitHub App settings → change webhook URL to exactly: `https://pauletta-coercionary-unglacially.ngrok-free.dev/webhook` (note: `.dev` not `.app`)
2. Click "Save changes"
3. Then trigger a **new** event — either push a commit to PR #2 or open a new PR (do NOT use Redeliver)

---

## 12. RULES FOR AGENTS

1. **Always activate venv first**: `source /Users/vishvendrasangwa/turff-review/venv/bin/activate`
2. **Never hardcode credentials** — all secrets come from GCP Secret Manager at runtime
3. **Never store code to disk during processing** — all PR data stays in memory (P0 requirement)
4. **Never deploy to Cloud Run before local validation passes** — test with ngrok first
5. **After making changes**: run `source venv/bin/activate && python3 -c "from app.main import app; print('OK')"` to validate imports
6. **After any code change**: commit and push to `origin main`
7. **Update this Context.md** after significant actions so the other agent can pick up context
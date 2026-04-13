# Universal AI Code Reviewer — Shared Context Document

> **Purpose**: This file is the shared knowledge base between **Antigravity (IDE agent)** and **Copilot CLI (terminal agent)**. Both agents read and update this file to stay synchronized. The human operator is **Vishvendra (sangwaboi)**.

> **Last Updated**: 2026-04-13T07:50:00+05:30
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
| **Service Account** | `universal-ai-reviewer-893@code-review-493116.iam.gserviceaccount.com` |
| **Cloud Run URL** | `https://universal-ai-reviewer-944575899427.us-central1.run.app` |
| **AI Models** | `gemini-2.5-flash` (fast review) + `gemini-2.5-pro` (deep analysis) |

---

## 2. WHAT THIS PROJECT DOES

A **stateless, event-driven microservice** that:
1. Receives GitHub PR webhook events (`POST /webhook`)
2. Validates HMAC-SHA256 signatures using secrets from GCP Secret Manager
3. Returns `HTTP 202` immediately (satisfies GitHub's 10-second timeout)
4. In a **background task**: runs **two-pass AI review**:
   - **Pass 1 (Flash)**: Fast scan → catches obvious issues
   - **Pass 2 (Pro)**: Deep analysis → finds root causes and architectural problems
5. Posts **batched** inline review comments back to the PR

### The Request Lifecycle
```
GitHub fires webhook → FastAPI receives → HMAC verify → Event filter
    → HTTP 202 returned to GitHub (< 200ms)
    → Background task starts:
        → JWT auth → Installation Token
        → Fetch PR files + diffs
        → Noise filter (skip .lock, dist/, node_modules/, etc.)
        → PASS 1: execute_review() with gemini-2.5-flash
        → PASS 2: execute_deep_analysis() with gemini-2.5-pro (if flash found issues)
        → Single pr.create_review() call with ALL comments batched
```

---

## 3. FILE STRUCTURE (COMPLETE)

```
truff-review/
├── app/
│   ├── __init__.py          # Package init
│   ├── main.py              # FastAPI app: POST /webhook + GET /health
│   ├── security.py          # HMAC-SHA256 signature verification (compare_digest)
│   ├── secrets.py           # GCP Secret Manager client (LRU cached)
│   ├── github_auth.py       # JWT generation (RS256) + Installation Token exchange
│   ├── context.py           # PR diff extraction + noise filtering
│   ├── inference.py         # Vertex AI inference: execute_review() + execute_deep_analysis()
│   ├── reviewer.py          # Background task orchestrator (two-pass review)
│   └── prompt_config.py     # Modular prompt config: build_prompt() + build_deep_prompt()
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
The `vertexai.generative_models` module inside `google-cloud-aiplatform` was **deprecated June 24, 2025** and is scheduled for removal June 24, 2026**. Google's official replacement is the `google-genai` SDK (`from google import genai`).

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

### 6.1 Two-Pass AI Review (CRITICAL)
- **Pass 1**: `execute_review()` → `gemini-2.5-flash` (fast, catches obvious issues)
- **Pass 2**: `execute_deep_analysis()` → `gemini-2.5-pro` (deep, finds root causes)
- Both pass results are combined and posted in a **single** `pr.create_review()` call
- This ensures comprehensive review without overwhelming GitHub's API rate limits

### 6.2 Batched Review Comments (CRITICAL)
- **DO NOT** use individual `pr.create_review_comment()` calls
- **DO** use a single `pr.create_review(event="COMMENT", comments=[...])` call
- Why: If you fire 12+ rapid sequential requests, GitHub's secondary abuse limits will shadowban the App

### 6.3 Background Task Architecture
- FastAPI's `BackgroundTasks` is used (not Celery, not threads)
- The webhook endpoint returns 202 BEFORE processing starts
- This satisfies GitHub's strict 10-second webhook timeout rule

### 6.4 Noise Filtering
- `app/context.py` filters these BEFORE hitting Vertex AI:
  - **Extensions**: `.lock`, `.csv`, `.svg`, `.png`, `.jpg`, `.map`, `.min.js`, `.min.css`, etc.
  - **Filenames**: `package-lock.json`, `yarn.lock`, `poetry.lock`, `Cargo.lock`, `go.sum`, etc.
  - **Directories**: `dist/`, `build/`, `node_modules/`, `.next/`, `vendor/`, `__pycache__/`, etc.
- If ALL files are filtered out → pipeline aborts, no Vertex AI call (saves compute budget)

### 6.5 Python 3.9/3.11 Compatibility
- Local Mac runs Python 3.9.6 (system python)
- Docker uses Python 3.11-slim
- All files use `from __future__ import annotations` for deferred type evaluation
- FastAPI parameters use `Optional[str]` instead of `str | None` because FastAPI evaluates annotations at runtime

### 6.6 Review Strictness: STRICT (current)
- Set in `app/reviewer.py`: `strictness = "STRICT_"`
- This means every issue is flagged — no filtering of AI findings

---

## 7. WHAT HAS BEEN COMPLETED

### Build Phase ✅
- [x] All 9 Python modules written and validated
- [x] AST syntax validation passed on all files
- [x] Full import chain works (all modules import without errors)
- [x] Noise filter unit tests (8 assertions passed)
- [x] Prompt assembly validation (repo name, diff, strictness, domain context)
- [x] Pydantic ReviewComment model validation
- [x] `venv` created with all deps installed locally
- [x] Code pushed to GitHub

### E2E Testing Phase ✅
- [x] GCP Auth: `gcloud auth application-default login`
- [x] IAM Fix: Granted service accounts access to secrets
- [x] Local Uvicorn: Running and healthy
- [x] ngrok: Tunnel active for local testing
- [x] HMAC verification: Working correctly
- [x] Manual webhook test: Returns `202 Accepted` with proper signature
- [x] Repo transferred to `absolutely-ai` org

### First Live Review ✅
- [x] First PR reviewed successfully on `absolutely-ai/truff-review`
- [x] Flash model found issues, Pro model did deep analysis
- [x] Comments posted to PR successfully

### Cloud Run Deployment ✅
- [x] Docker image built locally with `--platform linux/amd64`
- [x] Pushed to Artifact Registry
- [x] Deployed to Cloud Run: `https://universal-ai-reviewer-944575899427.us-central1.run.app`
- [x] IAM roles properly configured

---

## 8. CURRENT INFRASTRUCTURE

| Component | Value |
|-----------|-------|
| **Cloud Run** | `https://universal-ai-reviewer-944575899427.us-central1.run.app` |
| **GCP Project** | `code-review-493116` |
| **Service Account** | `universal-ai-reviewer-893@code-review-493116.iam.gserviceaccount.com` |
| **GitHub App** | `truff-review` under absolutely-ai org |
| **App ID** | `3356708` |
| **Installation ID** | `3356708` |
| **Models** | `gemini-2.5-flash` (fast) + `gemini-2.5-pro` (deep) |

---

## 9. DEBUGGING DISCOVERIES

### Discovery 1: Wrong Webhook URL (FIXED)
The GitHub App's webhook URL was configured to `https://www.agen8.io/webhook` (Vercel). All webhook deliveries were going to Vercel and returning 404.

**Fix**: Updated webhook URL to Cloud Run URL.

### Discovery 2: IAM Permission Issue (FIXED)
The service account used for local dev (`claude-vertex@agen8-486719.iam.gserviceaccount.com`) lacked access to `code-review-493116` secrets.

**Fix**: Granted `roles/secretmanager.secretAccessor` on all 3 secrets.

### Discovery 3: Docker Platform Issue (FIXED)
Cloud Run requires `linux/amd64` platform images. Apple Silicon builds create ARM64 images that are rejected.

**Fix**: Used `docker buildx build --platform linux/amd64` to build compatible images.

### Discovery 4: Two-Pass Review Architecture
First review was shallow. Discovered that running a second "deep analysis" pass with the Pro model catches architectural issues and root causes that Flash misses.

**Solution**: Implemented two-pass architecture with `execute_deep_analysis()`.

---

## 10. ENVIRONMENT INFO

| Item | Value |
|------|-------|
| **OS** | macOS |
| **Local Python** | 3.9.6 (system) |
| **Docker Python** | 3.11-slim |
| **Venv Location** | `/Users/vishvendrasangwa/turff-review/venv` |
| **Venv Activate** | `source /Users/vishvendrasangwa/turff-review/venv/bin/activate` |
| **GCP Auth** | Application Default Credentials active |
| **GitHub CLI** | Authenticated as sangwaboi |
| **GitHub Repo** | https://github.com/absolutely-ai/truff-review.git |
| **Branch** | `main` (merged from `test-ai-reviewer-live`) |

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
**Status**: Local testing infrastructure ready.

**What Was Done**:
1. GCP Auth: authenticated as `cmo@theozu.com`
2. IAM Fix: Granted `claude-vertex` SA access to all 3 secrets
3. Uvicorn: Started on port 8080
4. ngrok: Tunnel active at `https://pauletta-coercionary-unglacially.ngrok-free.dev`
5. Repo transfer: Changed remote from `sangwaboi/truff-review` to `absolutely-ai/truff-review`
6. Webhook URL issue discovered (was pointing to Vercel)

### Session 3 (Copilot CLI — 2026-04-13, ~07:15 IST)
**Status**: Cloud Run deployment completed. Service is live.

**What Was Done**:
1. Built Docker image locally with `docker buildx build --platform linux/amd64`
2. Pushed to Artifact Registry: `us-central1-docker.pkg.dev/code-review-493116/cloud-run-source-deploy/universal-ai-reviewer:v2`
3. Deployed to Cloud Run: `https://universal-ai-reviewer-944575899427.us-central1.run.app`
4. Resolved IAM issues for deployment

### Session 4 (Copilot CLI — 2026-04-13, ~07:50 IST)
**Status**: Two-pass review system implemented and working. First live PR reviewed successfully.

**What Was Done**:
1. Added `execute_deep_analysis()` in inference.py for gemini-2.5-pro second pass
2. Updated reviewer.py to orchestrate two-pass review (flash → pro)
3. Added `build_deep_prompt()` in prompt_config.py
4. Updated main.py to support 'reopened' action in addition to 'opened' and 'synchronize'
5. Changed strictness to STRICT (all issues flagged)
6. Merged `test-ai-reviewer-live` branch into `main`
7. Pushed all code to origin

---

## 12. RULES FOR AGENTS

1. **Always activate venv first**: `source /Users/vishvendrasangwa/turff-review/venv/bin/activate`
2. **Never hardcode credentials** — all secrets come from GCP Secret Manager at runtime
3. **Never store code to disk during processing** — all PR data stays in memory (P0 requirement)
4. **Deploy to Cloud Run only after local validation passes**
5. **After making changes**: run `source venv/bin/activate && python3 -c "from app.main import app; print('OK')"` to validate imports
6. **After any code change**: commit and push to `origin main`
7. **Update this Context.md** after significant actions so the other agent can pick up context
8. **Two-pass review**: Always run flash first, then pro for deep analysis when issues are found
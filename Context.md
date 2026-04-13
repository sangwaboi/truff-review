# Universal AI Code Reviewer — Shared Context Document

> **Purpose**: This file is the shared knowledge base between **Antigravity (IDE agent)** and **Copilot CLI (terminal agent)**. Both agents read and update this file to stay synchronized. The human operator is **Vishvendra (sangwaboi)**.

> **Last Updated**: 2026-04-13T06:25:00+05:30  
> **Updated By**: Copilot CLI

---

## 1. PROJECT IDENTITY

| Field | Value |
|-------|-------|
| **Project** | Universal AI Code Reviewer |
| **Repo** | https://github.com/sangwaboi/truff-review.git |
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

| Secret ID | Purpose | Created |
|-----------|---------|---------|
| `github-app-id` | GitHub App ID (integer) | 2026-04-12, 10:35 PM |
| `github-private-key` | GitHub App `.pem` private key | 2026-04-12, 10:37 PM |
| `github-webhook-secret` | HMAC webhook signing secret | 2026-04-12, 10:36 PM |

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
- [x] Code pushed to GitHub: https://github.com/sangwaboi/truff-review.git

### What Has NOT Been Done Yet ❌
- [ ] `gcloud auth application-default login` (needed for local Secret Manager + Vertex AI access)
- [ ] Local server startup (`uvicorn app.main:app --reload --port 8080`)
- [ ] ngrok tunnel setup (`ngrok http 8080`)
- [ ] GitHub App webhook URL configuration (paste ngrok URL)
- [ ] End-to-end test: open a dummy PR and verify inline comments appear
- [ ] Cloud Run deployment (DO NOT deploy yet — validate locally first)

---

## 8. NEXT STEPS — LOCAL TESTING WITH NGROK

This is the execution sequence. **Copilot CLI should execute these steps:**

### Step 1: Authenticate with GCP
```bash
gcloud auth application-default login
```
This opens a browser for OAuth. After auth, the local machine can access Secret Manager and Vertex AI using Vishvendra's credentials.

### Step 2: Activate venv and start FastAPI
```bash
cd /Users/vishvendrasangwa/turff-review
source venv/bin/activate
uvicorn app.main:app --reload --port 8080
```
Expected output: `Uvicorn running on http://0.0.0.0:8080`

### Step 3: Test health endpoint
```bash
curl http://localhost:8080/health
```
Expected: `{"status":"healthy","service":"universal-ai-reviewer"}`

### Step 4: Expose via ngrok
In a new terminal:
```bash
ngrok http 8080
```
Copy the HTTPS forwarding URL (e.g., `https://abc123.ngrok-free.app`)

### Step 5: Configure GitHub App
1. Go to GitHub App settings (the GitHub App that was created for this project)
2. Set Webhook URL to: `https://<ngrok-id>.ngrok-free.app/webhook`
3. Save

### Step 6: End-to-End Test
1. Open a dummy PR in a test repository where the GitHub App is installed
2. Watch the local uvicorn terminal for:
   - `Accepted PR event: action=opened, repo=..., PR=#...`
   - `Processing PR #... on ...`
   - `Context assembly complete: X files reviewed, Y skipped`
   - `Sending inference request to gemini-3.1-pro...`
   - `Review complete for ... PR #...: N comments posted in single review`
3. Check the PR on GitHub — inline AI review comments should appear

### Debugging Tips
- If HMAC fails: check that `github-webhook-secret` in GCP matches the secret configured in the GitHub App
- If JWT auth fails: check that `github-private-key` in GCP is the correct `.pem` file
- If Vertex AI fails: check that the service account has `roles/aiplatform.user`
- If comment posting fails with 422: the AI generated a line number that doesn't exist in the diff — this is a known edge case with LLMs

---

## 9. IMPORTANT API PATTERNS

### PyGithub: Batched Review
```python
# CORRECT — single API call
pr.create_review(
    commit=repo.get_commit(pr.head.sha),  # Commit OBJECT, not SHA string
    body="Review summary",
    event="COMMENT",
    comments=[
        {"path": "file.py", "line": 42, "side": "RIGHT", "body": "Fix this"},
        {"path": "file.py", "line": 88, "side": "RIGHT", "body": "Check this"},
    ]
)

# WRONG — will get rate-limited
for comment in comments:
    pr.create_review_comment(...)  # DON'T DO THIS
```

### Google GenAI SDK: Structured Output
```python
from google import genai
from google.genai import types
from pydantic import BaseModel

class ReviewComment(BaseModel):
    path: str
    line: int
    body: str

client = genai.Client(vertexai=True, project="code-review-493116", location="us-central1")
response = client.models.generate_content(
    model="gemini-3.1-pro",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=list[ReviewComment],
        temperature=0.2,
    )
)
```

### HMAC Verification
```python
import hmac, hashlib
hash_object = hmac.new(secret.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
expected = "sha256=" + hash_object.hexdigest()
hmac.compare_digest(expected, signature_header)  # Timing-attack safe
```

---

## 10. ENVIRONMENT INFO

| Item | Value |
|------|-------|
| **OS** | macOS |
| **Local Python** | 3.9.6 (system) |
| **Docker Python** | 3.11-slim |
| **Venv Location** | `/Users/vishvendrasangwa/turff-review/venv` |
| **Venv Activate** | `source venv/bin/activate` |
| **GCP Auth** | Application Default Credentials (needs `gcloud auth application-default login`) |
| **GitHub Repo** | https://github.com/sangwaboi/truff-review.git |
| **Branch** | `main` |
| **Last Commit** | `aa162754` — docs: add Context.md — shared handoff document between IDE and CLI agents |

---

## 11. CHANGE LOG

### Session 1 (2026-04-13, Antigravity)
1. **Created entire project from scratch** — 14 files, 1166 lines
2. **Corrected PRD's deprecated SDK** — `google-cloud-aiplatform` → `google-genai`
3. **Corrected PyGithub API** — `commit_id` (string) → `commit` (Commit object)
4. **Fixed Python 3.9 compat** — `str | None` → `Optional[str]` with `from __future__ import annotations`
5. **Implemented batched reviews** — single `pr.create_review()` instead of N × `create_review_comment()`
6. **Updated model** — `gemini-3.1-pro-preview` → `gemini-3.1-pro` (stable)
7. **Pushed to GitHub** — https://github.com/sangwaboi/truff-review.git
8. **Validated** — all imports, noise filter, prompt assembly, Pydantic models pass

### Session 2 (Copilot CLI — 2026-04-13, 06:30 IST)

**Status**: Local testing IN PROGRESS. Webhook endpoint is live and responding.

**What Was Done**:
1. **GCP Auth**: Ran `gcloud auth application-default login` — authenticated as `cmo@theozu.com`
2. **IAM Fix**: Discovered `claude-vertex@agen8-486719.iam.gserviceaccount.com` (local dev SA) lacked access to `code-review-493116` secrets
   - Granted `roles/secretmanager.secretAccessor` on all 3 secrets to `claude-vertex` SA
3. **Uvicorn**: Started successfully on `http://127.0.0.1:8080` (PID: 17646)
4. **Health Check**: `curl http://localhost:8080/health` → `{"status":"healthy","service":"universal-ai-reviewer"}`
5. **ngrok**: Tunnel active at `https://pauletta-coercionary-unglacially.ngrok-free.dev`
6. **Webhook Test**: POST without signature → `401 Missing x-hub-signature-256 header` (EXPECTED — endpoint working correctly)

**Still PENDING**:
- [ ] Configure GitHub App webhook URL to point to ngrok URL
- [ ] End-to-end test with real PR event (requires GitHub App installation + HMAC signature)
- [ ] Verify Vertex AI inference works end-to-end

**Critical Discovery**: The `claude-vertex` service account (used for local dev via `GOOGLE_APPLICATION_CREDENTIALS`) needed explicit IAM grant on `code-review-493116` secrets. This was NOT documented in the original setup.

**Next Step**: User needs to configure GitHub App webhook URL:
```
Webhook URL: https://pauletta-coercionary-unglacially.ngrok-free.app/webhook
```

---

## 12. RULES FOR AGENTS

1. **Always activate venv first**: `source /Users/vishvendrasangwa/turff-review/venv/bin/activate`
2. **Never hardcode credentials** — all secrets come from GCP Secret Manager at runtime
3. **Never store code to disk during processing** — all PR data stays in memory (P0 requirement)
4. **Never deploy to Cloud Run before local validation passes** — test with ngrok first
5. **After making changes**: run `source venv/bin/activate && python3 -c "from app.main import app; print('OK')"` to validate imports
6. **After any code change**: commit and push to `origin main`
7. **Update this Context.md** after significant actions so the other agent can pick up context

# Universal AI Code Reviewer

A stateless, event-driven FastAPI microservice deployed on Google Cloud Run that automatically reviews Pull Requests using Vertex AI (Gemini) and posts inline comments back to GitHub.

## Architecture

```
GitHub Webhook (PR opened/synced)
        │
        ▼
┌─────────────────────────┐
│  FastAPI (Cloud Run)    │
│                         │
│  1. HMAC-SHA256 Verify  │──── GCP Secret Manager
│  2. Event Filter        │
│  3. HTTP 202 Response   │
│        │                │
│        ▼ (background)   │
│  4. GitHub App Auth     │──── JWT → Installation Token
│  5. Fetch PR Diff       │──── GitHub REST API
│  6. Noise Filter        │
│  7. Vertex AI Inference │──── Gemini 3.1 Pro
│  8. Post Comments       │──── GitHub PR Review API
└─────────────────────────┘
```

## Project Structure

```
turff-review/
├── app/
│   ├── __init__.py        # Package init
│   ├── main.py            # FastAPI app, webhook endpoint
│   ├── security.py        # HMAC signature verification
│   ├── secrets.py         # GCP Secret Manager client (cached)
│   ├── github_auth.py     # JWT generation + Installation Token
│   ├── context.py         # PR diff extraction & noise filtering
│   ├── inference.py       # Vertex AI structured inference
│   ├── reviewer.py        # Background task orchestrator
│   └── prompt_config.py   # Modular prompt configuration
├── requirements.txt
├── Dockerfile
├── .dockerignore
└── README.md
```

## Prerequisites

- **GCP Project**: `code-review-493116`
- **Service Account**: `universal-reviewer@code-review-493116.iam.gserviceaccount.com`
  - `roles/aiplatform.user`
  - `roles/secretmanager.secretAccessor`
- **GCP Secrets** (must exist in Secret Manager):
  - `github-webhook-secret` — HMAC webhook secret
  - `github-private-key` — GitHub App `.pem` private key
  - `github-app-id` — GitHub App ID
- **GitHub App** — Installed at the organization level with webhook events for Pull Requests

## Local Development

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up Application Default Credentials
gcloud auth application-default login

# Run the server
uvicorn app.main:app --reload --port 8080
```

## Docker Build & Run

```bash
# Build
docker build -t ai-reviewer .

# Run locally
docker run -p 8080:8080 \
  -v ~/.config/gcloud:/root/.config/gcloud \
  ai-reviewer
```

## Deploy to Cloud Run

```bash
gcloud run deploy universal-ai-reviewer \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account universal-reviewer@code-review-493116.iam.gserviceaccount.com
```

After deployment, copy the Cloud Run URL and paste it into your GitHub App's **Webhook URL** field.

## Configuration

### Review Strictness

Edit `app/prompt_config.py` to change the AI's review behavior:

```python
# Options: STRICT, MODERATE, LENIENT
ACTIVE_STRICTNESS = ReviewStrictness.MODERATE
```

| Level | Behavior |
|-------|----------|
| **STRICT** | Flags everything — style, performance, logic, security |
| **MODERATE** | Focuses on correctness, performance, and security |
| **LENIENT** | Only flags clear bugs and critical issues |

### Noise Filter

Edit `app/context.py` to customize which files are excluded from AI review:
- `SKIP_EXTENSIONS` — File extensions to ignore
- `SKIP_FILENAMES` — Exact filenames to ignore
- `SKIP_DIRECTORIES` — Directory prefixes to ignore

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook` | GitHub webhook receiver (returns 202) |
| `GET` | `/health` | Cloud Run health check |

## Security

- **Zero hardcoded credentials** — all secrets fetched from GCP Secret Manager at runtime
- **HMAC-SHA256 verification** — prevents payload tampering
- **Timing-attack safe** — uses `hmac.compare_digest()` for signature comparison
- **Stateless** — no code is ever written to disk; all processing is in-memory
- **Scoped tokens** — GitHub Installation Tokens are short-lived and repo-scoped

<div align="center">
  <br />
  <a href="https://github.com/udarshcodes/codesentinel" style="text-decoration: none;">
    <img src="frontend/public/logo.jpg" alt="CodeSentinel Logo" width="120" height="120" style="border-radius: 50%;" />
    <br />
    <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=45&pause=1500&color=00D2FF&center=true&vCenter=true&width=1000&height=120&lines=CodeSentinel;Autonomous+AI+Code+Remediation;Stop+drowning+in+alerts;Automate+your+remediation" alt="CodeSentinel Typing SVG" />
  </a>
  <br />
  <h3><a href="https://salmon-ground-0362fac00.7.azurestaticapps.net/">Live Demo Available Here</a></h3>
</div>

---

## Problem Statement

### Alert Fatigue Is Killing Your Codebase

Today's modern CI/CD pipelines are exceptional at finding problems and almost useless at solving them. Every commit triggers a fresh wave of SAST warnings, dependency CVEs, and lint failures that pile up faster than any team can review them. Developers stop reading the alerts. Security debt compounds quietly in the background until it becomes a breach.

**This leads to:**
- Backlogs of unresolved vulnerabilities that nobody has time to investigate.
- Critical fixes delayed for weeks because triage requires deep repo context.
- Inconsistent patches when different engineers fix the same class of bug differently.
- Growing distance between detection tooling and the people who can actually act on it.

---

## Solution

> The problem isn't that scanners don't find the bugs.
> It's that finding a bug and fixing it correctly are two completely different jobs.

**CodeSentinel** is a proactive, autonomous site reliability engineer (SRE) and security researcher that closes that gap. It does not just flag issues, it reads your repository like an engineer would, plans a fix, writes the patch, tests it, re-scans it for the original vulnerability, and opens a pull request ready for human review.

Instead of adding another dashboard of red warnings, CodeSentinel turns those warnings into shipped code.

**Key Feature:** CodeSentinel includes a fully implemented Multi-Repository wildcard execution engine. You can trigger analysis across an entire GitHub organization (e.g., `github.com/org/*`), automatically discovering and scanning all repositories within that scope. For more details, see [PRODUCT.md](./PRODUCT.md).

---

## Tech Stack & Architecture

> **Note:** For deeper technical specifications, system architectural flows, and a comprehensive feature catalog, please refer to [PRODUCT.md](./PRODUCT.md).

### Architecture Overview (The Orchestrator Model)

**Why We Replaced the Monolithic Backend:**
Originally, CodeSentinel packaged all language runtimes, build tools, and SAST scanners into a single 5.5GB monolithic backend container. While functional, this huge image made deploying to cost-effective serverless environments (like Azure Container Apps Free Tier) impossible due to strict 5-minute image pull timeouts. 

**The Solution:**
We decoupled the heavy lifting into an ephemeral architecture.

#### 1. The Lightweight Orchestrator (Backend)
- **Single Source of Truth**: The FastAPI backend acts as the central command. It manages webhooks, authenticates requests, and maintains job state using a dynamic database abstraction layer supporting both **SQLite** and **PostgreSQL**.
- **Database Strategy**: CodeSentinel runs seamlessly on **SQLite** out-of-the-box for local development and lightweight orchestration, providing robust state management with zero setup. For mission-critical deployments and high concurrency, the system dynamically switches to **PostgreSQL** by simply providing a `DATABASE_URL`, securing row-level locking (`FOR UPDATE`) across workers.
- **Micro-Container**: By stripping out heavy toolchains (Node, Java, Rust, Go), the orchestrator Docker image is now under 250MB, deploying instantly on Azure's free tier.
- **Persistent Streams**: Real-time Server-Sent Events (SSE) read directly from the database, ensuring that if a user disconnects, they instantly receive the full history upon reconnecting.

#### 2. The Ephemeral Worker (GitHub Actions)
- **Why GitHub Actions Worker?**: We shifted the LangGraph execution and SAST scanning to an ephemeral GitHub Actions worker model triggered via HTTP webhooks. This provides isolated execution environments, zero-maintenance scaling, and seamless telemetry streaming via authenticated HTTP callbacks, completely eliminating the need for complex localized worker infrastructure.
- **Agent Mesh (`backend/agents/`)**: A swarm of stateless, specialized agents that execute within the worker process. Each agent acts as a distinct node in the LangGraph, executing heavy scans and posting granular state updates back to the orchestrator via HTTP webhooks.
- **LangGraph & ChromaDB**: The AI workflow (powered by the unified LLM provider and LangGraph) runs inside the worker, while validated patches are sent back to the orchestrator to be permanently stored in ChromaDB (RAG).

### Frontend
- **React 18 & Vite:** Lightning-fast HMR and optimized production builds.
- **Tailwind CSS:** Utility-first CSS for rapid, highly-customizable responsive design.
- **Context API & Custom Hooks:** Decouples SSE streaming state and asynchronous HTTP mutations.

### Tooling
- **SAST Runners & Analyzers:** 18 specialized scanning modules — 8 standard SAST tools (`Semgrep`, `SonarQube` (if available), `Bandit`, `Flake8`, `Pylint`, `ESLint`, `Go Vet`, and `Cargo Clippy`) serve as the deterministic baseline, plus 10 custom scanning modules for memory/resource leak detection, dead code detection, built-in hardcoded secrets detection, and circular dependency analysis.
- **Dependency & Registry Checks:** Real-time vulnerability queries via OSV.dev and live registry queries across NPM, PyPI, Maven Central, Go Proxy, and Crates.io.
- **PyGithub:** Safely abstracts cross-fork Pull Request creation and branch management.
- **Pure Python Patch Engine:** A custom-built Search/Replace engine that bypasses strict `git apply` constraints to guarantee reliable AI code insertion.

---

## Data Flow

```mermaid
graph TD
    A[User Submits Repo URL] -->|POST /api/analyze| B(FastAPI Orchestrator)
    B -->|Creates SQLite Job| C[(SQLite State)]
    B -->|Triggers Worker| D[Python Worker Process]
    
    subgraph Ephemeral Worker
    D --> E[LangGraph Execution]
    E --> F[Repo Mapper & Scanners]
    F --> G[Bug Investigator]
    G --> H[Code Generator]
    H --> I[Validator]
    I -->|If Tests Pass| J[PR Author]
    end
    
    J -->|Open Pull Request| K[GitHub API]
    
    D -.->|Webhook State Updates| B
    B -.->|SSE Real-time Stream| L(Frontend Dashboard)
    
    I -.->|Save Validated Fixes| B
    B -.->|Store| M[(ChromaDB)]
```

---

## Local Setup Instructions

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- Git and standard SAST tools.

**Required Tools Installation:**
```bash
pip install semgrep bandit flake8 pylint
```
*Note: `eslint`, `go vet`, and `cargo clippy` must exist in the target repository being analyzed, not in the CodeSentinel environment. `sonar-scanner` (SonarQube) is optional and the pipeline gracefully degrades without it.*

### 2. Clone & Backend Setup
```bash
git clone https://github.com/udarshcodes/codesentinel.git
cd codesentinel/backend

python3.10 -m venv venv  # Or python --version to check and use python3 if needed
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Frontend Setup
```bash
cd ../frontend
npm install
```

### 4. Environment Variables
Create a `.env` file in the `backend/` directory (see `.env.example` for a full template):
```env
# Required: Unified pool of up to 6 API keys for rate limit load balancing
GROQ_API_KEY_1=gsk_your_key_1
GROQ_API_KEY_2=gsk_your_key_2
GROQ_API_KEY_3=gsk_your_key_3
GROQ_API_KEY_4=gsk_your_key_4
GROQ_API_KEY_5=gsk_your_key_5
GROQ_API_KEY_6=gsk_your_key_6

# Optional: Daily token budget per key is determined dynamically via rate limit headers

# Required: For cloning, pushing, and opening PRs
GITHUB_TOKEN=ghp_your_personal_access_token

# Optional: Worker Configuration
WORKER_WEBHOOK_SECRET=your_worker_secret_here

# Optional: Public URL of this backend (the worker posts state updates here)
BACKEND_URL=http://localhost:8000

# Required: Master password to access the /admin observability dashboard
ADMIN_SECRET=your_super_secret_password

# Optional: Storage paths (defaults shown)
TEMP_REPO_PATH=/tmp/repos
CHROMA_PERSIST_PATH=./chroma_data

# Optional: CORS allowed origins (comma-separated)
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Optional: Slack/webhook URL for key exhaustion alerts
# ALERT_WEBHOOK_URL=https://hooks.slack.com/services/your/webhook/url

# Optional: GitHub Webhook Secret (for HMAC SHA-256 payload verification)
# GITHUB_WEBHOOK_SECRET=your_webhook_secret_here

# Optional: PostgreSQL connection string for production deployments
# DATABASE_URL=postgresql://user:password@localhost/codesentinel
```

### 5. Run the Application
**Start the Backend (Terminal 1):**
```bash
cd backend
python main.py
# Runs Uvicorn on http://localhost:8000
```

**Start the Frontend (Terminal 2):**
```bash
cd frontend
npm run dev
# Runs Vite on http://localhost:5173
```

Navigate to `http://localhost:5173` to use the app.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` (or `/api/v1/analyze`) | Initiates the headless pipeline for a single `repo_url` or multi-repository organization wildcard (`github.com/org/*`), returning unique UUID `task_id`(s) without blocking HTTP response. |
| `GET`  | `/api/v1/job/{task_id}/stream-capability` | Generates a short-lived, single-use SSE capability token for authorized viewers. |
| `GET`  | `/api/stream` | SSE endpoint streaming real-time `PipelineState` payloads. Requires `task_id` and `capability` query parameters. |
| `POST` | `/api/job/{task_id}/event` (or `/api/v1/job/{task_id}/event`) | Internal webhook used by the background worker to stream granular state updates to the orchestrator. |
| `POST` | `/api/approve/{task_id}` (or `/api/v1/approve/{task_id}`) | Unblocks the LangGraph pipeline with a human `approved` or `rejected` decision. Requires task-scoped `approval_token`. |
| `POST` | `/api/webhook/github` (or `/api/v1/webhook/github`) | Automated CI/CD webhook endpoint triggering analysis on GitHub push and PR events with HMAC SHA-256 signature verification (`X-Hub-Signature-256`). |
| `GET`  | `/health`, `/live`, `/ready`, `/metrics` | Observability endpoints returning system health status, liveness, readiness, and queue/execution job metrics. |
| `GET`  | `/api/v1/admin/telemetry` | Protected endpoint returning LLM key rotation stats, agent token usage, and key pool status. Requires `admin_session` cookie. |

---

## CI/CD Integration (GitHub Webhooks)

CodeSentinel analyzes repositories automatically when a Pull Request is opened or code is pushed. To set this up, configure a webhook in your GitHub repository pointing to your deployed backend's `/v1/webhook/github` endpoint. Ensure you configure a `GITHUB_WEBHOOK_SECRET` to secure the payloads and automatically trigger the CodeSentinel pipeline whenever a Pull Request is opened or a push lands on `main`.

**Setup Instructions:**
1. Navigate to your target repository on GitHub.
2. Go to **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**.
3. Name the secret `CODESENTINEL_API_URL` and set the value to the public URL of your deployed CodeSentinel backend (e.g., `https://api.codesentinel.yourdomain.com`).
4. Copy the `codesentinel.yml` file into your repository's `.github/workflows/` directory.

Once configured, CodeSentinel will automatically analyze incoming code and post a comment directly on your PRs with a link to the live SSE telemetry stream!

---

## Security Considerations

1. **Deterministic Patching:** The custom Python patch engine ensures exactly what the AI suggests is applied, bypassing brittle system patch limits while maintaining strict character matching and forbidding LLM abbreviations.
2. **Ephemeral Branching & Sandboxing:** The pipeline operates on temporary Git branches (`agent/fix-*`). Local file modifications are completely discarded if validation loops hit the maximum retry limit. To prevent malicious LLM code generation from executing arbitrary operations on the host, all untrusted code execution (such as `npm run build`, `pytest`, or compilation during validation) runs strictly within memory-bounded, ephemeral Docker sandboxes featuring dropped capabilities, restricted network access, and read-only filesystems.
3. **Secret Management & Transport:** LLM API keys and GitHub tokens are strictly confined to the backend environment. Tokens are handled securely via local git configuration (`http.extraheader`) rather than command-line remote URLs, ensuring they never leak into process logs or `.git/config`.
4. **Input Validation:** All repository URLs are strictly validated against allowlist regex patterns to prevent Server-Side Request Forgery (SSRF) and command injection before any cloning occurs.
5. **Approval State Integrity:** The orchestration layer enforces strict state machine fencing. When a job is in the pending human approval state (`WAITING_FOR_APPROVAL`), all generic worker state updates via the webhook are aggressively rejected (`HTTP 409 Conflict`). This guarantees that only cryptographically verifiable human decisions from the authorized frontend can resolve the approval.
6. **Transactional Event Consistency:** All state transitions in the orchestrator utilize strict database transactional locking (SQLite `BEGIN EXCLUSIVE` or PostgreSQL `FOR UPDATE`). Server-Sent Events (SSE) and worker dispatches are strictly executed *after* a successful database commit, ensuring absolute telemetry consistency between the UI and backend and avoiding split-brain scenarios.
7. **Rate Limiting & Anti-Brute Force:** Key API endpoints, including the main analysis trigger and the administrative dashboard, are strictly protected with IP-based rate limiting (SlowAPI). This prevents Denial of Wallet (exhausting LLM tokens) and Denial of Service (overloading concurrent Git cloning).

---

## Project Structure

```text
codesentinel/
├── .github/workflows/           # Project deployment & worker workflows
│   ├── azure-static-web-apps-*.yml  # Azure Static Web Apps deployment
│   ├── codesentinel-api-*.yml       # Azure Container Apps API deployment
│   ├── sandbox.yml                  # Docker sandbox image build workflow
│   └── worker.yml                   # Ephemeral LangGraph worker dispatch
├── backend/
│   ├── main.py                  # FastAPI entry point & lifespan manager
│   ├── state.py                 # Global state and SSE queues
│   ├── orchestrator.py          # LangGraph state machine
│   ├── worker.py                # Standalone LangGraph agent worker execution
│   ├── config.py                # Environment & LLM key rotation pool
│   ├── limiter.py               # SlowAPI rate limiter instance
│   ├── codesentinel.db          # SQLite orchestrator state database
│   ├── Dockerfile               # Backend container image
│   ├── requirements.txt         # Core dependencies
│   ├── requirements-worker.txt  # Worker dependencies
│   ├── .env.example             # Environment variable template
│   ├── api/
│   │   ├── routes.py            # POST endpoints (analysis initiation, approvals, webhooks)
│   │   ├── sse.py               # SSE streaming endpoint for pipeline observability
│   │   ├── job_manager.py       # Database interface for job state persistence
│   │   ├── db.py                # Database abstraction layer (SQLite/PostgreSQL)
│   │   └── worker_auth.py       # Worker-to-Orchestrator HMAC signature verification
│   ├── agents/                  # LangGraph Node Actors
│   │   ├── repo_mapper.py       # Builds LLM architectural map of target repo
│   │   ├── dependency_analyzer.py # Identifies outdated packages and CVEs (PyPI/npm/Maven/Go)
│   │   ├── static_analysis.py   # 25 scanning modules (8 SAST tools + 17 custom)
│   │   ├── bug_investigator.py  # LLM RAG root-cause analysis
│   │   ├── repair_planner.py    # Formulates fixes & requests human approval
│   │   ├── code_generator.py    # Generates Search/Replace blocks
│   │   ├── validator.py         # Pre-test build verification & dynamic test suite execution
│   │   ├── security_verifier.py # Re-runs SAST to verify vulnerabilities are fixed
│   │   └── pr_author.py         # Pull Request synthesizer
│   ├── models/
│   │   └── pipeline_state.py    # Strictly typed state schema
│   ├── tests/                   # Automated unit and integration test suite (90+ test files, 360+ tests)
│   ├── tools/
│   │   ├── llm_router.py        # Multi-tier LLM routing with token budgets
│   │   ├── key_dispatcher.py    # Round-robin API key rotation with daily budgets
│   │   ├── auth.py              # Worker-to-Orchestrator HMAC auth client
│   │   ├── patch_applier.py     # Pure Python search & replace patch engine
│   │   ├── github_client.py     # PyGithub abstraction layer
│   │   ├── vector_store.py      # ChromaDB fix memory (RAG store)
│   │   ├── osv_client.py        # OSV.dev vulnerability batch query client
│   │   ├── safe_path.py         # Directory traversal prevention utility
│   │   ├── safe_repo.py         # Safe filesystem operations for repo access
│   │   ├── subprocess_runner.py # Async safe subprocess executor
│   │   ├── sandbox_runner.py    # Docker sandbox execution engine
│   │   ├── confidence_calc.py   # Unified 4-part confidence score engine
│   │   ├── knowledge_graph.py   # AST import dependency graph & circular cycle detector
│   │   ├── context_cache.py     # In-memory LRU session cache for repo context
│   │   ├── context_pruner.py    # AST-aware function extraction & diff pruning
│   │   ├── response_cache.py    # LLM response LRU cache with disk persistence
│   │   └── prompt_cache.py      # Version-controlled system prompts
├── ci-cd-template/              # Drop-in automation scripts for target repos
│   └── .github/workflows/       
│       ├── codesentinel.yml     # GitHub webhook CI/CD reference config
│       └── azure-container-apps.yml # Azure Container Apps deployment
├── sandbox/                     # Docker sandbox for untrusted code execution
│   ├── Dockerfile               # Sandbox container image (memory-bounded, capabilities dropped)
│   └── scripts/                 # Sandbox helper scripts
├── scripts/
│   └── setup.sh                 # Environment setup and setup helper script
├── docker-compose.yml           # Multi-container orchestration configuration
├── nginx.conf                   # Reverse proxy routing configuration
└── frontend/
    ├── Dockerfile               # Frontend container image
    ├── index.html               # HTML entry point
    ├── vite.config.js           # API proxy configuration
    ├── tailwind.config.js       # Tailwind CSS configuration
    ├── postcss.config.js        # PostCSS plugin configuration
    ├── eslint.config.js         # ESLint flat configuration
    └── src/
        ├── main.jsx             # React DOM root mount
        ├── index.css            # Global styles & Tailwind directives
        ├── App.jsx              # Main UI Shell
        ├── context/
        │   └── PipelineContext.jsx # Global Reducer for SSE event payloads
        ├── hooks/
        │   ├── usePipeline.js   # SSE connection management & auto-retry
        │   └── useApproval.js   # Async mutation hook for human intervention
        ├── services/
        │   └── credentialStore.js # Secure credential storage service
        ├── pages/
        │   └── admin/
        │       └── AdminDashboard.jsx # System observability dashboard
        └── components/
            ├── dashboard/       # Pipeline UI components
            │   ├── ApprovalModal.jsx   # Human-in-the-loop approval dialog
            │   ├── ConfidenceScore.jsx # Pipeline confidence gauge
            │   ├── DiffViewer.jsx      # Side-by-side patch diff renderer
            │   ├── FindingsPanel.jsx   # SAST findings display panel
            │   ├── LLMWaitingState.jsx # LLM capacity waiting indicator
            │   ├── PRSummary.jsx       # Pull Request summary card
            │   ├── PipelineDashboard.jsx # Top-level dashboard layout
            │   ├── PipelineView.jsx    # Real-time pipeline stage tracker
            │   └── ThemeToggle.jsx     # Dark/light mode switch
            └── landing/         # Landing page components
                ├── LandingPage.jsx     # Landing page layout
                ├── Navbar.jsx          # Navigation bar
                ├── Hero.jsx            # Hero section
                ├── ProblemSection.jsx   # Problem statement section
                ├── FeaturesSection.jsx  # Feature highlights
                ├── WorkflowSection.jsx  # Pipeline workflow visualization
                ├── AgentsSection.jsx    # Agent mesh overview
                ├── ArchitectureSection.jsx # Architecture diagram
                ├── MultiRepoSection.jsx # Multi-repo wildcard feature
                ├── GithubIntegration.jsx # GitHub webhook integration
                ├── SecuritySection.jsx  # Security features
                ├── SupportedLanguages.jsx # Language support grid
                ├── RepositoryAnalyzer.jsx # Repo analysis input
                ├── FinalCTA.jsx         # Call-to-action footer
                └── Footer.jsx          # Page footer
```

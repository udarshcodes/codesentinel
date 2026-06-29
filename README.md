<div align="center">
  <br />
  <a href="https://github.com/udarshcodes/codesentinel" style="text-decoration: none;">
    <img src="frontend/public/logo.jpg" alt="CodeSentinel Logo" width="120" height="120" style="border-radius: 50%;" />
    <br />
    <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=45&pause=1500&color=00D2FF&center=true&vCenter=true&width=1000&height=120&lines=CodeSentinel;Autonomous+AI+Code+Remediation;Stop+drowning+in+alerts;Automate+your+remediation" alt="CodeSentinel Typing SVG" />
  </a>
  <br />
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

### Backend
- **Python 3.10+ & FastAPI:** Asynchronous speed, Pydantic validation, and Server-Sent Events (SSE). Utilizes `fastapi.BackgroundTasks` to execute headless pipelines suitable for robust CI/CD webhook triggers.
- **LangGraph:** Robust directed graph state machine orchestrating discrete AI agents, with controlled cyclic loops for iterative repair (test -> fail -> fix -> test).
- **ChromaDB:** Lightweight embedded vector database storing and retrieving past validated fixes via RAG.
- **Groq API:** Multi-tier routing sending simple tasks to rapid models and complex code generation to 70B+ parameters.

### Frontend
- **React 18 & Vite:** Lightning-fast HMR and optimized production builds.
- **Tailwind CSS:** Utility-first CSS for rapid, highly-customizable responsive design.
- **Context API & Custom Hooks:** Decouples SSE streaming state and asynchronous HTTP mutations.

### Tooling
- **SAST Runners & Analyzers:** `Semgrep`, `SonarQube` (if available), `Bandit`, `Flake8`, `Pylint`, `ESLint`, `Go Vet`, and `Cargo Clippy` serve as the deterministic baseline. Also features 13 custom scanning modules for memory/resource leak detection, dead code detection, built-in hardcoded secrets detection, and circular dependency analysis.
- **Dependency & Registry Checks:** Real-time vulnerability queries via OSV.dev and live registry queries across NPM, PyPI, Maven Central, Go Proxy, and Crates.io.
- **PyGithub:** Safely abstracts cross-fork Pull Request creation and branch management.
- **Pure Python Patch Engine:** A custom-built Search/Replace engine that bypasses strict `git apply` constraints to guarantee reliable AI code insertion.

---

## Data Flow

```mermaid
graph TD
    A[User Submits Repo URL] -->|POST /api/analyze| B(FastAPI Router)
    B --> C{LangGraph Orchestrator}
    
    subgraph Agentic Pipeline
    C --> D[Repo Mapper]
    D --> DA[Dependency Analyzer]
    DA --> SA[Static Analysis]
    SA --> F[Bug Investigator]
    F -.->|Query| G[(ChromaDB Vector Store)]
    F --> H[Repair Planner]
    H -->|If High Risk: SSE Pause| I((Human Approval))
    H -->|If Low Risk| J[Code Generator]
    I -->|POST /api/approve/{task_id}| J
    J --> K[Validator]
    K -->|If Build or Tests Fail| J
    K -->|If Tests Pass| SV[Security Verifier]
    SV -->|If Still Vulnerable, Return to Generator| J
    SV -->|If Secure| L[PR Author]
    end
    
    L --> M[GitHub API]
    M --> N((Open Pull Request))
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

### 4. Admin Dashboard Setup (Required for /admin route)
```bash
cd ../backend/admin_dashboard
npm install
npm run build
```

### 5. Environment Variables
Create a `.env` file in the `backend/` directory:
```env
# Required: Comma-separated Groq API keys for automated round-robin rotation
GROQ_API_KEY=gsk_abc123,gsk_def456,gsk_ghi789

# Optional: Emergency key (activates only when all primary keys are exhausted)
GROQ_EMERGENCY_KEY=gsk_emergency_key

# Required: For cloning, pushing, and opening PRs
GITHUB_TOKEN=ghp_your_personal_access_token

# Required: Master password to access the /admin observability dashboard
ADMIN_SECRET=your_super_secret_password
```

### 6. Run the Application
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
| `GET`  | `/api/stream` | SSE endpoint streaming real-time `PipelineState` payloads, filterable by `task_id`. |
| `POST` | `/api/approve/{task_id}` (or `/api/v1/approve/{task_id}`) | Unblocks the LangGraph pipeline with a human `approved` or `rejected` decision. |
| `POST` | `/api/webhook/github` (or `/api/v1/webhook/github`) | Automated CI/CD webhook endpoint triggering analysis on GitHub push and PR events with HMAC SHA-256 signature verification (`X-Hub-Signature-256`). |
| `GET`  | `/health`, `/live`, `/ready`, `/metrics` | Observability endpoints returning system health status, liveness, readiness, and queue/execution job metrics. |
| `GET`  | `/admin/token-usage` | Protected endpoint returning LLM key rotation stats. Requires `X-Admin-Token` header. |
| `GET`  | `/admin` | Serves the statically built React Admin Dashboard. |

---

## CI/CD Integration (GitHub Actions)

CodeSentinel comes with a pre-configured GitHub Actions workflow template located in `ci-cd-template/.github/workflows/codesentinel.yml`.

By copying this workflow into your target repository, you can automatically trigger the CodeSentinel pipeline whenever a Pull Request is opened or a push lands on `main`.

**Setup Instructions:**
1. Navigate to your target repository on GitHub.
2. Go to **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**.
3. Name the secret `CODESENTINEL_API_URL` and set the value to the public URL of your deployed CodeSentinel backend (e.g., `https://api.codesentinel.yourdomain.com`).
4. Copy the `codesentinel.yml` file into your repository's `.github/workflows/` directory.

Once configured, CodeSentinel will automatically analyze incoming code and post a comment directly on your PRs with a link to the live SSE telemetry stream!

---

## Security Considerations

1. **Deterministic Patching:** The custom Python patch engine ensures exactly what the AI suggests is applied, bypassing brittle system patch limits while maintaining strict character matching and forbidding LLM abbreviations.
2. **Ephemeral Branching:** The pipeline operates on temporary Git branches (`agent/fix-*`). Local file modifications are completely discarded if validation loops hit the maximum retry limit. Note: Code execution during validation runs directly on the host, not in an isolated sandbox. Future updates plan to shift this execution into ephemeral, isolated Docker containers to prevent malicious LLM code generation from executing arbitrary operations.
3. **Secret Management & Transport:** LLM API keys and GitHub tokens are strictly confined to the backend environment. Tokens are handled securely via local git configuration (`http.extraheader`) rather than command-line remote URLs, ensuring they never leak into process logs or `.git/config`.
4. **Input Validation:** All repository URLs are strictly validated against allowlist regex patterns to prevent Server-Side Request Forgery (SSRF) and command injection before any cloning occurs.

---

## Project Structure

```text
codesentinel/
├── backend/
│   ├── main.py                  # FastAPI entry point & static asset mounter
│   ├── state.py                 # Global state and SSE queues
│   ├── orchestrator.py          # LangGraph state machine
│   ├── config.py                # Environment & LLM key rotation pool
│   ├── api/
│   │   ├── routes.py            # POST endpoints (analysis initiation, approvals)
│   │   └── sse.py               # SSE streaming endpoint for pipeline observability
│   ├── agents/                  # LangGraph Node Actors
│   │   ├── repo_mapper.py       # Builds LLM architectural map of target repo
│   │   ├── dependency_analyzer.py # Identifies outdated packages and CVEs (PyPI/npm/Maven/Go)
│   │   ├── static_analysis.py   # Subprocess orchestration for SAST tools
│   │   ├── bug_investigator.py  # LLM RAG root-cause analysis
│   │   ├── repair_planner.py    # Formulates fixes & requests human approval
│   │   ├── code_generator.py    # Generates Search/Replace blocks
│   │   ├── validator.py         # Pre-test build verification & dynamic test suite execution
│   │   ├── security_verifier.py # Re-runs SAST to verify vulnerabilities are fixed
│   │   └── pr_author.py         # Pull Request synthesizer
│   ├── models/
│   │   └── pipeline_state.py    # Strictly typed state schema
│   ├── tests/                   # Automated unit and integration test suite (11 test files)
│   ├── tools/
│   │   ├── llm_router.py        # Multi-tier LLM routing with token budgets
│   │   ├── key_dispatcher.py    # Round-robin API key rotation & emergency failover
│   │   ├── patch_applier.py     # Pure Python search & replace patch engine
│   │   ├── github_client.py     # PyGithub abstraction layer
│   │   ├── vector_store.py      # ChromaDB fix memory (RAG store)
│   │   ├── osv_client.py        # OSV.dev vulnerability batch query client
│   │   ├── analysis_runner.py   # Scoped Semgrep/Bandit/Pylint/Flake8 runner
│   │   ├── confidence_calc.py   # Unified 4-part confidence score engine used by validator and pr_author
│   │   ├── knowledge_graph.py   # AST import dependency graph & circular cycle detector
│   │   ├── context_cache.py     # In-memory LRU session cache for repo context
│   │   ├── context_pruner.py    # AST-aware function extraction & diff pruning
│   │   ├── response_cache.py    # LLM response LRU cache with disk persistence
│   │   └── prompt_cache.py      # Version-controlled system prompts
│   └── admin_dashboard/         # Isolated Vite/React app for Token Observability
├── ci-cd-template/              # Drop-in automation scripts for target repos
│   └── .github/workflows/       
│       ├── codesentinel.yml     # GitHub Actions CI/CD trigger workflow
│       └── azure-container-apps.yml # Azure Container Apps deployment
├── scripts/
│   └── setup.sh                 # Environment setup and setup helper script
├── docker-compose.yml           # Multi-container orchestration configuration
├── nginx.conf                   # Reverse proxy routing configuration
└── frontend/
    ├── src/
    │   ├── context/
    │   │   └── PipelineContext.jsx # Global Reducer for SSE event payloads
    │   ├── hooks/
    │   │   ├── usePipeline.js   # SSE connection management & auto-retry
    │   │   └── useApproval.js   # Async mutation hook for human intervention
    │   ├── components/          # Reusable UI components (DiffViewer, PipelineView, etc.)
    │   └── App.jsx              # Main UI Shell
    └── vite.config.js           # API proxy configuration
```

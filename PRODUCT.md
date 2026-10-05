# CodeSentinel: Autonomous AI Vulnerability Remediation Pipeline

**Live Demo:** [https://salmon-ground-0362fac00.7.azurestaticapps.net/](https://salmon-ground-0362fac00.7.azurestaticapps.net/)

## 1. Executive Summary
CodeSentinel is an advanced, autonomous AI agent mesh designed to identify, analyze, and remediate vulnerabilities and structural bugs within modern codebases. By leveraging a deterministic state machine (LangGraph) integrated with tiered Large Language Models (LLMs), CodeSentinel operates as a proactive, autonomous site reliability engineer (SRE) and security researcher. The system maps repositories, executes static analysis, generates AST-aware code patches, validates repairs against testing suites, runs targeted security re-verifications, and authors production-ready GitHub Pull Requests entirely autonomously.

## 2. Problem Statement
Modern CI/CD pipelines are excellent at *detecting* issues via static application security testing (SAST), linting, and dependency scanning, but fundamentally fail at *remediation*. Developers are bombarded with alerts, leading to alert fatigue and growing technical debt. Critical fixes are delayed, and inconsistent patches arise when different engineers fix the same class of bug differently. Traditional AI coding assistants are reactive, requiring human-in-the-loop prompting and localized context gathering. There is a critical need for an asynchronous, autonomous pipeline capable of digesting global repository context, synthesizing architectural understanding, executing high-confidence code repairs, and verifying security fixes without manual intervention.

## 3. Solution Overview
CodeSentinel bridges the gap between detection and remediation. When triggered, it performs a complete ingestion of the target repository. It utilizes a multi-agent architecture where highly specialized AI agents handle distinct phases of the remediation lifecycle:
1. **Contextual Mapping:** Building an LLM-synthesized architectural mapping of the repository.
2. **Deep Investigation:** Triaging anomalies detected by traditional static analyzers, utilizing Retrieval-Augmented Generation (RAG) against past successful fixes.
3. **Repair Planning:** Formulating multi-file architectural repair strategies, with human-in-the-loop approval gates for high-risk operations (e.g., Auth, DB schemas).
4. **Code Generation:** Applying precise, contextually aware code patches.
5. **Validation:** Verifying structural integrity post-repair via syntax checks and test suite executions.
6. **Security Verification:** File-scoped, post-patch execution of security scanners (Bandit/Semgrep) to guarantee vulnerability closure.
7. **PR Authoring:** Generating rich, conventional pull requests for human review.

## 4. System Architecture

### 4.1 Component Breakdown
CodeSentinel is built on a modern, decoupled architecture prioritizing extreme fault tolerance, real-time observability, and horizontal scalability.

- **Frontend Visualization Layer (React + Vite + Tailwind):** 
  A high-performance React application serving as the control plane. It consumes Server-Sent Events (SSE) to render real-time telemetry of the LangGraph execution state, providing operators with confidence scores, live diff rendering, and pipeline visualization.
  - *Admin Dashboard:* Integrated directly into the main React application at `/admin`, built for observability. It exposes macro-level system metrics, model tracking, token rotation stats, queue depth, and job metrics. Accessing this dashboard requires the backend session cookie created by providing the `ADMIN_SECRET`.
  
- **API & Orchestration Layer (FastAPI + Database):** 
  A high-throughput asynchronous backend powered by FastAPI that acts as the **Single Source of Truth** for the entire system. 
  - *Why the Monolithic Backend was Replaced:* Originally, CodeSentinel packaged all language runtimes, build tools, and SAST scanners into a single 5.5GB monolithic backend container. This huge image made deploying to cost-effective serverless environments (like Azure Container Apps Free Tier) impossible due to strict 5-minute image pull timeouts. 
  - *Why SQLite/PostgreSQL was Selected:* SQLite provides robust, persistent job tracking and idempotent state management without the overhead, cost, or complexity of managing a dedicated database service for a lightweight orchestrator in local development. For production deployments, the abstraction layer seamlessly shifts to PostgreSQL to provide robust row-level concurrency locking (`FOR UPDATE`).
  - *Why Backend is the Single Source of Truth:* The orchestrator tracks the state and broadcasts it via SSE. This ensures that the frontend never has to poll GitHub APIs directly, and the backend maintains authoritative control over ChromaDB, API keys, and job lifecycles.

- **Ephemeral Worker Layer (GitHub Actions):** 
  - *Why GitHub Actions Worker was Chosen:* We shifted the LangGraph execution and SAST scanning to an ephemeral GitHub Actions worker model triggered via HTTP webhooks. This provides isolated execution environments, zero-maintenance scaling, and seamless telemetry streaming via authenticated HTTP callbacks, completely eliminating the need for complex localized worker infrastructure.
  - *Agent Mesh (`backend/agents/`)*: A swarm of stateless, specialized agents that execute within the worker process. Each agent acts as a distinct node in the LangGraph, executing heavy scans and posting granular state updates back to the orchestrator via HTTP webhooks.
  - *Repo Mapper:* Builds a rich architectural map containing API endpoint inventories, database interaction mappings, and service boundary detection via LLM synthesis.
  - *Dependency Analyzer:* Identifies outdated packages and CVEs (PyPI/npm/Maven/Go).
  - *Static Analysis:* Scans for vulnerabilities across multiple categories including `security`, `quality` (e.g., duplicate code, long methods), and `performance` (e.g., SQLAlchemy N+1 detection).
  - *Bug Investigator:* Performs LLM RAG root-cause analysis querying historical fixes.
  - *Repair Planner:* Formulates fixes & conditionally requests human approval for high-risk operations.
  - *Code Generator:* Generates precise, AST-aware Search/Replace patches.
  - *Validator:* Executes an automated build verification step followed by dynamic testing and security reverification.
  - *Security Verifier:* Re-runs SAST on modified files to verify vulnerabilities are fixed.
  - *PR Author:* Synthesizes diffs and interactions into a Pull Request for human review.
  
- **Intelligent Tooling & Routing (`backend/tools/`):** 
  The proprietary LLM and operational infrastructure layer. Features a highly optimized `llm_router` capable of dynamic model tiering (fast/cheap vs. slow/reasoning), automatic JSON schema extraction, resilient deterministic Round-Robin credential cycling across multiple distinct unified keys for rate limit load balancing, an integrated scanner runner for executing core SAST tools, a `confidence_calc` engine for weighted pipeline scoring, and a `knowledge_graph` module that builds AST import dependency graphs and detects circular import cycles.

## 5. Data Flow (System Telemetry)

The data flow ensures context is preserved and strictly typed throughout the execution lifecycle.
1. **Ingestion & Triggering:** A webhook or API call initiates the pipeline. The orchestrator initializes a strictly typed `PipelineState` object containing `repo_url`, `retry_count`, and `confidence_score`.
2. **Contextual Mapping:** The `repo_mapper` agent builds an LLM-synthesized architectural mapping of the repository, extracting boundaries and relationships.
3. **Analysis Execution:** The dependency_analyzer agent runs first, followed by the static_analysis agent, both injecting raw findings into the state using external tools (OSV, Bandit, Semgrep, ESLint, Pylint, Flake8, SonarQube (if available), Go Vet, Cargo Clippy) and real-time public registry checks (NPM, PyPI, Maven Central, Go Proxy, and Crates.io).
4. **LLM Triage & Context Retrieval:** The `bug_investigator` agent queries the ChromaDB Vector Store for historical fixes of similar bugs, filtering out false positives using an LLM.
5. **Planning & Approval:** The `repair_planner` formulates a patch strategy. If modifications hit sensitive paths (e.g., `auth/`, `db/`), it transitions the pipeline to an `awaiting_approval` state, broadcasting an SSE event and pausing the graph until a `/api/approve/{task_id}` webhook is received. This endpoint is secured using an ephemeral, task-scoped `approval_token` generated during ingestion, ensuring the frontend never requires global administrative credentials.
6. **Execution Loop:** The `code_generator` executes file I/O to apply patches. The `validator` inspects syntax and test outputs. If tests fail, the graph cycles back. 
7. **Security Verification Loop:** Post-validation, `security_verifier` executes targeted Semgrep/Bandit scans strictly on modified files. If the original vulnerability rule fires again, the `security_retry_context` is updated and the graph routes back to `code_generator`.
8. **Commit & PR:** Upon successful validation and security clearance, the `pr_author` synthesizes the diffs and interactions into a comprehensive Pull Request via the PyGithub SDK.

## 6. Agent Pipeline Architecture

The LangGraph implementation uses a directed graph with tightly controlled cyclic capabilities for self-healing:

```text
[ START ] 
   │
   ▼
( Repo Mapper ) ──► ( Dependency Analyzer ) ──► ( Static Analysis )
                                                       │
                                                       ▼
                                            ( Bug Investigator )
                                                       │
                                                       ▼
                                             ( Repair Planner ) ──► [ High Risk: Await Approval ]
                                                       │                        │
                                            [Low Risk] │                        │ [Approved]
                                                       ▼                        ▼
                 ┌◄───────────────────────── ( Code Generator ) ◄┐ ◄────────────┘
                 │                                     │         │
           [ Validation Failed ]                       ▼         │
                 │                               ( Validator )   │
                 └─────────────────────────────────────┤         │
                                                       │         │
                                              [ Validation Passed ]
                                                       │         │
                                                       ▼         │
                                            ( Security Verifier )┴─ [ Vulnerability Persists ]
                                                       │
                                            [ Security Clean ]
                                                       │
                                                       ▼
                                                ( PR Author )
                                                       │
                                                       ▼
                                                    [ END ]
```

## 7. Feature Catalog & Technical Depth

### Dynamic Multi-Tier LLM Routing (`llm_router.py`)
CodeSentinel optimizes cost and latency by routing tasks to appropriately sized models. Structural tasks (mapping, basic extraction) are routed to Tier 1 models (e.g., `openai/gpt-oss-20b`), while complex architectural reasoning and actual code synthesis are routed to Tier 2 models (e.g., `openai/gpt-oss-120b`). A specialized fallback logic utilizes `qwen/qwen3.6-27b` if needed. 

### Human-in-the-loop Approval Gate
For maximum safety, `repair_planner.py` uses heuristic `classify_risk` checks. If high-risk changes are detected, the ephemeral worker pauses execution by transitioning the pipeline to an `awaiting_approval` state, persisting this to the orchestrator, and securely terminating. The FastAPI backend streams an `approval_required` SSE event to the React frontend, displaying an Approval Modal. Once the human operator approves via the `/api/approve/{task_id}` REST endpoint, the orchestrator dispatches a new ephemeral worker attempt that hydrates the state and seamlessly resumes the LangGraph execution. This completely eliminates thread deadlocks and long-polling in the orchestrator.

### Code Quality & Performance Scans
Beyond basic security checks, the `static_analysis.py` agent enforces high structural code quality across 18 specialized scanning modules (8 standard SAST tools and 10 custom modules). Findings are tagged with specific categories (`security`, `quality`, `performance`, `functional`).
- **Quality & Dead Code:** Enforces thresholds for long methods (50 lines) and duplicate code blocks, identifies circular dependencies via `knowledge_graph`, detects built-in hardcoded secrets, and flags unused functions, classes, and files across Python, JS/TS, HTML, and CSS.
- **Performance & Leak Detection:** Executes AST matching to detect N+1 query structures in SQLAlchemy, Prisma, Mongoose, Go, Rust, and Java. Identifies memory and resource leaks such as unclosed Python `open()` calls, uncleaned JS/TS event listeners/intervals, Go unclosed resources, and Java unclosed streams.

### Pre-Test Build Verification
Before running dynamic test suites, the `validator.py` agent executes a mandatory build verification step. It intelligently detects the project type (`package.json`, `pom.xml`, `build.gradle`, `pyproject.toml`, `setup.py`) and runs the associated build command (e.g., `npm run build`, `mvn package`, `gradle assemble`, `python -m build`). If the build fails, the pipeline immediately short-circuits back to the `code_generator`, saving valuable compute time that would otherwise be wasted on fundamentally broken syntax.

### Targeted Security Retries
Rather than executing blind fixes, CodeSentinel ensures deterministic proof of remediation. The `security_verifier.py` isolates newly generated patches and runs `semgrep` and `bandit` strictly on modified files. If the patch fails to clear the initial rule ID, the system injects `security_retry_context` back into the graph, feeding the exact tool failure logs back to the `code_generator` for a secondary attempt.

### ChromaDB Fix Memory & Confidence Scoring
CodeSentinel learns from its successes. Using `confidence_calc.py`, the `validator.py` and `pr_author.py` agents calculate a unified 4-part confidence score: `(tests_ratio * 40.0) + (static_clean * 30.0) + (patches_ratio * 20.0) + (chroma_ratio * 10.0)`. Every successfully validated patch is hashed and embedded into a persistent `validated_fixes` ChromaDB collection centrally managed by the orchestrator. Future runs by the `bug_investigator` worker query this persistent vector store via the orchestrator's unified backend REST interface to inject context from previously successful architectural repairs, avoiding stale memory across ephemeral worker lifecycles.

### Dynamic API Key Rotation & Token Budgeting (`llm_router.py`)
To bypass rate limits and token exhaustion, the system implements a proprietary load-balancer tracking daily token budgets across an array of up to 6 unified API keys directly within the LLM Router. There is no designated "reserve" key; all configured keys operate as a unified credential pool. Upon exhaustion or HTTP 429 errors, the router seamlessly rolls over to the next available key. Qwen is used as a fallback model across the pool when primary models are exhausted.

### Server-Sent Events (SSE) Streaming
To provide a massive leap in User Experience (UX), the FastAPI backend streams LangGraph state transitions directly to the React frontend via SSE. The pipeline execution is completely decoupled into a headless `fastapi.BackgroundTasks` runner generating a unique `task_id`. The UI requests an authenticated, single-use stream capability from `/api/v1/job/{task_id}/stream-capability` and connects to `/api/v1/stream`. Reconnections are gracefully handled via a unified `Last-Event-ID` header (or `last_event_id` query parameter fallback), ensuring the UI instantly hydrates from the exact point of disconnection without dropping events.

## 8. API Design Decisions
- **Asynchronous Execution:** Long-running AI agents are executed as background tasks within the asynchronous event loop. The `/api/analyze` endpoint immediately returns a `TaskID`, preventing HTTP timeouts.
- **RESTful + Streaming:** Standard operations utilize REST, while active pipeline execution relies exclusively on SSE for real-time telemetry. This inherently supports strict corporate firewalls better than stateful WebSockets.
- **Unblocking Mechanisms:** The `/api/approve/{task_id}` webhook interacts directly with the orchestration database. When a human approves, the orchestrator validates the task-scoped capability token (`approval_token`), updates the job status, and triggers a fresh worker dispatch to resume execution.
- **Admin Authentication:** The React SPA Dashboard (`/admin`) is secured using an HTTP-Only, Secure session cookie (`admin_session`). The `/api/v1/admin/login` endpoint validates the provided secret against the environment's `ADMIN_SECRET` and creates a session trackable in the backend database to secure all subsequent dashboard observability queries.
- **Worker Authentication:** Ephemeral GitHub Action workers authenticate state updates via strict HMAC SHA-256 signatures (`X-Worker-Signature`) generated with `WORKER_WEBHOOK_SECRET` covering the HTTP method, path, task ID, and timestamp. The system inherently rejects cross-talk via `X-Worker-Attempt-Id` validations.
- **Transactional Event Consistency:** All state transitions in the orchestrator utilize strict transactional locking (SQLite `BEGIN EXCLUSIVE` or PostgreSQL `FOR UPDATE`). Server-Sent Events (SSE) and worker dispatches are strictly executed *after* a successful database commit, ensuring absolute telemetry consistency between the UI and backend and avoiding split-brain scenarios.
- **CI/CD Integration Pipeline:** The primary integration mechanism leverages GitHub Webhooks. Configuring a repository webhook to point to the `/v1/webhook/github` endpoint automatically initiates the analysis whenever a PR is opened or a push occurs. It validates the webhook payload via HMAC SHA-256 signature verification and responds by posting a comment on the PR containing a link to the live SSE telemetry stream.

## 9. Scalability Strategy
- **Stateless Orchestration & Ephemeral Compute:** LangGraph nodes process state transformations on a `PipelineState` TypedDict within decoupled background workers. This architecture inherently supports massive horizontal scaling because the heavy compute (cloning, building, scanning, LLM generation) is offloaded to independent worker processes, while the orchestrator remains an ultra-lightweight state machine and SSE broadcaster.
- **Aggressive Caching (`context_cache.py` / `response_cache.py`):** Identical LLM prompts and repository AST structures are cached locally. During repetitive debugging cycles, this prevents redundant network I/O to the LLM provider, drastically reducing pipeline execution time and API costs.
- **Dependency Structure:** CodeSentinel uniformly pins its orchestration and worker dependencies against the `langchain==0.3.x` ecosystem, guaranteeing absolute consistency between orchestrator-bound database functions and ephemeral worker graphs.

## 10. Security Considerations
- **Execution Environment:** To prevent malicious LLM code generation from executing arbitrary operations on the host SRE server, all untrusted code execution (e.g., running `npm run build` or `python -m build` during the validation phase) strictly executes within memory-bounded, ephemeral Docker sandboxes. These isolated containers operate with dropped capabilities, restricted network access, and read-only filesystems.
- **Principle of Least Privilege:** GitHub Personal Access Tokens (PATs) used by the `pr_author` agent are strictly scoped to the `repo:write` capability and are designed for rapid rotation.
- **Air-Gapped Telemetry:** No user source code is ever transmitted via SSE payloads; the system relies heavily on metadata, diff hashes, and rule IDs to stream pipeline progress.
- **Secret Management & Secure Transport:** API tokens and GitHub credentials are never passed via command-line arguments (which are visible in process logs). Instead, the Git Client intelligently injects credentials using `http.extraheader` directly into isolated subprocess executions.
- **Strict Input Validation:** All external inputs, specifically target repository URLs, are scrubbed and validated via strict regex allowlists to thwart Server-Side Request Forgery (SSRF) and command injection vectors prior to cloning.
- **Approval State Integrity:** The orchestration layer strictly fences state mutations. When a job is in a pending human approval state (`WAITING_FOR_APPROVAL`), all generic worker state updates via the webhook are aggressively rejected (`HTTP 409 Conflict`). This guarantees that only cryptographically verifiable human decisions from the authorized frontend can advance the pipeline, mitigating any potential forged worker payloads.

## 11. Future Roadmap
1. **Advanced Distributed Tracing:** Expanding the `repo_mapper` to trace vulnerabilities across runtime microservice boundaries via OpenTelemetry integrations, building on top of the already implemented Multi-Repository wildcard execution engine (`github.com/org/*`) and AST `KnowledgeGraph` service boundary mappings.
2. **IDE Integration:** Exposing the FastAPI backend via a Language Server Protocol (LSP) to allow the LangGraph pipeline to operate directly within VSCode/JetBrains environments.
3. **Advanced Self-Healing via MCTS:** Implementing Monte Carlo Tree Search (MCTS) within the `validator` loop to explore multiple repair pathways simultaneously, testing competing branches and selecting the one with the highest terminal confidence score.

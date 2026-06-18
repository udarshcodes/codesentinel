# CodeSentinel: Autonomous AI Vulnerability Remediation Pipeline

## 1. Executive Summary
CodeSentinel is an advanced, autonomous AI agent mesh designed to identify, analyze, and remediate vulnerabilities and structural bugs within modern codebases. By leveraging a deterministic state machine (LangGraph) integrated with tiered Large Language Models (LLMs), CodeSentinel operates as a proactive, autonomous site reliability engineer (SRE) and security researcher. The system maps repositories, executes static analysis, generates AST-aware code patches, validates repairs against testing suites, runs targeted security re-verifications, and authors production-ready GitHub Pull Requests entirely autonomously.

## 2. Problem Statement
Modern CI/CD pipelines are excellent at *detecting* issues via static application security testing (SAST), linting, and dependency scanning, but fundamentally fail at *remediation*. Developers are bombarded with alerts, leading to alert fatigue and growing technical debt. Traditional AI coding assistants are reactive, requiring human-in-the-loop prompting and localized context gathering. There is a critical need for an asynchronous, autonomous pipeline capable of digesting global repository context, synthesizing architectural understanding, executing high-confidence code repairs, and verifying security fixes without manual intervention.

## 3. Solution Overview
CodeSentinel bridges the gap between detection and remediation. When triggered, it performs a complete ingestion of the target repository. It utilizes a multi-agent architecture where highly specialized AI agents handle distinct phases of the remediation lifecycle:
1. **Contextual Mapping:** Building an LLM-synthesized architectural mapping of the repository.
2. **Deep Investigation:** Triaging anomalies detected by traditional static analyzers, utilizing Retrieval-Augmented Generation (RAG) against past successful fixes.
3. **Repair Planning:** Formulating multi-file architectural repair strategies, with human-in-the-loop approval gates for high-risk operations (e.g., Auth, DB schemas).
4. **Code Generation:** Applying precise, context-aware code patches.
5. **Validation:** Verifying structural integrity post-repair via syntax checks and test suite executions.
6. **Security Verification:** File-scoped, post-patch execution of security scanners (Bandit/Semgrep) to guarantee vulnerability closure.
7. **PR Authoring:** Generating rich, conventional pull requests for human review.

## 4. System Architecture

### 4.1 Component Breakdown
CodeSentinel is built on a modern, decoupled architecture prioritizing extreme fault tolerance, real-time observability, and horizontal scalability.

- **Frontend Visualization Layer (React + Vite + Tailwind):** 
  A high-performance React application serving as the control plane. It consumes Server-Sent Events (SSE) to render real-time telemetry of the LangGraph execution state, providing operators with confidence scores, live diff rendering, and pipeline visualization. Features a dedicated Admin Dashboard for macro-level system metrics.
  
- **API & Orchestration Layer (FastAPI + LangGraph):** 
  A high-throughput asynchronous backend powered by FastAPI. At its core, LangGraph governs the pipeline's deterministic state machine, ensuring cyclic graphs (like iterative repair-validation loops and security retries) are handled gracefully with strictly typed `PipelineState` models. Deadlock-free asynchronous execution is managed via `asyncio` primitives (`FIRST_COMPLETED` wait states).

- **Agent Mesh (`backend/agents/`):** 
  A swarm of stateless, specialized agents. Each agent acts as a distinct node in the LangGraph, modifying a central, immutable state object and yielding control back to the orchestrator.
  - *Repo Mapper:* Builds a rich architectural map containing API endpoint inventories, database interaction mappings, and service boundary detection via LLM synthesis.
  - *Static Analysis:* Scans for vulnerabilities across multiple categories including `security`, `quality` (e.g., duplicate code, long methods), and `performance` (e.g., SQLAlchemy N+1 detection).
  - *Validator:* Executes an automated build verification step followed by dynamic testing and security reverification.
  
- **Intelligent Tooling & Routing (`backend/tools/`):** 
  The proprietary LLM and operational infrastructure layer. Features a highly optimized `llm_router` capable of dynamic model tiering (fast/cheap vs. slow/reasoning), automatic JSON schema extraction, a highly resilient `key_dispatcher` for token budget load balancing, and a unified `analysis_runner` for executing subprocess scanning tools.

## 5. Data Flow (System Telemetry)

The data flow ensures context is preserved and strictly typed throughout the execution lifecycle.
1. **Ingestion & Triggering:** A webhook or API call initiates the pipeline. The orchestrator initializes a strictly typed `PipelineState` object containing `repo_url`, `retry_count`, and `confidence_score`.
2. **Analysis Execution:** `static_analysis` and `dependency_analyzer` agents extract raw findings using external tools (OSV, Bandit, Semgrep, SonarQube) and real-time public registry checks (NPM/PyPI/Maven), injecting them into the state.
3. **LLM Triage & Context Retrieval:** The `bug_investigator` agent queries the ChromaDB Vector Store for historical fixes of similar bugs, filtering out false positives using an LLM.
4. **Planning & Approval:** The `repair_planner` formulates a patch strategy. If modifications hit sensitive paths (e.g., `auth/`, `db/`), it transitions the pipeline to an `awaiting_approval` state, broadcasting an SSE event and pausing the graph until a `/api/v1/approve` webhook is received.
5. **Execution Loop:** The `code_generator` executes file I/O to apply patches. The `validator` inspects syntax and test outputs. If tests fail, the graph cycles back. 
6. **Security Verification Loop:** Post-validation, `security_verifier` executes targeted Semgrep/Bandit scans strictly on modified files. If the original vulnerability rule fires again, the `security_retry_context` is updated and the graph routes back to `code_generator`.
7. **Commit & PR:** Upon successful validation and security clearance, the `pr_author` synthesizes the diffs and interactions into a comprehensive Pull Request via the PyGithub SDK.

## 6. Agent Pipeline Architecture

The LangGraph implementation enforces a strict Directed Acyclic Graph (DAG) with tightly controlled cyclic capabilities for self-healing:

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
                                             ( Repair Planner ) ──► [ Await Human Approval ]
                                                       │
                                                       ▼
                 ┌◄───────────────────────── ( Code Generator ) ◄┐
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
CodeSentinel optimizes cost and latency by routing tasks to appropriately sized models. Structural tasks (mapping, basic extraction) are routed to Tier 1 models (e.g., `llama-3.1-8b-instant`), while complex architectural reasoning and actual code synthesis are routed to Tier 2 models (e.g., `llama-3.3-70b-versatile`). 

### Human-in-the-loop Approval Gate
For maximum safety, `repair_planner.py` uses heuristic `classify_risk` checks. If high-risk changes are detected, execution pauses dynamically via `asyncio.Event`. The FastAPI backend streams an `approval_required` SSE event to the React frontend, displaying an Approval Modal. `asyncio.wait` with `FIRST_COMPLETED` ensures telemetry and incoming webhooks don't cause thread deadlocks while the main graph is sleeping.

### Code Quality & Performance Scans
Beyond basic security checks, the `static_analysis.py` agent enforces high structural code quality. Findings are tagged with specific categories (`security`, `quality`, `performance`, `functional`).
- **Quality:** Enforces thresholds for long methods, duplicate code blocks, and detects dead imports utilizing strict Pylint configurations.
- **Performance:** Executes lightweight Python AST matching to detect N+1 query structures targeting SQLAlchemy ORM patterns, and JS/TS regex parsing for Prisma and Mongoose inefficient database loads.

### Pre-Test Build Verification
Before running dynamic test suites, the `validator.py` agent executes a mandatory build verification step. It intelligently detects the project type (`package.json`, `pom.xml`, `pyproject.toml`) and runs the associated build command (`npm run build`, `mvn package`, `python -m build`). If the build fails, the pipeline immediately short-circuits back to the `code_generator`, saving valuable compute time that would otherwise be wasted on fundamentally broken syntax.

### Targeted Security Retries
Rather than executing blind fixes, CodeSentinel ensures cryptographic proof of remediation. The `security_verifier.py` isolates newly generated patches and runs `semgrep` and `bandit` strictly on modified files. If the patch fails to clear the initial rule ID, the system injects `security_retry_context` back into the graph, feeding the exact tool failure logs back to the `code_generator` for a secondary attempt.

### ChromaDB Fix Memory & Confidence Scoring
CodeSentinel learns from its successes. The `validator.py` calculates a weighted confidence score `(tests_ratio * 0.5) + (static_clean * 0.3) + (chroma_score * 0.2)`. Every successfully validated patch is hashed and embedded into a local `validated_fixes` ChromaDB collection. Future runs by the `bug_investigator` query this vector store via RAG to inject context from previously successful architectural repairs.

### API Key Dispatcher & Token Budgeting (`key_dispatcher.py`)
To bypass rate limits and token exhaustion, the system implements a proprietary load-balancer tracking daily token budgets across an array of API keys. Upon exhaustion or HTTP 429 errors, it seamlessly rolls over to the next key, eventually failing over to a highly restricted Emergency Key.

### Server-Sent Events (SSE) Streaming
To provide a massive leap in User Experience (UX), the FastAPI backend streams LangGraph state transitions directly to the React frontend via SSE. The pipeline execution is completely decoupled into a headless `fastapi.BackgroundTasks` runner generating a unique `task_id`. The `event_generator` drains background `asyncio.Queue` objects asynchronously based on this ID, allowing the UI to safely disconnect and reconnect without interrupting the robust CI/CD execution pipeline.

## 8. API Design Decisions
- **Asynchronous Execution:** Long-running AI agents are executed in isolated asynchronous event loops. The `/api/v1/analyze` endpoint immediately returns a `TaskID`, preventing HTTP timeouts.
- **RESTful + Streaming:** Standard operations utilize REST, while active pipeline execution relies exclusively on SSE for real-time telemetry. This inherently supports strict corporate firewalls better than stateful WebSockets.
- **Unblocking Mechanisms:** The `/api/v1/approve/{task_id}` webhook interacts directly with the orchestration memory space to set thread events, elegantly waking sleeping graph nodes.

## 9. Scalability Strategy
- **Stateless Agents:** LangGraph nodes process purely functional transformations on a `PipelineState` TypedDict. This allows the computational load of individual agents to be distributed across horizontally scaled worker nodes or serverless architectures (like AWS Lambda or Celery workers).
- **Aggressive Caching (`context_cache.py` / `response_cache.py`):** Identical LLM prompts and repository AST structures are cached locally. During repetitive debugging cycles, this prevents redundant network I/O to the LLM provider, drastically reducing pipeline execution time and API costs.

## 10. Security Considerations
- **Execution Environment:** Code execution (e.g., running `npm build` or `python -m build` during the validation phase) currently runs directly on the host environment. Future updates plan to shift this execution into ephemeral, isolated Docker containers to prevent malicious LLM code generation from executing arbitrary operations on the host SRE server.
- **Principle of Least Privilege:** GitHub Personal Access Tokens (PATs) used by the `pr_author` agent are strictly scoped to the `repo:write` capability and are designed for rapid rotation.
- **Air-Gapped Telemetry:** No user source code is ever transmitted via SSE payloads; the system relies heavily on metadata, diff hashes, and rule IDs to stream pipeline progress.
- **Secure Secret Transport:** API tokens and GitHub credentials are never passed via command-line arguments (which are visible in process logs) and are injected using `http.extraheader` configuration for git operations.
- **Strict Input Validation:** All external inputs, specifically target repository URLs, are scrubbed and validated via strict regex allowlists to thwart Server-Side Request Forgery (SSRF) and command injection vectors prior to cloning.

## 11. Future Roadmap
1. **Advanced Distributed Tracing:** Expanding the `repo_mapper` to trace vulnerabilities across microservice boundaries via OpenTelemetry integrations, building on top of the newly implemented Multi-Repository wildcard execution engine.
2. **IDE Integration:** Exposing the FastAPI backend via a Language Server Protocol (LSP) to allow the LangGraph pipeline to operate directly within VSCode/JetBrains environments.
3. **Advanced Self-Healing via MCTS:** Implementing Monte Carlo Tree Search (MCTS) within the `validator` loop to explore multiple repair pathways simultaneously, testing competing branches and selecting the one with the highest terminal confidence score.

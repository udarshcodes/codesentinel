# CodeSentinel Sandbox

This directory contains the immutable, reproducible Docker image definition for the CodeSentinel security sandbox.

## Purpose

The CodeSentinel worker operates on untrusted repositories (which may contain malicious configurations, pre-install scripts, or engineered paths). To protect the CodeSentinel orchestrator and infrastructure from compromise, all repository-controlled operations must execute within this hardened sandbox container.

## Security Properties

- **Non-root**: The container runs strictly as the unprivileged `codesentinel` user (`UID 1000`).
- **No Credentials**: No GitHub Tokens, API keys, or Webhook secrets are passed into the sandbox.
- **Network Isolation**: By default, the sandbox is executed with `--network none`.
- **Filesystem Isolation**: The host filesystem is completely detached. Only the required target repository is mounted to `/sandbox/repo`.
- **No New Privileges**: Run with `--security-opt=no-new-privileges` and `--cap-drop=ALL` (enforced by the sandbox runner).
- **Immutable Toolchain**: All tools and their versions are fixed and baked into the image.

## Supported Toolchain Versions

* **Python**: 3.10
* **Node.js**: 20.x
* **Go**: 1.21.8
* **Rust (Cargo)**: 1.75.0
* **Java**: 17
* **Maven**: 3.9.6
* **Gradle**: 8.5
* **Semgrep**: 1.66.0
* **Bandit**: 1.7.8
* **Pylint**: 3.1.0
* **Flake8**: 7.0.0
* **ESLint**: 8.57.0
* **Sonar Scanner**: 5.0.1.3006

## Verification

The script `scripts/verify-tools.sh` asserts that every required tool is available and returns a healthy version string. This is executed during the Docker build and dynamically checked in the CI/CD pipeline.

## Build and Test Locally

To build the image manually:
```bash
docker build -t codesentinel/sandbox:latest .
```

To run the capability verification script:
```bash
docker run --rm codesentinel/sandbox:latest verify-tools.sh
```

## Production Immutable Reference

In production environments, the container image is referenced via an immutable digest (e.g., `ghcr.io/udarshcodes/codesentinel-sandbox@sha256:...`). This guarantees that the execution boundary cannot drift or be poisoned via floating `latest` tags.

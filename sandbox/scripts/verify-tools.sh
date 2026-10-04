#!/usr/bin/env bash
set -e

echo "Verifying Sandbox Toolchain Capabilities..."

# Keep the container offline during verification
export http_proxy="http://127.0.0.1:1"
export https_proxy="http://127.0.0.1:1"

# Redirect caches to /tmp to prevent read-only filesystem errors
export HOME="/tmp"
export XDG_CACHE_HOME="/tmp/cache"
export NPM_CONFIG_CACHE="/tmp/npm"
export GOPATH="/tmp/go"
export GOCACHE="/tmp/go-cache"
export CARGO_HOME="/tmp/cargo"
export MAVEN_OPTS="-Duser.home=/tmp"
export GRADLE_USER_HOME="/tmp/gradle"

check_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "FATAL: Required tool '$1' is not installed or not in PATH."
        exit 1
    fi
}

verify_exec() {
    if ! "$@" >/dev/null 2>&1; then
        echo "FATAL: Verification failed for: $*"
        exit 1
    fi
}

# Base OS
check_tool "curl"
verify_exec curl --version
check_tool "git"
verify_exec git --version
check_tool "zip"
verify_exec zip -v

# Python
check_tool "python"
verify_exec python --version
check_tool "python3"
verify_exec python3 --version
check_tool "pip"
verify_exec pip --version

# Node
check_tool "node"
verify_exec node --version
check_tool "npm"
verify_exec npm --version

# Go
check_tool "go"
verify_exec go version

# Rust
check_tool "rustc"
verify_exec rustc --version
check_tool "cargo"
verify_exec cargo --version

# Java / Maven / Gradle
check_tool "java"
verify_exec java -version
check_tool "javac"
verify_exec javac -version
check_tool "mvn"
verify_exec mvn --version
check_tool "gradle"
verify_exec gradle --version

# Scanners / Linters
check_tool "bandit"
verify_exec bandit --version
check_tool "eslint"
verify_exec eslint --version
check_tool "sonar-scanner"
verify_exec sonar-scanner -v

check_tool "jq"
verify_exec jq --version

check_tool "shellspec"
verify_exec shellspec --version

echo "All required tools are installed and operational."
exit 0

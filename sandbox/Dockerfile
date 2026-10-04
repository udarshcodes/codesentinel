FROM ubuntu:22.04@sha256:829f6df217bcbae2b371026e81711d1a787c61b2967ad09d015063663ebafbf7

# Provenance arguments
ARG REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/udarshcodes/codesentinel"
LABEL org.opencontainers.image.revision="${REVISION}"
LABEL org.opencontainers.image.version="latest"

# Stop interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Pin tool versions
ENV PYTHON_VERSION=3.10
ENV NODE_VERSION=20.11.1
ENV GO_VERSION=1.21.8
ENV RUST_VERSION=1.75.0
ENV JAVA_VERSION=17
ENV MAVEN_VERSION=3.9.6
ENV GRADLE_VERSION=8.5
ENV SONAR_SCANNER_VERSION=5.0.1.3006
ENV ESLINT_VERSION=8.57.0

# 1. Install base OS packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    unzip \
    zip \
    build-essential \
    ca-certificates \
    software-properties-common \
    # Python 3.10 is default in 22.04
    python3 \
    python3-pip \
    python3-venv \
    # Java 17
    openjdk-17-jdk-headless \
    && rm -rf /var/lib/apt/lists/*

# Symlink python3 to python
RUN ln -s /usr/bin/python3 /usr/bin/python

# 2. Install Node.js
RUN wget -q https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz \
    && wget -q https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt \
    && grep node-v${NODE_VERSION}-linux-x64.tar.xz SHASUMS256.txt | sha256sum -c - \
    && tar -xJ -f node-v${NODE_VERSION}-linux-x64.tar.xz -C /usr/local --strip-components=1 \
    && rm node-v${NODE_VERSION}-linux-x64.tar.xz SHASUMS256.txt

# 3. Install Go
ENV GO_SHA256=538b3b143dc7f32b093c8ffe0e050c260b57fc9d57a12c4140a639a8dd2b4e4f
RUN wget -qO go.tar.gz https://golang.org/dl/go${GO_VERSION}.linux-amd64.tar.gz \
    && echo "${GO_SHA256}  go.tar.gz" | sha256sum -c - \
    && tar -C /usr/local -xzf go.tar.gz \
    && rm go.tar.gz
ENV PATH="/usr/local/go/bin:${PATH}"

# 4. Install Rust
ENV RUSTUP_HOME=/opt/rust
ENV CARGO_HOME=/opt/rust
RUN wget -qO rustup-init https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init \
    && wget -qO rustup-init.sha256 https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init.sha256 \
    && hash=$(awk '{print $1}' rustup-init.sha256) \
    && echo "${hash}  rustup-init" | sha256sum -c - \
    && chmod +x rustup-init \
    && ./rustup-init -y --default-toolchain ${RUST_VERSION} --profile minimal \
    && rm rustup-init rustup-init.sha256
ENV PATH="/opt/rust/bin:${PATH}"

# 5. Install Maven
RUN wget -q https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz \
    && wget -q https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz.sha512 \
    && hash=$(awk '{print $1}' apache-maven-${MAVEN_VERSION}-bin.tar.gz.sha512) \
    && echo "${hash}  apache-maven-${MAVEN_VERSION}-bin.tar.gz" | sha512sum -c - \
    && tar -xzf apache-maven-${MAVEN_VERSION}-bin.tar.gz -C /opt \
    && ln -s /opt/apache-maven-${MAVEN_VERSION} /opt/maven \
    && rm apache-maven-${MAVEN_VERSION}-bin.tar.gz apache-maven-${MAVEN_VERSION}-bin.tar.gz.sha512
ENV PATH="/opt/maven/bin:${PATH}"

# 6. Install Gradle
RUN wget -q https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip \
    && wget -q https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip.sha256 \
    && hash=$(awk '{print $1}' gradle-${GRADLE_VERSION}-bin.zip.sha256) \
    && echo "${hash}  gradle-${GRADLE_VERSION}-bin.zip" | sha256sum -c - \
    && unzip -q gradle-${GRADLE_VERSION}-bin.zip -d /opt \
    && ln -s /opt/gradle-${GRADLE_VERSION} /opt/gradle \
    && rm gradle-${GRADLE_VERSION}-bin.zip gradle-${GRADLE_VERSION}-bin.zip.sha256
ENV PATH="/opt/gradle/bin:${PATH}"

# 7. Install Python scanners (Global install via pip)
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# 8. Install ESLint (Global install via npm)
RUN npm install -g eslint@${ESLINT_VERSION}

# 9. Install Sonar Scanner
RUN wget -q https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux.zip \
    && wget -q https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux.zip.sha256 \
    && hash=$(awk '{print $1}' sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux.zip.sha256) \
    && echo "${hash}  sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux.zip" | sha256sum -c - \
    && unzip -q sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux.zip -d /opt \
    && ln -s /opt/sonar-scanner-${SONAR_SCANNER_VERSION}-linux /opt/sonar-scanner \
    && rm sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux.zip sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux.zip.sha256
ENV PATH="/opt/sonar-scanner/bin:${PATH}"

# 10. Copy verification script
COPY scripts/verify-tools.sh /usr/local/bin/verify-tools.sh
RUN chmod +x /usr/local/bin/verify-tools.sh

# 11. Install jq
ENV JQ_VERSION=1.7.1
ENV JQ_SHA256=5942c9b0934e510ee61eb3e30273f1b3fe2590df93933a93d7c58b81d19c8ff5
RUN wget -qO /usr/local/bin/jq "https://github.com/jqlang/jq/releases/download/jq-${JQ_VERSION}/jq-linux-amd64" \
    && echo "${JQ_SHA256}  /usr/local/bin/jq" | sha256sum -c - \
    && chmod +x /usr/local/bin/jq

# 12. Install shellspec
ENV SHELLSPEC_VERSION=0.28.1
ENV SHELLSPEC_SHA256=400d835466429a5fe6c77a62775a9173729d61dd43e05dfa893e8cf6cb511783
RUN wget -qO shellspec.tar.gz "https://github.com/shellspec/shellspec/archive/refs/tags/${SHELLSPEC_VERSION}.tar.gz" \
    && echo "${SHELLSPEC_SHA256}  shellspec.tar.gz" | sha256sum -c - \
    && tar -xzf shellspec.tar.gz -C /opt \
    && ln -s /opt/shellspec-${SHELLSPEC_VERSION}/shellspec /usr/local/bin/shellspec \
    && rm shellspec.tar.gz

# 13. Create unprivileged user "codesentinel"
RUN groupadd -g 1000 codesentinel && \
    useradd -u 1000 -g 1000 -m -s /bin/bash codesentinel

# Create sandbox workspace directory
RUN mkdir -p /sandbox/repo && chown codesentinel:codesentinel /sandbox/repo

# Set unprivileged user
USER codesentinel:codesentinel
WORKDIR /sandbox/repo

# Default command (could be overridden)
CMD ["bash"]

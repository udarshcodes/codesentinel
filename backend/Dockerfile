FROM python:3.10-slim

WORKDIR /app

# Install system dependencies needed for SAST tools and worker tasks
RUN apt-get update && \
    apt-get install -y git build-essential nodejs npm maven curl golang-go && \
    rm -rf /var/lib/apt/lists/*

# Install Rust toolchain (for cargo clippy support)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --component clippy
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Sonar Scanner
RUN npm install -g sonarqube-scanner

# Install Semgrep globally
RUN pip install --no-cache-dir semgrep

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# Copy application code
COPY . .

# Build the admin dashboard so FastAPI can serve it statically at /admin
RUN cd admin_dashboard && npm install && npm run build

# Add Healthcheck for Azure Container Apps
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start the application
CMD ["python", "main.py"]

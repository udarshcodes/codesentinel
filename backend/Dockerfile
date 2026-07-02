# Stage 1: Build the Admin Dashboard
FROM node:20-slim AS builder
WORKDIR /app
# Only copy the frontend code needed for the dashboard
COPY admin_dashboard/ ./admin_dashboard/
RUN cd admin_dashboard && npm install && npm run build

# Stage 2: Final Backend Image
FROM python:3.10-slim
WORKDIR /app

# Install ONLY the necessary system packages (git is needed for cloning repos)
RUN apt-get update && \
    apt-get install -y git curl && \
    rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# Ensure semgrep is installed
RUN pip install --no-cache-dir semgrep

# Copy backend source code
COPY . .

# Copy the built dashboard from Stage 1
COPY --from=builder /app/admin_dashboard/dist ./admin_dashboard/dist

# Link the package to the github repository so it shows up in the UI
LABEL org.opencontainers.image.source="https://github.com/udarshcodes/codesentinel"

# Add Healthcheck for Azure Container Apps
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start the application
CMD ["python", "main.py"]

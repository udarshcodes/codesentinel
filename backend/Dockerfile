FROM node:22.23.5-alpine AS admin-web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
# API-hosted admin must call its own origin, independent of the public SPA host.
ENV VITE_API_URL=""
RUN npm run build

# Build lightweight orchestrator backend
FROM python:3.12-slim

WORKDIR /app

# Link the package to the github repository so it shows up in the UI
LABEL org.opencontainers.image.source="https://github.com/udarshcodes/codesentinel"

# Ensure Python output is logged immediately in Azure
ENV PYTHONUNBUFFERED=1

# Install basic system dependencies
RUN apt-get update && \
    apt-get install -y curl git && \
    rm -rf /var/lib/apt/lists/*

# Install lightweight Python requirements (NO heavy scanning tools)
COPY backend/requirements.txt .
RUN pip install uv && uv pip install --system -r requirements.txt

# Bundle Chroma's own embedding model so historical retrieval needs no model
# download on the API request path. This runs in the remote image build.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['CodeSentinel verified repository fix'])"

# Copy application code
COPY backend/ .
COPY --from=admin-web /web/dist /opt/codesentinel/admin-web

# Add Healthcheck for Azure Container Apps
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start the orchestrator API
CMD ["python", "main.py"]

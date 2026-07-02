# Build frontend dashboard
FROM node:20 AS builder
WORKDIR /app
COPY admin_dashboard ./admin_dashboard
RUN cd admin_dashboard && npm install && npm run build

# Build lightweight orchestrator backend
FROM python:3.10-slim

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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Overwrite the unbuilt admin_dashboard with the built dist from the builder stage
COPY --from=builder /app/admin_dashboard/dist ./admin_dashboard/dist

# Add Healthcheck for Azure Container Apps
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start the orchestrator API
CMD ["python", "main.py"]

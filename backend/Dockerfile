FROM python:3.10-slim

WORKDIR /app

# Install system dependencies needed for SAST tools and worker tasks
RUN apt-get update && \
    apt-get install -y git build-essential nodejs npm maven curl && \
    rm -rf /var/lib/apt/lists/*

# Install Semgrep globally
RUN pip install --no-cache-dir semgrep

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Add Healthcheck for Azure Container Apps
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start the application
CMD ["python", "main.py"]

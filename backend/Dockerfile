FROM python:3.10-slim

WORKDIR /app

# Install system dependencies needed for SAST tools
RUN apt-get update && apt-get install -y git build-essential nodejs npm maven && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]

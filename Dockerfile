FROM python:3.11-slim

LABEL maintainer="David Elimelech <delimelech@riverbed.com>"
LABEL description="QA Test Scanners with Anomaly Detection"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY scan_stability.py .
COPY scan_infra.py .
COPY agent.py .
COPY teams.json .
COPY console_log_patterns.json .

# Create necessary directories
RUN mkdir -p /data/allure_reports /data/console_logs /output /.history /.cache

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Make agent.py executable
RUN chmod +x agent.py

# Default command - show help
ENTRYPOINT ["python", "agent.py"]
CMD ["--help"]

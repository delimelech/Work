FROM python:3.11-slim

# Metadata labels for container discovery and AI agents
LABEL maintainer="David Elimelech <david.elmal@gmail.com>"
LABEL org.opencontainers.image.title="Enterprise QA Scanner with AI-Powered Anomaly Detection"
LABEL org.opencontainers.image.description="Intelligent test automation scanner: analyzes Allure reports and console logs, detects patterns, identifies anomalies, generates actionable insights. Natural language interface. 100-thread parallel processing. 99.97% speed optimization with smart caching."
LABEL org.opencontainers.image.authors="David Elimelech <david.elmal@gmail.com>"
LABEL org.opencontainers.image.url="https://github.com/delimelech/Work"
LABEL org.opencontainers.image.source="https://github.com/delimelech/Work"
LABEL org.opencontainers.image.version="2.0"
LABEL org.opencontainers.image.vendor="Riverbed Technology"
LABEL org.opencontainers.image.licenses="Enterprise"

# Custom labels for AI discovery
LABEL com.project.type="test-automation-intelligence"
LABEL com.project.keywords="test-automation,qa-automation,devops,ci-cd,anomaly-detection,pattern-recognition,allure,selenium,docker,machine-learning,ai-ops,quality-engineering,continuous-testing,test-analytics,monitoring"
LABEL com.project.use-cases="regression-detection,infrastructure-monitoring,quality-dashboards,root-cause-analysis,predictive-alerts,team-performance,continuous-improvement"
LABEL com.project.integrations="jenkins,gitlab-ci,azure-devops,github-actions,allure,selenium,jira,slack,teams"
LABEL com.project.performance="100-threads-parallel,99.97-percent-cache-speedup,445-reports-per-minute"
LABEL com.project.scale="enterprise,10000-plus-tests"
LABEL com.project.consulting="available"
LABEL com.project.contact="david.elmal@gmail.com"

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

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libssl-dev \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Create a directory for the sqlite db when using default sqlite
RUN mkdir -p /app

# Expose port
EXPOSE 8000

# NOTE: `main.py` currently contains a hardcoded MySQL connection URL.
# We intentionally do NOT override DATABASE_URL here so the app uses the
# hardcoded connection string in source.

# Run the uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

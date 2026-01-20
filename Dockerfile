FROM python:3.11-slim

WORKDIR /app

# Install basic system tools
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only to save space/time)
# We need to install the browser + systems deps
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# Expose the standard FastAPI port
EXPOSE 8000

# Use the PORT environment variable provided by Railway, default to 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]

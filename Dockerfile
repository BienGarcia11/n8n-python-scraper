FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Node.js
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    gnupg2 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright system dependencies (before installing playwright)
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies (includes playwright)
RUN pip install --no-cache-dir -r requirements.txt

# Install Python Playwright browsers (version-specific)
RUN python -m playwright install --with-deps chromium

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose port (for health checks if needed)
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Run the application
CMD ["python", "main.py"]

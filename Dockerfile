FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    curl \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libxshmfence1 \
    libxext6 \
    libxinerama1 \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first (so Playwright installs to their home directory)
RUN useradd -m appuser

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies as appuser
USER appuser
RUN pip install --no-cache-dir --user -r requirements.txt

# Install Playwright browsers as appuser (this puts them in /home/appuser/.cache/ms-playwright/)
RUN playwright install --with-deps chromium

# Copy application code (as root for proper ownership)
USER root
COPY . .
RUN chown -R appuser:appuser /app

# Switch back to appuser for running
USER appuser

# Set Playwright to use the browser cache path
ENV PLAYWRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "supabase_scraper:app", "--host", "0.0.0.0", "--port", "8000"]

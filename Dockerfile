FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies and Playwright browser dependencies
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

# Create non-root user
RUN useradd -m appuser

# Copy requirements
COPY requirements.txt .

# Install Python dependencies as ROOT (system-wide)
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright chromium browser
RUN playwright install chromium

# Copy application code and set ownership
COPY . .
RUN chown -R appuser:appuser /app
RUN chown -R appuser:appuser /root/.cache/ms-playwright

# Switch to appuser for running
USER appuser

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "supabase_scraper:app", "--host", "0.0.0.0", "--port", "8000"]

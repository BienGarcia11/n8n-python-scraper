# Use official Playwright image with pre-installed Chromium
FROM mcr.microsoft.com/playwright:v1.40.0-jammy

# Set working directory
WORKDIR /app

# Install Python and system build tools
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    gcc \
    g++ \
    make \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m appuser

# Copy application code
COPY . .
RUN chown -R appuser:appuser /app

# Switch to appuser for running
USER appuser

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "supabase_scraper:app", "--host", "0.0.0.0", "--port", "8000"]

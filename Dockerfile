# Use official Python 3.11 image (based on Debian Bookworm)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install Playwright dependencies only
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libglib2.0-0 \
    libxkbcommon-x11-0 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN python -m playwright install chromium

# Copy application files
COPY scraper.py .
COPY .env.example .env

# Create a non-root user
RUN useradd -m -u 1000 scraperuser && chown -R scraperuser:scraperuser /app
USER scraperuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Run the scraper
CMD ["python", "scraper.py"]

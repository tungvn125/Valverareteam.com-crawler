# ============================================================
# VVR-Scraper Docker Image
# Multi-stage build: wheel/venv dependencies -> runtime
# ============================================================

# --- Stage 1: Builder (install Python deps) ---
FROM python:3.12-slim AS builder

WORKDIR /build
ENV PATH="/opt/venv/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install build tools needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv

# Copy package metadata and source needed for editable install
COPY pyproject.toml ./
COPY vvr_scraper ./vvr_scraper

RUN pip install --no-cache-dir -e .


# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

# Metadata
LABEL maintainer="VVR-Scraper Contributors"
LABEL description="Valvrare Team Web Novel Scraper - Ebook, Audiobook, Cinematic Video"

ENV PATH="/opt/venv/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install system dependencies:
#   - FFmpeg: audio/video processing
#   - Playwright system deps: Chromium browser for scraping & video rendering
#   - curl: healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    # Playwright/Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Install Playwright Chromium browser
RUN playwright install chromium

# Keep browser binaries available to the non-root runtime user
RUN chmod -R 755 /ms-playwright

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash vvr
USER vvr
WORKDIR /home/vvr/app

# Copy application source code
COPY --chown=vvr:vvr . .

# Create directories for persistent data
RUN mkdir -p /home/vvr/.config/vvr-scraper \
    && mkdir -p /home/vvr/app/novels \
    && mkdir -p /home/vvr/app/error-logs

# Volumes for persistent data
VOLUME ["/home/vvr/app/novels", "/home/vvr/.config/vvr-scraper"]

# Default port for Web UI + OPDS
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: start the web server
# Override with: docker run vvr-scraper <slug> -f EPUB
ENTRYPOINT ["vvrt"]
CMD ["web", "--host", "0.0.0.0", "--port", "8000"]

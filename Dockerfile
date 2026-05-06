# ─────────────────────────────────────────────────────────────────────────────
#  Dockerfile — AI Video Automation Pipeline
#  Base: Python 3.11 slim + ffmpeg + chromium
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── System dependencies (ffmpeg + chromium for Playwright) ────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        chromium \
        chromium-driver \
        fonts-liberation \
        libglib2.0-0 \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        wget \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps || true

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# Create directories expected at runtime
RUN mkdir -p downloads/raw downloads/edited logs secrets assets

# ── Default command ───────────────────────────────────────────────────────────
# Override GAME and other vars via environment variables or docker run args
ENV GAME="One State RP"
ENV LANDING_URL="https://example.com"
ENV BRANDING_IMAGE="branding.png"
ENV MAX_VIDEOS=3

CMD python main.py \
        "${GAME}" \
        --branding "${BRANDING_IMAGE}" \
        --landing-url "${LANDING_URL}" \
        --max-videos "${MAX_VIDEOS}"

FROM python:3.11-slim AS base

WORKDIR /app

# System deps for OpenCV + ffmpeg (required by openai-whisper) + curl (healthcheck fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglx-mesa0 \
    libglib2.0-0 \
    gcc \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
# Step 1: bootstrap with a setuptools version that still ships pkg_resources
#         (setuptools>=70 removed it, breaking openai-whisper's legacy setup.py)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "setuptools>=40,<70" wheel && \
    pip install --no-cache-dir --no-build-isolation openai-whisper==20240930 && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# Use official Python lightweight image
FROM python:3.10-slim

# Install system dependencies required by MoviePy and Whisper
RUN apt-get update && apt-get install -y \
    ffmpeg \
    imagemagick \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Fix ImageMagick policy to allow editing/reading text and PDFs (needed by MoviePy TextClip)
RUN sed -i 's/<policy domain="path" rights="none" pattern="@\*"/<!-- <policy domain="path" rights="none" pattern="@\*" -->/g' /etc/ImageMagick-6/policy.xml || true

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files to container
COPY . .

# Set environment variables for Flask
ENV PYTHONUNBUFFERED=1

# Hugging Face Spaces require the app to run on port 7860
# We use gunicorn to run the Flask app
CMD exec gunicorn --bind 0.0.0.0:7860 --workers 1 --threads 8 --timeout 0 web_app:app

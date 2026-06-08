# Use the official Python slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install git, which is required for claws_opened git operations
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY python/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Compile python files to verify syntax at build time
RUN python -m compileall python/

# Default command to run the Telegram bot daemon
CMD ["python", "python/main.py", "telegram"]

# Use Python Alpine as the base image for security and size benefits
FROM python:alpine

# Set metadata
LABEL maintainer="Daikin XML Listener Middleware"
LABEL version="1.0"
LABEL description="Middleware to aggregate XML event streams from Avigilon ACM to S3"

# Set working directory
WORKDIR /app

# Copy only the requirements file first to leverage Docker cache
COPY src/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/server.py .

# Create non-root user and directories
# Note: Alpine uses adduser instead of useradd
RUN adduser -D -u 1001 -G root appuser && \
    mkdir -p /app/data && \
    chown -R appuser:root /app && \
    chmod -R 755 /app

# Set environment variables
ENV PORT=8080 \
    ROTATION_INTERVAL=3600 \
    MAX_FILE_SIZE=10485760 \
    PREFIX="xml-events/" \
    OUTPUT_FORMAT="xml" \
    CURRENT_FILE="/app/data/current.xml" \
    TEMP_FILE="/app/data/temp.xml" \
    PYTHONUNBUFFERED=1

# Expose the port
EXPOSE ${PORT}

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.connect(('localhost', ${PORT})); s.close()"

# Switch to non-root user
USER appuser

# Run the application
CMD ["python", "server.py"]
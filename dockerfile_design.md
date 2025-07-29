# Dockerfile Design

## Overview
The Dockerfile will package the XML listener middleware into a lightweight, secure, and configurable container image based on Python 3.12. It will include all necessary dependencies, expose the appropriate port, and set up the environment for running the middleware.

## Base Image Selection
We'll use `python:3.12-slim` as our base image for several reasons:
- It provides Python 3.12, which is the target version for our application
- The "slim" variant is significantly smaller than the full image, reducing container size
- It includes only essential packages, improving security posture
- It's based on Debian, providing a stable and well-supported environment

## Dockerfile Structure

```dockerfile
# Use Python 3.12 slim as the base image
FROM python:3.12-slim

# Set metadata
LABEL maintainer="Daikin XML Listener Middleware"
LABEL version="1.0"
LABEL description="Middleware to aggregate XML event streams from Avigilon ACM to S3"

# Set working directory
WORKDIR /app

# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .

# Create directory for temporary files
RUN mkdir -p /app/data

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

# Run the application
CMD ["python", "server.py"]
```

## Requirements File
We'll create a `requirements.txt` file to specify the exact dependencies:

```
boto3==1.28.38
botocore==1.31.38
```

## Security Considerations

1. **Minimal Base Image**: Using the slim variant reduces attack surface
2. **Non-root User**: Consider adding a dedicated user for running the application
3. **Fixed Versions**: Pinning dependency versions prevents unexpected changes
4. **No Secrets**: AWS credentials should be provided at runtime, not baked into the image
5. **Read-only Filesystem**: Consider making the filesystem read-only except for data directory

## Multi-stage Build Option
For even smaller images, we could use a multi-stage build:

```dockerfile
# Build stage
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final stage
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /install /usr/local
COPY server.py .

# Rest of the Dockerfile remains the same
```

## Environment Variables

The container will be configurable through the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| PORT | TCP port to listen on | 8080 |
| BUCKET_NAME | S3 bucket for uploads | (required) |
| PREFIX | S3 key prefix | xml-events/ |
| ROTATION_INTERVAL | File rotation interval in seconds | 3600 |
| MAX_FILE_SIZE | Max file size in bytes | 10485760 (10MB) |
| AWS_ACCESS_KEY_ID | AWS access key | (required) |
| AWS_SECRET_ACCESS_KEY | AWS secret key | (required) |
| AWS_REGION | AWS region | (required) |
| OUTPUT_FORMAT | Output format (xml or json) | xml |

## Build and Run Instructions

### Build
```bash
docker build -t xml-stream-aggregator .
```

### Run
```bash
docker run -d \
  -p 8080:8080 \
  -e BUCKET_NAME=my-bucket \
  -e AWS_ACCESS_KEY_ID=your-access-key \
  -e AWS_SECRET_ACCESS_KEY=your-secret-key \
  -e AWS_REGION=us-west-2 \
  --name xml-listener \
  xml-stream-aggregator
```

## Volume Mounting (Optional)
For debugging or data persistence, consider mounting volumes:

```bash
docker run -d \
  -p 8080:8080 \
  -e BUCKET_NAME=my-bucket \
  -e AWS_ACCESS_KEY_ID=your-access-key \
  -e AWS_SECRET_ACCESS_KEY=your-secret-key \
  -e AWS_REGION=us-west-2 \
  -v /path/to/logs:/app/logs \
  --name xml-listener \
  xml-stream-aggregator
```

## Health Check (Optional)
For better container orchestration, consider adding a health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD nc -z localhost $PORT || exit 1
```

## Optimization Considerations

1. **Layer Caching**: Structure the Dockerfile to maximize cache usage
2. **Minimal Dependencies**: Include only what's necessary
3. **Image Size**: Use slim variant and consider multi-stage builds
4. **Startup Time**: Keep the image lightweight for faster container startup
5. **Resource Limits**: Consider setting memory and CPU limits
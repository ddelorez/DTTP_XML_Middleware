# Quick Start Guide for Daikin XML Listener

This guide will help you get the Daikin XML Listener middleware up and running quickly.

## Prerequisites

- Docker installed on your system
- AWS account with S3 bucket created
- AWS credentials (Access Key ID and Secret Access Key)
- Avigilon ACM system for sending XML events

## Step 1: Build the Docker Image

```bash
# Clone the repository (or extract the provided files)
cd "Daikin XML Listener"

# Build the Docker image
docker build -t xml-stream-aggregator .
```

## Option 1: Using Docker Compose (Recommended)

Docker Compose simplifies environment variable configuration and provides additional security features.

### Step 2a: Create Environment File

Create a `.env` file in the project directory:

```bash
# Create .env file
cat > .env << EOF
# Required S3 Configuration
BUCKET_NAME=your-s3-bucket-name
AWS_REGION=us-west-2

# For quick testing (not recommended for production)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# Optional Configuration
OUTPUT_FORMAT=xml
ROTATION_INTERVAL=3600
MAX_FILE_SIZE=10485760
EOF
```

### Step 2b: Run with Docker Compose

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Step 2c: Production Setup with Secrets

For production, use Docker secrets instead of environment variables:

```bash
# Create secrets directory
mkdir -p secrets
chmod 700 secrets

# Store AWS credentials securely
echo -n "your-access-key" > secrets/aws_access_key_id.txt
echo -n "your-secret-key" > secrets/aws_secret_access_key.txt
chmod 600 secrets/*.txt

# Update .env to remove AWS credentials
cat > .env << EOF
BUCKET_NAME=your-s3-bucket-name
AWS_REGION=us-west-2
OUTPUT_FORMAT=xml
EOF

# Run with secrets
docker-compose up -d
```

## Option 2: Using Docker Run

### Step 2: Set Environment Variables

```bash
# Required environment variables
export BUCKET_NAME=your-s3-bucket-name
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_REGION=us-west-2  # or your preferred region

# Optional: Set output format to JSON (default is XML)
export OUTPUT_FORMAT=json
```

### Step 3: Run the Container

```bash
# Run the middleware container
docker run -d \
  --name xml-listener \
  -p 8080:8080 \
  -e BUCKET_NAME=$BUCKET_NAME \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_REGION=$AWS_REGION \
  -e OUTPUT_FORMAT=$OUTPUT_FORMAT \
  xml-stream-aggregator

# Check that the container is running
docker ps

# View logs
docker logs -f xml-listener
```

## Step 4: Configure Avigilon ACM

1. In the ACM system, go to Settings → External Systems → Collaboration
2. Create a new XML collaboration:
   - **Host**: IP address of the machine running the middleware
   - **Port**: 8080 (or your configured port)
   - **Require TCP**: Enabled
3. Select the events you want to stream
4. Save and activate the collaboration

## Step 5: Test the Setup

### Option 1: Use the Test Event Generator

```bash
# Make the script executable
chmod +x generate_test_events.py

# Send 10 test events
python3 generate_test_events.py --count 10

# Send alarm events continuously
python3 generate_test_events.py --count 100 --interval 0.5 --type alarm
```

### Option 2: Use the Validation Script

```bash
# Make the script executable
chmod +x validate.sh

# Run validation
./validate.sh
```

### Option 3: Manual Test with netcat

```bash
# Send a single test event
echo '<EVENT><plasectrxEventname>Test Event</plasectrxEventname></EVENT>' | nc localhost 8080
```

## Step 6: Verify S3 Uploads

```bash
# List files in your S3 bucket
aws s3 ls s3://$BUCKET_NAME/xml-events/

# Download and inspect a file
aws s3 cp s3://$BUCKET_NAME/xml-events/20250729_123456.xml ./test-download.xml
cat test-download.xml
```

## Common Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| PORT | TCP listening port | 8080 |
| ROTATION_INTERVAL | File rotation interval (seconds) | 3600 |
| MAX_FILE_SIZE | Max file size before rotation (bytes) | 10485760 |
| OUTPUT_FORMAT | Output format (xml or json) | xml |
| PREFIX | S3 key prefix | xml-events/ |
| USE_DATE_FOLDERS | Organize files by date (true/false) | false |

## Docker Compose vs Docker Run

### Benefits of Docker Compose

1. **Easier Configuration**: All settings in one `.env` file
2. **Security Features**: Built-in resource limits, read-only filesystem
3. **Health Checks**: Automatic container health monitoring
4. **Networking**: Isolated internal network
5. **Secrets Management**: Secure credential handling
6. **Simpler Commands**: No need for long docker run commands

### When to Use Each

- **Docker Compose**: Production deployments, testing with multiple configurations, enhanced security requirements
- **Docker Run**: Quick testing, simple deployments, CI/CD pipelines

## Troubleshooting

### Container won't start
```bash
# Check container logs
docker logs xml-listener

# Common issues:
# - Missing BUCKET_NAME environment variable
# - Invalid AWS credentials
# - S3 bucket doesn't exist or no access
```

### No files in S3
```bash
# Check if file rotation has occurred (default is hourly)
# Force rotation by sending many events or reducing ROTATION_INTERVAL:
docker run -d \
  --name xml-listener \
  -p 8080:8080 \
  -e BUCKET_NAME=$BUCKET_NAME \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_REGION=$AWS_REGION \
  -e ROTATION_INTERVAL=60 \
  xml-stream-aggregator
```

### Connection refused
```bash
# Ensure port 8080 is not already in use
netstat -an | grep 8080

# Check firewall rules
# Ensure Docker port mapping is correct
```

### Docker Compose Issues
```bash
# If docker-compose command not found
# Install Docker Compose:
# https://docs.docker.com/compose/install/

# Check if .env file is loaded
docker-compose config

# Verify environment variables
docker-compose exec xml-listener env | grep AWS

# Force rebuild after changes
docker-compose up -d --build
```

## Next Steps

1. Set up Snowflake integration (see README.md)
2. Configure monitoring and alerting
3. Customize rotation intervals based on your needs
4. Consider enabling JSON output for better Snowflake performance

For detailed documentation, see [README.md](README.md).
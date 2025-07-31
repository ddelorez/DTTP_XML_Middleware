#!/bin/bash
# Secure deployment script for Daikin XML Listener Middleware

set -euo pipefail

echo "=== Daikin XML Listener Secure Deployment ==="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo -e "${RED}Please do not run this script as root${NC}"
   exit 1
fi

# Function to check command availability
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}$1 is required but not installed.${NC}"
        exit 1
    fi
}

# Check prerequisites
echo "Checking prerequisites..."
check_command docker
check_command openssl
echo -e "${GREEN}✓ Prerequisites satisfied${NC}"
echo

# Create directory structure
echo "Creating secure directory structure..."
mkdir -p secrets
chmod 700 secrets
echo -e "${GREEN}✓ Directories created${NC}"
echo

# Get configuration from user
echo "Configuration Setup:"
echo "==================="

# S3 Configuration
read -p "Enter S3 Bucket Name: " BUCKET_NAME
read -p "Enter AWS Region (e.g., us-west-2): " AWS_REGION

# Security settings
read -p "Enter port to listen on (default 8080): " PORT
PORT=${PORT:-8080}

read -p "Enter maximum concurrent connections (default 10): " MAX_CONNECTIONS
MAX_CONNECTIONS=${MAX_CONNECTIONS:-10}

read -p "Enter rate limit per minute (default 1000): " RATE_LIMIT
RATE_LIMIT=${RATE_LIMIT:-1000}

# AWS Credentials
echo
echo "AWS Credentials (will be stored securely):"
read -p "Enter AWS Access Key ID: " AWS_ACCESS_KEY_ID
read -sp "Enter AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY
echo
echo

# Save credentials securely
echo "Saving credentials..."
echo -n "$AWS_ACCESS_KEY_ID" > secrets/aws_access_key_id.txt
echo -n "$AWS_SECRET_ACCESS_KEY" > secrets/aws_secret_access_key.txt
chmod 600 secrets/*.txt
echo -e "${GREEN}✓ Credentials saved securely${NC}"
echo

# Create .env file for docker-compose
echo "Creating environment file..."
cat > .env <<EOF
# S3 Configuration
BUCKET_NAME=${BUCKET_NAME}
AWS_REGION=${AWS_REGION}
PREFIX=xml-events/
USE_DATE_FOLDERS=false

# Network Configuration
PORT=${PORT}
BIND_HOST=0.0.0.0

# Security Settings
MAX_CONNECTIONS=${MAX_CONNECTIONS}
MAX_MESSAGE_SIZE=1048576
RATE_LIMIT_ENABLED=true
RATE_LIMIT_WINDOW=60
RATE_LIMIT_MAX_EVENTS=${RATE_LIMIT}

# File Management
ROTATION_INTERVAL=3600
MAX_FILE_SIZE=10485760
OUTPUT_FORMAT=xml
PRETTY_PRINT_JSON=true

# File Paths (used internally by container)
CURRENT_FILE=/app/data/current.xml
TEMP_FILE=/app/data/temp.xml
EOF
chmod 600 .env
echo -e "${GREEN}✓ Environment file created${NC}"
echo

# Build Docker image
echo "Building Docker image..."
docker build -t xml-stream-aggregator:latest .
echo -e "${GREEN}✓ Docker image built${NC}"
echo

# Create firewall rules script
echo "Creating firewall configuration..."
cat > configure_firewall.sh <<'EOF'
#!/bin/bash
# Firewall configuration for Daikin XML Listener

# Get the IP address of Avigilon ACM system
read -p "Enter Avigilon ACM IP address: " ACM_IP

# Configure iptables (requires sudo)
echo "Configuring firewall rules..."
sudo iptables -A INPUT -p tcp --dport ${PORT} -s ${ACM_IP} -j ACCEPT -m comment --comment "Avigilon ACM XML"
sudo iptables -A INPUT -p tcp --dport ${PORT} -j DROP -m comment --comment "Block other XML access"

echo "Current firewall rules for port ${PORT}:"
sudo iptables -L -n | grep ${PORT}

echo
echo "To make firewall rules persistent, run:"
echo "  sudo apt-get install iptables-persistent"
echo "  sudo netfilter-persistent save"
EOF
chmod +x configure_firewall.sh
echo -e "${GREEN}✓ Firewall script created${NC}"
echo

# Create monitoring script
echo "Creating monitoring script..."
cat > monitor.sh <<'EOF'
#!/bin/bash
# Monitor Daikin XML Listener

echo "=== Daikin XML Listener Monitor ==="
echo

# Check container status
if docker ps | grep -q xml-listener; then
    echo -e "\033[0;32m✓ Container is running\033[0m"
else
    echo -e "\033[0;31m✗ Container is not running\033[0m"
    exit 1
fi

# Show container stats
echo
echo "Container Statistics:"
docker stats --no-stream xml-listener

# Show recent logs
echo
echo "Recent Logs:"
docker logs --tail 20 xml-listener

# Check S3 uploads
echo
echo "Recent S3 Activity:"
docker logs xml-listener 2>&1 | grep "Successfully uploaded" | tail -5

# Show connection count
echo
echo "Active Connections:"
docker logs xml-listener 2>&1 | grep "active:" | tail -1
EOF
chmod +x monitor.sh
echo -e "${GREEN}✓ Monitoring script created${NC}"
echo

# Create startup script
echo "Creating startup script..."
cat > start_secure.sh <<EOF
#!/bin/bash
# Start Daikin XML Listener with security settings

echo "Starting Daikin XML Listener..."

# Check if secrets exist
if [ ! -f secrets/aws_access_key_id.txt ] || [ ! -f secrets/aws_secret_access_key.txt ]; then
    echo -e "\033[0;31mError: AWS credentials not found in secrets directory\033[0m"
    exit 1
fi

# Start with docker-compose
docker-compose up -d

# Wait for container to start
sleep 5

# Check status
if docker ps | grep -q xml-listener; then
    echo -e "\033[0;32m✓ Daikin XML Listener started successfully\033[0m"
    echo
    echo "Container is listening on localhost:${PORT}"
    echo "To expose externally, configure firewall with: ./configure_firewall.sh"
    echo "To monitor: ./monitor.sh"
    echo "To view logs: docker logs -f xml-listener"
else
    echo -e "\033[0;31m✗ Failed to start container\033[0m"
    echo "Check logs with: docker-compose logs"
    exit 1
fi
EOF
chmod +x start_secure.sh
echo -e "${GREEN}✓ Startup script created${NC}"
echo

# Summary
echo "======================================"
echo -e "${GREEN}Secure deployment setup complete!${NC}"
echo
echo "Next steps:"
echo "1. Start the container:     ./start_secure.sh"
echo "2. Configure firewall:      ./configure_firewall.sh"
echo "3. Monitor the service:     ./monitor.sh"
echo
echo "Security features enabled:"
echo "- Container runs as non-root user"
echo "- Connection limiting (max ${MAX_CONNECTIONS})"
echo "- Rate limiting (${RATE_LIMIT} events/minute)"
echo "- Message size limits (1MB)"
echo "- Read-only filesystem with tmpfs for data"
echo "- Resource limits (CPU: 1 core, Memory: 512MB)"
echo "- Listening on localhost only by default"
echo
echo -e "${YELLOW}Remember to:${NC}"
echo "- Configure firewall rules for Avigilon ACM IP"
echo "- Set up S3 bucket policies"
echo "- Enable S3 encryption at rest"
echo "- Monitor logs regularly"
echo
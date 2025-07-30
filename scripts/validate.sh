#!/bin/bash
# validate.sh - Validation script for Daikin XML Listener Middleware

echo "=== Daikin XML Listener Middleware Validation ==="
echo

# Check if required environment variables are set
check_env_vars() {
    echo "Checking environment variables..."
    
    if [ -z "$BUCKET_NAME" ]; then
        echo "✗ BUCKET_NAME is not set"
        echo "  Please set: export BUCKET_NAME=your-bucket-name"
        exit 1
    else
        echo "✓ BUCKET_NAME is set: $BUCKET_NAME"
    fi
    
    if [ -z "$AWS_REGION" ]; then
        echo "✗ AWS_REGION is not set"
        echo "  Please set: export AWS_REGION=your-region"
        exit 1
    else
        echo "✓ AWS_REGION is set: $AWS_REGION"
    fi
    
    echo
}

# Check if container is running
check_container() {
    echo "Checking Docker container..."
    
    if [ $(docker ps -q -f name=xml-listener) ]; then
        echo "✓ Container 'xml-listener' is running"
    else
        echo "✗ Container 'xml-listener' is not running"
        echo "  Run: docker run -d --name xml-listener -p 8080:8080 -e BUCKET_NAME=$BUCKET_NAME -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY -e AWS_REGION=$AWS_REGION xml-stream-aggregator"
        exit 1
    fi
    
    echo
}

# Check if port is accessible
check_port() {
    echo "Checking port availability..."
    
    if nc -z localhost 8080 2>/dev/null; then
        echo "✓ Port 8080 is open and accessible"
    else
        echo "✗ Port 8080 is not accessible"
        exit 1
    fi
    
    echo
}

# Send test event
send_test_event() {
    echo "Sending test event..."
    
    # Generate test event with timestamp
    TIMESTAMP=$(date -u +"%Y%m%d%H%M%S")
    TEST_EVENT="<EVENT>
<plasectrxGatewayDN>cn=test-validation,ou=gateways,dc=plasec</plasectrxGatewayDN>
<plasectrxRecdate>${TIMESTAMP}-0000</plasectrxRecdate>
<plasectrxRecdateUTC>${TIMESTAMP}Z</plasectrxRecdateUTC>
<plasectrxEvtypename>Validation</plasectrxEvtypename>
<plasectrxEventname>Validation Test Event</plasectrxEventname>
<plasectrxSourcename>Validation Script</plasectrxSourcename>
<plasectrxIsAlarm>0</plasectrxIsAlarm>
</EVENT>"
    
    echo "$TEST_EVENT" | nc localhost 8080
    
    if [ $? -eq 0 ]; then
        echo "✓ Test event sent successfully"
    else
        echo "✗ Failed to send test event"
        exit 1
    fi
    
    echo
}

# Wait for file rotation
wait_for_rotation() {
    echo "Waiting for file rotation (this may take up to 60 seconds)..."
    
    # Check container logs for rotation
    TIMEOUT=70
    ELAPSED=0
    
    while [ $ELAPSED -lt $TIMEOUT ]; do
        if docker logs xml-listener 2>&1 | grep -q "File rotated and uploaded successfully"; then
            echo "✓ File rotation detected in logs"
            return 0
        fi
        
        sleep 5
        ELAPSED=$((ELAPSED + 5))
        echo -n "."
    done
    
    echo
    echo "⚠ Warning: File rotation not detected in logs within timeout"
    echo "  This might be normal if ROTATION_INTERVAL is set to a large value"
    echo
}

# Check S3 for uploaded files
check_s3_upload() {
    echo "Checking S3 bucket for uploaded files..."
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        echo "⚠ AWS CLI not found, skipping S3 check"
        echo "  Install AWS CLI to enable S3 validation"
        return
    fi
    
    # List files in S3
    FILES=$(aws s3 ls s3://$BUCKET_NAME/${PREFIX:-xml-events/} --region $AWS_REGION 2>&1)
    
    if [ $? -eq 0 ]; then
        if echo "$FILES" | grep -qE '\.(xml|json)$'; then
            echo "✓ Files found in S3 bucket:"
            echo "$FILES" | grep -E '\.(xml|json)$' | tail -5
            
            # Try to download and check the latest file
            LATEST_FILE=$(echo "$FILES" | grep -E '\.(xml|json)$' | tail -1 | awk '{print $4}')
            if [ ! -z "$LATEST_FILE" ]; then
                echo
                echo "Downloading latest file: $LATEST_FILE"
                aws s3 cp s3://$BUCKET_NAME/${PREFIX:-xml-events/}$LATEST_FILE ./validation_download.xml --region $AWS_REGION
                
                if grep -q "Validation Test Event" ./validation_download.xml 2>/dev/null; then
                    echo "✓ Validation event found in uploaded file!"
                else
                    echo "⚠ Validation event not found in latest file (might be in a different file)"
                fi
                
                rm -f ./validation_download.xml
            fi
        else
            echo "✗ No XML or JSON files found in S3 bucket"
        fi
    else
        echo "✗ Failed to list S3 bucket contents"
        echo "  Error: $FILES"
    fi
    
    echo
}

# Check container logs for errors
check_logs() {
    echo "Checking container logs for errors..."
    
    ERROR_COUNT=$(docker logs xml-listener 2>&1 | grep -c "ERROR")
    
    if [ $ERROR_COUNT -eq 0 ]; then
        echo "✓ No errors found in container logs"
    else
        echo "⚠ Found $ERROR_COUNT error(s) in container logs"
        echo "  Recent errors:"
        docker logs xml-listener 2>&1 | grep "ERROR" | tail -5
    fi
    
    echo
}

# Main validation flow
main() {
    echo "Starting validation at $(date)"
    echo
    
    # Run validation steps
    check_env_vars
    check_container
    check_port
    send_test_event
    wait_for_rotation
    check_s3_upload
    check_logs
    
    echo "=== Validation Summary ==="
    echo "✓ Basic connectivity and functionality verified"
    echo "  For full validation, check S3 bucket for uploaded files"
    echo "  Monitor container logs: docker logs -f xml-listener"
    echo
    echo "Validation completed at $(date)"
}

# Run main function
main
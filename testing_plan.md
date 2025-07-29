# Testing Plan for Daikin XML Listener Middleware

This document outlines the comprehensive testing strategy for the Daikin XML Listener middleware, including unit tests, integration tests, performance tests, and validation procedures.

## Table of Contents

- [Testing Approach](#testing-approach)
- [Test Environment Setup](#test-environment-setup)
- [Unit Tests](#unit-tests)
- [Integration Tests](#integration-tests)
- [Performance Tests](#performance-tests)
- [Validation Procedures](#validation-procedures)
- [Test Data](#test-data)
- [Continuous Integration](#continuous-integration)
- [Test Reporting](#test-reporting)

## Testing Approach

The testing strategy follows a multi-layered approach:

1. **Unit Tests**: Verify individual components in isolation
2. **Integration Tests**: Validate interactions between components
3. **Performance Tests**: Ensure the system meets performance requirements
4. **Validation Procedures**: Manual and automated checks for correct operation

All tests will be automated where possible, with clear documentation for manual validation steps.

## Test Environment Setup

### Local Development Environment

```python
# test_setup.py
import os
import tempfile
import boto3
from moto import mock_s3

def setup_test_environment():
    """Set up a test environment with mocked AWS services."""
    # Create temporary directory for test files
    temp_dir = tempfile.mkdtemp()
    
    # Set environment variables for testing
    os.environ["CURRENT_FILE"] = os.path.join(temp_dir, "current.xml")
    os.environ["TEMP_FILE"] = os.path.join(temp_dir, "temp.xml")
    os.environ["BUCKET_NAME"] = "test-bucket"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "test-key"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret"
    
    # Return the temp directory for cleanup
    return temp_dir

def teardown_test_environment(temp_dir):
    """Clean up the test environment."""
    # Remove temporary files
    for filename in os.listdir(temp_dir):
        os.remove(os.path.join(temp_dir, filename))
    os.rmdir(temp_dir)
    
    # Clear environment variables
    for var in ["CURRENT_FILE", "TEMP_FILE", "BUCKET_NAME", "AWS_REGION", 
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]:
        if var in os.environ:
            del os.environ[var]
```

### Docker Test Environment

```bash
#!/bin/bash
# setup_docker_test.sh

# Build the test image
docker build -t xml-stream-aggregator:test .

# Create a local network for testing
docker network create xml-test-network

# Start a mock S3 container
docker run -d --name mock-s3 \
  --network xml-test-network \
  -p 9000:9000 \
  adobe/s3mock:latest

# Start the middleware container with test configuration
docker run -d --name xml-listener-test \
  --network xml-test-network \
  -p 8080:8080 \
  -e BUCKET_NAME=test-bucket \
  -e AWS_ACCESS_KEY_ID=test-key \
  -e AWS_SECRET_ACCESS_KEY=test-secret \
  -e AWS_REGION=us-east-1 \
  -e AWS_ENDPOINT_URL=http://mock-s3:9000 \
  xml-stream-aggregator:test
```

## Unit Tests

### TCP Server Tests

```python
# test_tcp_server.py
import unittest
import socket
import threading
import time
from server import TCPServer

class TestTCPServer(unittest.TestCase):
    def setUp(self):
        self.config = {
            "PORT": 8081,
            "CURRENT_FILE": "/tmp/test_current.xml"
        }
        self.server = TCPServer(self.config)
        self.server_thread = threading.Thread(target=self.server.start)
        self.server_thread.daemon = True
        self.server_thread.start()
        time.sleep(0.1)  # Allow server to start
        
    def tearDown(self):
        self.server.stop()
        self.server_thread.join(timeout=1)
        
    def test_server_accepts_connection(self):
        """Test that the server accepts a client connection."""
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("localhost", 8081))
        self.assertTrue(client.fileno() > 0)  # Valid socket
        client.close()
        
    def test_server_receives_data(self):
        """Test that the server receives and stores data."""
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("localhost", 8081))
        test_data = b"<EVENT><plasectrxEventname>Test Event</plasectrxEventname></EVENT>"
        client.sendall(test_data)
        client.close()
        time.sleep(0.1)  # Allow server to process
        
        with open("/tmp/test_current.xml", "rb") as f:
            content = f.read()
        self.assertEqual(content, test_data)
        
    def test_server_handles_multiple_clients(self):
        """Test that the server can handle multiple client connections."""
        clients = []
        for i in range(5):
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(("localhost", 8081))
            clients.append(client)
            
        for i, client in enumerate(clients):
            test_data = f"<EVENT><plasectrxEventname>Test Event {i}</plasectrxEventname></EVENT>".encode()
            client.sendall(test_data)
            client.close()
            
        time.sleep(0.1)  # Allow server to process
        
        with open("/tmp/test_current.xml", "rb") as f:
            content = f.read()
        
        for i in range(5):
            self.assertIn(f"Test Event {i}".encode(), content)
```

### File Manager Tests

```python
# test_file_manager.py
import unittest
import os
import time
import threading
from unittest.mock import MagicMock
from server import FileManager

class TestFileManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = setup_test_environment()
        self.current_file = os.environ["CURRENT_FILE"]
        self.temp_file = os.environ["TEMP_FILE"]
        
        # Create mock S3 client
        self.mock_s3_client = MagicMock()
        self.mock_s3_client.upload_file.return_value = True
        
        # Create file manager
        self.config = {
            "CURRENT_FILE": self.current_file,
            "TEMP_FILE": self.temp_file,
            "ROTATION_INTERVAL": 1,  # 1 second for faster testing
            "MAX_FILE_SIZE": 1024,   # 1KB for faster testing
        }
        self.file_manager = FileManager(self.config)
        self.file_lock = threading.Lock()
        
    def tearDown(self):
        self.file_manager.stop()
        teardown_test_environment(self.temp_dir)
        
    def test_file_rotation_time_based(self):
        """Test that files are rotated based on time."""
        # Write test data to current file
        with open(self.current_file, "w") as f:
            f.write("<EVENT><plasectrxEventname>Test Event</plasectrxEventname></EVENT>")
        
        # Start file manager
        self.file_manager.start(self.file_lock, self.mock_s3_client)
        
        # Wait for rotation
        time.sleep(2)
        
        # Verify S3 upload was called
        self.mock_s3_client.upload_file.assert_called()
        
        # Verify current file was reset
        with open(self.current_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "")
        
    def test_file_rotation_size_based(self):
        """Test that files are rotated based on size."""
        # Write large test data to current file
        with open(self.current_file, "w") as f:
            f.write("<EVENT>" + "X" * 2000 + "</EVENT>")  # Exceeds MAX_FILE_SIZE
        
        # Start file manager
        self.file_manager.start(self.file_lock, self.mock_s3_client)
        
        # Wait for rotation
        time.sleep(0.5)
        
        # Verify S3 upload was called
        self.mock_s3_client.upload_file.assert_called()
        
    def test_xml_wrapping(self):
        """Test that XML content is properly wrapped in EVENTS tags."""
        # Write test data to current file
        with open(self.current_file, "w") as f:
            f.write("<EVENT><plasectrxEventname>Test Event</plasectrxEventname></EVENT>")
        
        # Manually trigger rotation
        self.file_manager.start(self.file_lock, self.mock_s3_client)
        self.file_manager.rotate_file()
        
        # Verify temp file contains wrapped XML
        with open(self.temp_file, "r") as f:
            content = f.read()
        
        self.assertTrue(content.startswith("<EVENTS>"))
        self.assertTrue(content.endswith("</EVENTS>"))
        self.assertIn("<EVENT><plasectrxEventname>Test Event</plasectrxEventname></EVENT>", content)
```

### S3 Client Tests

```python
# test_s3_client.py
import unittest
import os
import boto3
from moto import mock_s3
from server import S3Client

class TestS3Client(unittest.TestCase):
    @mock_s3
    def setUp(self):
        self.temp_dir = setup_test_environment()
        
        # Create test file
        self.test_file = os.path.join(self.temp_dir, "test.xml")
        with open(self.test_file, "w") as f:
            f.write("<EVENTS><EVENT>Test</EVENT></EVENTS>")
        
        # Create S3 bucket
        self.s3 = boto3.client(
            's3',
            region_name='us-east-1',
            aws_access_key_id='test-key',
            aws_secret_access_key='test-secret'
        )
        self.s3.create_bucket(Bucket='test-bucket')
        
        # Create S3 client
        self.config = {
            "BUCKET_NAME": "test-bucket",
            "PREFIX": "test-prefix/",
            "AWS_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": "test-key",
            "AWS_SECRET_ACCESS_KEY": "test-secret"
        }
        self.s3_client = S3Client(self.config)
        
    def tearDown(self):
        teardown_test_environment(self.temp_dir)
        
    @mock_s3
    def test_upload_file(self):
        """Test that files are uploaded to S3."""
        # Create bucket in moto
        self.s3.create_bucket(Bucket='test-bucket')
        
        # Upload file
        result = self.s3_client.upload_file(self.test_file)
        
        # Verify upload was successful
        self.assertTrue(result)
        
        # Verify file exists in S3
        response = self.s3.list_objects(Bucket='test-bucket', Prefix='test-prefix/')
        self.assertEqual(len(response['Contents']), 1)
        
    @mock_s3
    def test_get_s3_key(self):
        """Test that S3 keys are generated correctly."""
        # Test with date folders disabled
        key = self.s3_client.get_s3_key("20250729_123456.xml")
        self.assertEqual(key, "test-prefix/20250729_123456.xml")
        
        # Test with date folders enabled
        self.s3_client.use_date_folders = True
        key = self.s3_client.get_s3_key("20250729_123456.xml")
        self.assertEqual(key, "test-prefix/2025/07/29/20250729_123456.xml")
```

### Format Converter Tests

```python
# test_format_converter.py
import unittest
import os
import json
import xml.etree.ElementTree as ET
from server import FormatConverter

class TestFormatConverter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = setup_test_environment()
        
        # Create test XML file
        self.xml_file = os.path.join(self.temp_dir, "test.xml")
        with open(self.xml_file, "w") as f:
            f.write('<EVENTS><EVENT><plasectrxEventname>Test Event</plasectrxEventname><plasectrxIsAlarm>1</plasectrxIsAlarm></EVENT></EVENTS>')
        
        # Create converter
        self.xml_config = {"OUTPUT_FORMAT": "xml"}
        self.json_config = {"OUTPUT_FORMAT": "json"}
        
    def tearDown(self):
        teardown_test_environment(self.temp_dir)
        
    def test_is_json_output(self):
        """Test that output format is correctly identified."""
        xml_converter = FormatConverter(self.xml_config)
        json_converter = FormatConverter(self.json_config)
        
        self.assertFalse(xml_converter.is_json_output())
        self.assertTrue(json_converter.is_json_output())
        
    def test_get_file_extension(self):
        """Test that file extensions are correct."""
        xml_converter = FormatConverter(self.xml_config)
        json_converter = FormatConverter(self.json_config)
        
        self.assertEqual(xml_converter.get_file_extension(), ".xml")
        self.assertEqual(json_converter.get_file_extension(), ".json")
        
    def test_convert_to_json(self):
        """Test XML to JSON conversion."""
        converter = FormatConverter(self.json_config)
        json_file = converter.convert_to_json(self.xml_file)
        
        # Verify JSON file was created
        self.assertTrue(os.path.exists(json_file))
        
        # Verify JSON content
        with open(json_file, "r") as f:
            data = json.load(f)
        
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["plasectrxEventname"], "Test Event")
        self.assertEqual(data[0]["plasectrxIsAlarm"], "1")
```

## Integration Tests

### End-to-End Test

```python
# test_integration.py
import unittest
import socket
import threading
import time
import os
import boto3
from moto import mock_s3
from server import start_server

class TestIntegration(unittest.TestCase):
    @mock_s3
    def setUp(self):
        self.temp_dir = setup_test_environment()
        
        # Create S3 bucket
        self.s3 = boto3.client(
            's3',
            region_name='us-east-1',
            aws_access_key_id='test-key',
            aws_secret_access_key='test-secret'
        )
        self.s3.create_bucket(Bucket='test-bucket')
        
        # Start server in a thread
        self.server_thread = threading.Thread(target=start_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        time.sleep(0.5)  # Allow server to start
        
    def tearDown(self):
        # Server will be terminated when the thread exits
        teardown_test_environment(self.temp_dir)
        
    @mock_s3
    def test_end_to_end_flow(self):
        """Test the complete flow from TCP input to S3 upload."""
        # Create bucket in moto
        self.s3.create_bucket(Bucket='test-bucket')
        
        # Connect to server and send data
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("localhost", 8080))
        
        # Send sample XML event
        sample_event = """
        <EVENT>
        <plasectrxGatewayDN>cn=544de4aa06914073,ou=gateways,dc=plasec</plasectrxGatewayDN>
        <plasectrxEventname>Input point in alarm</plasectrxEventname>
        <plasectrxIsAlarm>1</plasectrxIsAlarm>
        </EVENT>
        """
        client.sendall(sample_event.encode())
        client.close()
        
        # Force rotation by setting small rotation interval
        os.environ["ROTATION_INTERVAL"] = "1"
        
        # Wait for rotation and upload
        time.sleep(2)
        
        # Check S3 for uploaded file
        response = self.s3.list_objects(Bucket='test-bucket', Prefix='xml-events/')
        
        # Verify file was uploaded
        self.assertGreater(len(response.get('Contents', [])), 0)
        
        # Download and verify content
        key = response['Contents'][0]['Key']
        obj = self.s3.get_object(Bucket='test-bucket', Key=key)
        content = obj['Body'].read().decode()
        
        # Verify content has EVENTS wrapper and our event
        self.assertIn("<EVENTS>", content)
        self.assertIn("<plasectrxEventname>Input point in alarm</plasectrxEventname>", content)
        self.assertIn("</EVENTS>", content)
```

## Performance Tests

```python
# test_performance.py
import unittest
import socket
import threading
import time
import os
import statistics
from server import start_server

class TestPerformance(unittest.TestCase):
    def setUp(self):
        self.temp_dir = setup_test_environment()
        
        # Start server in a thread
        self.server_thread = threading.Thread(target=start_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        time.sleep(0.5)  # Allow server to start
        
    def tearDown(self):
        # Server will be terminated when the thread exits
        teardown_test_environment(self.temp_dir)
        
    def test_throughput(self):
        """Test the server's throughput capacity."""
        # Create sample event
        sample_event = """
        <EVENT>
        <plasectrxGatewayDN>cn=544de4aa06914073,ou=gateways,dc=plasec</plasectrxGatewayDN>
        <plasectrxEventname>Input point in alarm</plasectrxEventname>
        <plasectrxIsAlarm>1</plasectrxIsAlarm>
        </EVENT>
        """
        event_size = len(sample_event.encode())
        
        # Connect to server
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("localhost", 8080))
        
        # Send events in a loop and measure throughput
        num_events = 1000
        start_time = time.time()
        
        for _ in range(num_events):
            client.sendall(sample_event.encode())
            
        end_time = time.time()
        client.close()
        
        # Calculate throughput
        duration = end_time - start_time
        events_per_second = num_events / duration
        bytes_per_second = (num_events * event_size) / duration
        
        print(f"Throughput: {events_per_second:.2f} events/second")
        print(f"Throughput: {bytes_per_second/1024:.2f} KB/second")
        
        # Assert minimum performance requirements
        self.assertGreater(events_per_second, 100)  # At least 100 events per second
        
    def test_concurrent_connections(self):
        """Test the server's ability to handle concurrent connections."""
        # Create sample event
        sample_event = "<EVENT><plasectrxEventname>Test</plasectrxEventname></EVENT>"
        
        # Function to send events from a client
        def client_task(client_id, num_events):
            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.connect(("localhost", 8080))
                
                for i in range(num_events):
                    event = f"<EVENT><plasectrxEventname>Test from client {client_id}, event {i}</plasectrxEventname></EVENT>"
                    client.sendall(event.encode())
                    time.sleep(0.01)  # Small delay between events
                    
                client.close()
                return True
            except Exception as e:
                print(f"Client {client_id} error: {e}")
                return False
        
        # Start multiple clients
        num_clients = 10
        events_per_client = 50
        client_threads = []
        
        start_time = time.time()
        
        for i in range(num_clients):
            thread = threading.Thread(target=client_task, args=(i, events_per_client))
            thread.start()
            client_threads.append(thread)
            
        # Wait for all clients to finish
        results = []
        for thread in client_threads:
            thread.join()
            
        end_time = time.time()
        
        # Calculate statistics
        duration = end_time - start_time
        total_events = num_clients * events_per_client
        events_per_second = total_events / duration
        
        print(f"Concurrent connections: {num_clients}")
        print(f"Total events: {total_events}")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Throughput: {events_per_second:.2f} events/second")
        
        # Verify all events were processed
        with open(os.environ["CURRENT_FILE"], "r") as f:
            content = f.read()
            
        for i in range(num_clients):
            for j in range(events_per_client):
                expected = f"Test from client {i}, event {j}"
                self.assertIn(expected, content)
```

## Validation Procedures

### Manual Validation Checklist

1. **Installation Validation**
   - [ ] Docker image builds successfully
   - [ ] Container starts without errors
   - [ ] Container exposes the correct port
   - [ ] Container logs show successful initialization

2. **Configuration Validation**
   - [ ] Environment variables are correctly applied
   - [ ] AWS credentials are properly handled
   - [ ] S3 bucket access is verified on startup

3. **Functionality Validation**
   - [ ] TCP server accepts connections
   - [ ] XML events are received and stored
   - [ ] Files are rotated on schedule
   - [ ] Files are uploaded to S3
   - [ ] XML is properly wrapped in EVENTS tags
   - [ ] JSON conversion works when enabled

4. **Error Handling Validation**
   - [ ] Server recovers from connection drops
   - [ ] Malformed XML is handled gracefully
   - [ ] S3 upload failures are properly retried
   - [ ] Resource exhaustion is handled appropriately

### Automated Validation Script

```bash
#!/bin/bash
# validate.sh

echo "Starting validation..."

# Check if container is running
if [ $(docker ps -q -f name=xml-listener) ]; then
    echo "✓ Container is running"
else
    echo "✗ Container is not running"
    exit 1
fi

# Check if port is exposed
if nc -z localhost 8080; then
    echo "✓ Port 8080 is open"
else
    echo "✗ Port 8080 is not open"
    exit 1
fi

# Send test event
echo "Sending test event..."
echo "<EVENT><plasectrxEventname>Validation Test</plasectrxEventname></EVENT>" | nc localhost 8080

# Wait for processing
echo "Waiting for processing..."
sleep 5

# Check S3 for uploaded file (requires AWS CLI)
echo "Checking S3 bucket..."
if aws s3 ls s3://$BUCKET_NAME/xml-events/ --region $AWS_REGION | grep -q xml; then
    echo "✓ File uploaded to S3"
else
    echo "✗ No file found in S3"
    exit 1
fi

# Download the latest file
LATEST_FILE=$(aws s3 ls s3://$BUCKET_NAME/xml-events/ --region $AWS_REGION | sort | tail -n 1 | awk '{print $4}')
aws s3 cp s3://$BUCKET_NAME/xml-events/$LATEST_FILE ./validation_download.xml --region $AWS_REGION

# Verify content
if grep -q "Validation Test" ./validation_download.xml; then
    echo "✓ Test event found in uploaded file"
else
    echo "✗ Test event not found in uploaded file"
    exit 1
fi

echo "Validation completed successfully!"
```

## Test Data

### Sample XML Events

```xml
<!-- sample_events.xml -->
<EVENT>
<plasectrxGatewayDN>cn=544de4aa06914073,ou=gateways,dc=plasec</plasectrxGatewayDN>
<plasectrxRecdate>20140610055028-0700</plasectrxRecdate>
<plasectrxRecdateUTC>20140610125028Z</plasectrxRecdateUTC>
<plasectrxEvtypename>Intrusion</plasectrxEvtypename>
<plasectrxEventname>Input point in alarm</plasectrxEventname>
<plasectrxSourcename>Input on subpanel 0 Address 1</plasectrxSourcename>
<plasectrxIsAlarm>1</plasectrxIsAlarm>
</EVENT>

<EVENT>
<plasectrxGatewayDN>cn=544de4aa06914073,ou=gateways,dc=plasec</plasectrxGatewayDN>
<plasectrxRecdate>20140610055129-0700</plasectrxRecdate>
<plasectrxRecdateUTC>20140610125129Z</plasectrxRecdateUTC>
<plasectrxEvtypename>Access</plasectrxEvtypename>
<plasectrxEventname>Access granted</plasectrxEventname>
<plasectrxSourcename>Main Entrance</plasectrxSourcename>
<plasectrxLname>Smith</plasectrxLname>
<plasectrxFname>John</plasectrxFname>
<plasectrxCardno>12345</plasectrxCardno>
<plasectrxIsAlarm>0</plasectrxIsAlarm>
</EVENT>

<EVENT>
<plasectrxGatewayDN>cn=544de4aa06914073,ou=gateways,dc=plasec</plasectrxGatewayDN>
<plasectrxRecdate>20140610055230-0700</plasectrxRecdate>
<plasectrxRecdateUTC>20140610125230Z</plasectrxRecdateUTC>
<plasectrxEvtypename>Access</plasectrxEvtypename>
<plasectrxEventname>Access denied</plasectrxEventname>
<plasectrxSourcename>Secure Area</plasectrxSourcename>
<plasectrxLname>Jones</plasectrxLname>
<plasectrxFname>Alice</plasectrxFname>
<plasectrxCardno>67890</plasectrxCardno>
<plasectrxIsAlarm>0</plasectrxIsAlarm>
</EVENT>
```

### Test Event Generator

```python
# generate_test_events.py
import socket
import time
import random
import argparse
from datetime import datetime

def generate_event(event_type="random"):
    """Generate a sample XML event."""
    now = datetime.utcnow()
    timestamp = now.strftime("%Y%m%d%H%M%S")
    timestamp_utc = f"{timestamp}Z"
    
    event_types = {
        "alarm": {
            "evtypename": "Intrusion",
            "eventname": "Input point in alarm",
            "sourcename": f"Sensor {random.randint(1, 100)}",
            "is_alarm": "1"
        },
        "access_granted": {
            "evtypename": "Access",
            "eventname": "Access granted",
            "sourcename": f"Door {random.randint(1, 20)}",
            "is_alarm": "0"
        },
        "access_denied": {
            "evtypename": "Access",
            "eventname": "Access denied",
            "sourcename": f"Door {random.randint(1, 20)}",
            "is_alarm": "0"
        }
    }
    
    if event_type == "random":
        event_type = random.choice(list(event_types.keys()))
        
    event_data = event_types.get(event_type, event_types["alarm"])
    
    # Generate random person data for access events
    person_data = ""
    if "access" in event_type:
        first_names = ["John", "Jane", "Alice", "Bob", "Charlie", "Diana", "Edward", "Fiona"]
        last_names = ["Smith", "Jones", "Brown", "Wilson", "Taylor", "Davis", "White", "Clark"]
        
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        card_no = random.randint(10000, 99999)
        
        person_data = f"""
        <plasectrxLname>{last_name}</plasectrxLname>
        <plasectrxFname>{first_name}</plasectrxFname>
        <plasectrxCardno>{card_no}</plasectrxCardno>
        """
    
    # Build the event XML
    event = f"""
    <EVENT>
    <plasectrxGatewayDN>cn=544de4aa06914073,ou=gateways,dc=plasec</plasectrxGatewayDN>
    <plasectrxRecdate>{timestamp}-0000</plasectrxRecdate>
    <plasectrxRecdateUTC>{timestamp_utc}</plasectrxRecdateUTC>
    <plasectrxEvtypename>{event_data["evtypename"]}</plasectrxEvtypename>
    <plasectrxEventname>{event_data["eventname"]}</plasectrxEventname>
    <plasectrxSourcename>{event_data["sourcename"]}</plasectrxSourcename>{person_data}
    <plasectrxIsAlarm>{event_data["is_alarm"]}</plasectrxIsAlarm>
    </EVENT>
    """
    
    return event.strip()

def send_events(host, port, count, interval, event_type):
    """Send events to the TCP server."""
    try:
        # Connect to server
        client = socket.socket(socket.AF_INET, socket.SOCK
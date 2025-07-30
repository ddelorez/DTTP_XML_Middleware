#!/usr/bin/env python3
"""
Unit tests for the Daikin XML Listener middleware.
"""

import unittest
import os
import tempfile
import socket
import threading
import time
import json
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

# Import the server components
from server import TCPServer, S3Client, FormatConverter, FileManager, load_config


class TestTCPServer(unittest.TestCase):
    """Test cases for the TCP server component."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.current_file = os.path.join(self.temp_dir, "current.xml")
        self.config = {
            "PORT": 8081,
            "CURRENT_FILE": self.current_file
        }
        self.server = TCPServer(self.config)
        
    def tearDown(self):
        """Clean up test environment."""
        self.server.stop()
        # Clean up temp files
        if os.path.exists(self.current_file):
            os.remove(self.current_file)
        os.rmdir(self.temp_dir)
        
    def test_server_initialization(self):
        """Test that the server initializes with correct configuration."""
        self.assertEqual(self.server.port, 8081)
        self.assertEqual(self.server.current_file, self.current_file)
        self.assertEqual(self.server.host, "0.0.0.0")
        
    def test_server_socket_creation(self):
        """Test that the server can create a socket."""
        # Start server in a thread
        server_thread = threading.Thread(target=self.server.start, args=(threading.Lock(),))
        server_thread.daemon = True
        server_thread.start()
        
        # Give the server time to start
        time.sleep(0.1)
        
        # Try to connect
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            client.connect(("localhost", 8081))
            self.assertTrue(True)  # Connection successful
        except ConnectionRefusedError:
            self.fail("Could not connect to server")
        finally:
            client.close()
            self.server.stop()


class TestFormatConverter(unittest.TestCase):
    """Test cases for the format converter component."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test environment."""
        # Clean up temp files
        for filename in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, filename))
        os.rmdir(self.temp_dir)
        
    def test_xml_output_format(self):
        """Test XML output format detection."""
        converter = FormatConverter({"OUTPUT_FORMAT": "xml"})
        self.assertFalse(converter.is_json_output())
        self.assertEqual(converter.get_file_extension(), ".xml")
        
    def test_json_output_format(self):
        """Test JSON output format detection."""
        converter = FormatConverter({"OUTPUT_FORMAT": "json"})
        self.assertTrue(converter.is_json_output())
        self.assertEqual(converter.get_file_extension(), ".json")
        
    def test_xml_to_json_conversion(self):
        """Test XML to JSON conversion."""
        # Create test XML file
        xml_file = os.path.join(self.temp_dir, "test.xml")
        xml_content = """<EVENTS>
<EVENT>
<plasectrxEventname>Test Event</plasectrxEventname>
<plasectrxIsAlarm>1</plasectrxIsAlarm>
</EVENT>
</EVENTS>"""
        
        with open(xml_file, "w") as f:
            f.write(xml_content)
        
        # Convert to JSON
        converter = FormatConverter({"OUTPUT_FORMAT": "json"})
        json_file = converter.convert_to_json(xml_file)
        
        # Verify conversion was successful
        self.assertIsNotNone(json_file)
        
        if json_file:  # Type guard for type checker
            # Verify JSON file was created
            self.assertTrue(os.path.exists(json_file))
            
            # Verify JSON content
            with open(json_file, "r") as f:
                data = json.load(f)
            
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["plasectrxEventname"], "Test Event")
            self.assertEqual(data[0]["plasectrxIsAlarm"], "1")


class TestS3Client(unittest.TestCase):
    """Test cases for the S3 client component."""
    
    @patch('boto3.client')
    def test_s3_client_initialization(self, mock_boto3_client):
        """Test S3 client initialization."""
        # Mock the S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        
        config = {
            "BUCKET_NAME": "test-bucket",
            "AWS_REGION": "us-east-1"
        }
        
        s3_client = S3Client(config)
        
        # Verify boto3 client was created
        mock_boto3_client.assert_called_once_with(
            's3',
            region_name='us-east-1',
            endpoint_url=None
        )
        
        # Verify bucket access was checked
        mock_s3.head_bucket.assert_called_once_with(Bucket='test-bucket')
        
    def test_s3_key_generation(self):
        """Test S3 key generation."""
        config = {
            "BUCKET_NAME": "test-bucket",
            "PREFIX": "xml-events/",
            "USE_DATE_FOLDERS": "false"
        }
        
        with patch('boto3.client'):
            s3_client = S3Client(config)
            
            # Test without date folders
            key = s3_client.get_s3_key("20250729_123456.xml")
            self.assertEqual(key, "xml-events/20250729_123456.xml")
            
            # Test with date folders
            s3_client.use_date_folders = True
            key = s3_client.get_s3_key("20250729_123456.xml")
            self.assertEqual(key, "xml-events/2025/07/29/20250729_123456.xml")


class TestConfigLoading(unittest.TestCase):
    """Test cases for configuration loading."""
    
    def test_load_config(self):
        """Test loading configuration from environment variables."""
        # Set test environment variables
        os.environ["PORT"] = "9090"
        os.environ["BUCKET_NAME"] = "my-test-bucket"
        os.environ["OUTPUT_FORMAT"] = "json"
        
        config = load_config()
        
        # Verify config values
        self.assertEqual(config["PORT"], "9090")
        self.assertEqual(config["BUCKET_NAME"], "my-test-bucket")
        self.assertEqual(config["OUTPUT_FORMAT"], "json")
        
        # Clean up
        del os.environ["PORT"]
        del os.environ["BUCKET_NAME"]
        del os.environ["OUTPUT_FORMAT"]


class TestFileManager(unittest.TestCase):
    """Test cases for the file manager component."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.current_file = os.path.join(self.temp_dir, "current.xml")
        self.temp_file = os.path.join(self.temp_dir, "temp.xml")
        
        self.config = {
            "CURRENT_FILE": self.current_file,
            "TEMP_FILE": self.temp_file,
            "ROTATION_INTERVAL": 1,  # 1 second for testing
            "MAX_FILE_SIZE": 100     # 100 bytes for testing
        }
        
    def tearDown(self):
        """Clean up test environment."""
        # Clean up temp files
        for filename in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, filename))
        os.rmdir(self.temp_dir)
        
    def test_file_manager_initialization(self):
        """Test file manager initialization."""
        file_manager = FileManager(self.config)
        
        self.assertEqual(file_manager.current_file, self.current_file)
        self.assertEqual(file_manager.temp_file, self.temp_file)
        self.assertEqual(file_manager.rotation_interval, 1)
        self.assertEqual(file_manager.max_file_size, 100)
        
    def test_size_based_rotation_trigger(self):
        """Test that size-based rotation is triggered correctly."""
        # Create a file larger than MAX_FILE_SIZE
        with open(self.current_file, "w") as f:
            f.write("X" * 150)  # 150 bytes > 100 byte limit
        
        file_manager = FileManager(self.config)
        
        # Mock the S3 client and format converter
        mock_s3_client = MagicMock()
        mock_s3_client.upload_file.return_value = True
        mock_format_converter = MagicMock()
        mock_format_converter.is_json_output.return_value = False
        
        # Start file manager
        file_manager.start(threading.Lock(), mock_s3_client, mock_format_converter)
        
        # Wait a bit for rotation to trigger
        time.sleep(2)
        
        # Stop file manager
        file_manager.stop()
        
        # Verify upload was attempted
        mock_s3_client.upload_file.assert_called()


if __name__ == "__main__":
    unittest.main()
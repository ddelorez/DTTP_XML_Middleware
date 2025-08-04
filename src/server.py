#!/usr/bin/env python3
"""
Daikin XML Listener Middleware

A lightweight middleware for aggregating XML event streams from Avigilon ACM systems
into an S3 bucket, ensuring compatibility with Snowflake for data ingestion.
"""

import os
import socket
import threading
import time
import logging
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import signal
import sys
from collections import defaultdict
from threading import Semaphore

import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TCPServer:
    """TCP server component for receiving XML event streams."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize TCP server with configuration."""
        self.host = config.get("BIND_HOST", "0.0.0.0")
        self.port = int(config.get("PORT", 8080))
        self.current_file = config.get("CURRENT_FILE", "./current.xml")
        self.file_lock = threading.Lock()
        self.running = False
        self.server_socket = None
        self.worker_threads = []
        
        # Security settings
        self.max_connections = int(config.get("MAX_CONNECTIONS", 50))
        self.max_message_size = int(config.get("MAX_MESSAGE_SIZE", 1024 * 1024))  # 1MB default
        self.rate_limit_enabled = config.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
        self.rate_limit_window = int(config.get("RATE_LIMIT_WINDOW", 60))  # seconds
        self.rate_limit_max_events = int(config.get("RATE_LIMIT_MAX_EVENTS", 1000))
        
        # Connection tracking
        self.connection_semaphore = Semaphore(self.max_connections)
        self.connection_count = 0
        self.connection_lock = threading.Lock()
        
        # Rate limiting
        self.rate_limiter = defaultdict(list)  # IP -> list of timestamps
        self.rate_limit_lock = threading.Lock()
        
        # Event tracking
        self.event_count = 0
        self.event_count_lock = threading.Lock()
        
    def start(self, file_lock: threading.Lock):
        """Start the TCP server."""
        self.file_lock = file_lock  # Use shared lock
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            logger.info(f"TCP server started on {self.host}:{self.port}")
            
            while self.running:
                try:
                    # Set timeout to allow periodic checking of self.running
                    self.server_socket.settimeout(1.0)
                    try:
                        client_socket, address = self.server_socket.accept()
                        
                        # Check rate limit (skip for localhost/trusted sources)
                        if self.rate_limit_enabled and address[0] not in ['127.0.0.1', 'localhost']:
                            if not self.check_rate_limit(address[0]):
                                logger.warning(f"Rate limit exceeded for {address[0]} - closing connection")
                                client_socket.close()
                                continue
                        
                        # Try to acquire connection semaphore
                        if not self.connection_semaphore.acquire(blocking=False):
                            logger.warning(f"Max connections reached, rejecting {address}")
                            client_socket.close()
                            continue
                        
                        with self.connection_lock:
                            self.connection_count += 1
                            logger.info(f"Connection from {address} (active: {self.connection_count})")
                        
                        client_thread = threading.Thread(
                            target=self.handle_client,
                            args=(client_socket, address)
                        )
                        client_thread.daemon = True
                        client_thread.start()
                        self.worker_threads.append(client_thread)
                    except socket.timeout:
                        continue
                except socket.error as e:
                    if self.running:
                        logger.error(f"Socket error: {e}")
                    continue
        finally:
            self.stop()
    
    def handle_client(self, client_socket: socket.socket, address: tuple):
        """Handle client connection in a worker thread."""
        try:
            # Set socket timeout for reads
            client_socket.settimeout(30.0)
            
            message_buffer = b""
            total_received = 0
            
            while self.running:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break  # Client disconnected
                    
                    # Check message size limit
                    total_received += len(data)
                    if total_received > self.max_message_size:
                        logger.warning(f"Message size limit exceeded from {address}")
                        break
                    
                    message_buffer += data
                    
                    # Process complete events
                    while b"</EVENT>" in message_buffer:
                        event_end = message_buffer.find(b"</EVENT>") + 8
                        event_data = message_buffer[:event_end]
                        message_buffer = message_buffer[event_end:]
                        
                        # Remove XML declaration if present (ACM sends one per event)
                        if event_data.startswith(b"<?xml"):
                            xml_decl_end = event_data.find(b"?>")
                            if xml_decl_end != -1:
                                event_data = event_data[xml_decl_end + 2:].lstrip()
                        
                        # Append complete event to current file
                        with self.file_lock:
                            with open(self.current_file, "ab") as f:
                                f.write(event_data)
                                f.write(b"\n")  # Add newline for readability
                        
                        # Increment event counter
                        with self.event_count_lock:
                            self.event_count += 1
                            current_count = self.event_count
                        
                        logger.info(f"Received XML event from ACM ({address[0]}) - Total event count: {current_count}")
                        
                        # Update rate limiter
                        if self.rate_limit_enabled:
                            self.update_rate_limit(address[0])
                    
                except socket.timeout:
                    logger.warning(f"Socket timeout for {address}")
                    break
                except Exception as e:
                    logger.error(f"Error processing data from {address}: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}")
        finally:
            client_socket.close()
            self.connection_semaphore.release()
            with self.connection_lock:
                self.connection_count -= 1
                logger.info(f"Connection closed: {address} (active: {self.connection_count})")
    
    def check_rate_limit(self, ip_address: str) -> bool:
        """Check if IP address is within rate limits."""
        with self.rate_limit_lock:
            current_time = time.time()
            # Clean old entries
            self.rate_limiter[ip_address] = [
                ts for ts in self.rate_limiter[ip_address]
                if current_time - ts < self.rate_limit_window
            ]
            
            # Check limit
            event_count = len(self.rate_limiter[ip_address])
            if event_count >= self.rate_limit_max_events:
                logger.debug(f"Rate limit check: {ip_address} has {event_count} events in {self.rate_limit_window}s window (limit: {self.rate_limit_max_events})")
                return False
            
            return True
    
    def update_rate_limit(self, ip_address: str):
        """Update rate limit tracker for IP address."""
        with self.rate_limit_lock:
            self.rate_limiter[ip_address].append(time.time())
    
    def get_and_reset_event_count(self) -> int:
        """Get current event count and reset it to zero."""
        with self.event_count_lock:
            count = self.event_count
            self.event_count = 0
            return count
    
    def get_event_count(self) -> int:
        """Get current event count without resetting."""
        with self.event_count_lock:
            return self.event_count
    
    def stop(self):
        """Stop the TCP server."""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        logger.info(f"TCP server stopped - Total events processed in session: {self.get_event_count()}")


class S3Client:
    """S3 client component for uploading files to S3."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize S3 client with configuration."""
        self.bucket_name = config.get("BUCKET_NAME")
        if not self.bucket_name:
            raise ValueError("BUCKET_NAME environment variable is required")
        
        self.prefix = config.get("PREFIX", "xml-events/")
        self.use_date_folders = config.get("USE_DATE_FOLDERS", "false").lower() == "true"
        self.max_retries = int(config.get("MAX_RETRIES", 5))
        self.retry_base_delay = float(config.get("RETRY_BASE_DELAY", 1.0))
        
        # Initialize boto3 client with credentials fallback
        try:
            # Check for custom endpoint URL (useful for testing with minio)
            endpoint_url = config.get("AWS_ENDPOINT_URL")
            
            # Load credentials with fallback: secrets files first, then env vars
            access_key = self._load_credential("AWS_ACCESS_KEY_ID", "/run/secrets/aws_access_key_id")
            secret_key = self._load_credential("AWS_SECRET_ACCESS_KEY", "/run/secrets/aws_secret_access_key")
            
            self.s3 = boto3.client(
                's3',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=config.get("AWS_REGION"),
                endpoint_url=endpoint_url
            )
            
            # Test bucket access - fail fast if misconfigured
            if not self.check_bucket_access():
                logger.error("=" * 60)
                logger.error("S3 CONFIGURATION FAILURE - SERVICE CANNOT START")
                logger.error("Please fix the S3 configuration issues above")
                logger.error("=" * 60)
                raise ValueError("S3 bucket access validation failed")
                
            logger.info(f"✓ S3 client initialized successfully")
            logger.info(f"  Bucket: {self.bucket_name}")
            logger.info(f"  Region: {self.s3.meta.region_name}")
            logger.info(f"  Prefix: {self.prefix}")
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize S3 client: {e}")
            logger.error("   Check your AWS credentials and network connectivity")
            raise
    
    def _load_credential(self, env_var: str, secret_path: str) -> str:
        """Load credential from secret file if exists, else from environment variable."""
        if os.path.exists(secret_path):
            with open(secret_path, 'r') as f:
                value = f.read().strip()
            logger.info(f"Loaded {env_var} from secret file: {secret_path}")
            return value
        else:
            value = os.environ.get(env_var)
            if value:
                logger.info(f"Loaded {env_var} from environment variable")
                return value
            else:
                raise ValueError(f"{env_var} not found in secrets or environment variables")
    
    def check_bucket_access(self) -> bool:
        """Test S3 bucket access to validate credentials and permissions."""
        try:
            self.s3.head_bucket(Bucket=self.bucket_name)
            logger.info(f"✓ Successfully verified access to S3 bucket: {self.bucket_name}")
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            # Provide specific guidance based on error code
            if error_code == '404' or error_code == 'NoSuchBucket':
                logger.error(f"❌ S3 CONFIGURATION ERROR: Bucket '{self.bucket_name}' does not exist!")
                logger.error("   Please check your BUCKET_NAME in .env file")
            elif error_code == 'AccessDenied':
                logger.error(f"❌ S3 PERMISSION ERROR: Access denied to bucket '{self.bucket_name}'")
                logger.error("   Please check your AWS credentials and bucket permissions")
                logger.error("   Required permissions: s3:ListBucket, s3:PutObject")
            elif error_code == 'InvalidBucketName':
                logger.error(f"❌ S3 CONFIGURATION ERROR: Invalid bucket name '{self.bucket_name}'")
                logger.error("   Bucket names must be 3-63 characters, lowercase letters, numbers, and hyphens only")
            elif error_code == 'RequestTimeout':
                logger.error(f"❌ S3 CONNECTION ERROR: Timeout connecting to S3")
                logger.error("   Please check your network connection and AWS_REGION setting")
            else:
                logger.error(f"❌ S3 ERROR {error_code}: {error_msg}")
                logger.error(f"   Bucket: {self.bucket_name}, Region: {self.s3.meta.region_name}")
            
            return False
        except Exception as e:
            logger.error(f"❌ UNEXPECTED ERROR checking S3 bucket: {str(e)}")
            logger.error("   This may indicate network issues or invalid AWS configuration")
            return False
    
    def get_s3_key(self, filename: str) -> str:
        """Generate S3 key with optional date-based folders."""
        base_filename = os.path.basename(filename)
        
        if self.use_date_folders and len(base_filename) >= 8:
            # Extract date components from filename (assumes format: YYYYMMDD_HHMMSS.xml)
            try:
                year = base_filename[0:4]
                month = base_filename[4:6]
                day = base_filename[6:8]
                return f"{self.prefix}{year}/{month}/{day}/{base_filename}"
            except (IndexError, ValueError):
                logger.warning(f"Could not parse date from filename: {base_filename}")
                return f"{self.prefix}{base_filename}"
        else:
            return f"{self.prefix}{base_filename}"
    
    def upload_file(self, file_path: str, s3_key: Optional[str] = None) -> bool:
        """Upload a file to S3 with retry logic."""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        
        if not s3_key:
            s3_key = self.get_s3_key(os.path.basename(file_path))
        
        # Determine content type based on file extension
        content_type = "application/xml"
        if file_path.endswith(".json"):
            content_type = "application/json"
        
        # Add metadata
        metadata = {
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "xml-stream-aggregator"
        }
        
        # Attempt upload with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Uploading {file_path} to s3://{self.bucket_name}/{s3_key} "
                           f"(Attempt {attempt}/{self.max_retries})")
                
                self.s3.upload_file(
                    file_path,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={
                        'ContentType': content_type,
                        'Metadata': metadata
                    }
                )
                
                logger.info(f"Successfully uploaded {file_path} to s3://{self.bucket_name}/{s3_key}")
                return True
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                
                # Handle different error types
                if error_code in ['AccessDenied', 'InvalidAccessKeyId', 'SignatureDoesNotMatch']:
                    # Authentication/permission errors - fail fast
                    logger.error(f"S3 authentication error: {error_code} - {str(e)}")
                    return False
                    
                elif error_code in ['SlowDown', 'RequestTimeTooSkewed', 'RequestTimeout']:
                    # Throttling/timing errors - retry with backoff
                    if attempt < self.max_retries:
                        delay = self.retry_base_delay * (2 ** (attempt - 1))  # Exponential backoff
                        logger.warning(f"S3 throttling error: {error_code}, retrying in {delay:.2f}s")
                        time.sleep(delay)
                    else:
                        logger.error(f"S3 throttling error: {error_code}, max retries exceeded")
                        return False
                        
                else:
                    # Other errors - retry with backoff for transient issues
                    if attempt < self.max_retries:
                        delay = self.retry_base_delay * (2 ** (attempt - 1))
                        logger.warning(f"S3 error: {error_code} - {str(e)}, retrying in {delay:.2f}s")
                        time.sleep(delay)
                    else:
                        logger.error(f"S3 error: {error_code} - {str(e)}, max retries exceeded")
                        return False
                        
            except Exception as e:
                # Unexpected errors
                if attempt < self.max_retries:
                    delay = self.retry_base_delay * (2 ** (attempt - 1))
                    logger.warning(f"Unexpected error during S3 upload: {str(e)}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                else:
                    logger.error(f"Unexpected error during S3 upload: {str(e)}, max retries exceeded")
                    return False
        
        return False


class FormatConverter:
    """Format converter component for optional JSON conversion."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize format converter with configuration."""
        self.output_format = config.get("OUTPUT_FORMAT", "xml").lower()
        self.pretty_print = config.get("PRETTY_PRINT_JSON", "true").lower() == "true"
        
    def is_json_output(self) -> bool:
        """Check if output format is JSON."""
        return self.output_format == "json"
    
    def get_file_extension(self) -> str:
        """Get the appropriate file extension based on output format."""
        return ".json" if self.is_json_output() else ".xml"
    
    def convert_to_json(self, xml_file_path: str, json_file_path: Optional[str] = None) -> Optional[str]:
        """Convert XML file to JSON format."""
        if not json_file_path:
            json_file_path = xml_file_path.rsplit(".", 1)[0] + ".json"
        
        try:
            # Parse XML file
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            # Check if root is EVENTS
            if root.tag != "EVENTS":
                logger.warning(f"Root element is not EVENTS: {root.tag}")
                # Wrap in EVENTS if needed
                events_root = ET.Element("EVENTS")
                if root.tag == "EVENT":
                    events_root.append(root)
                else:
                    for event in root.findall(".//EVENT"):
                        events_root.append(event)
                root = events_root
            
            # Convert to list of dictionaries
            events_list = []
            for event in root.findall(".//EVENT"):
                event_dict = {}
                for child in event:
                    # Handle text content
                    if child.text is not None:
                        event_dict[child.tag] = child.text.strip()
                    else:
                        event_dict[child.tag] = ""
                events_list.append(event_dict)
            
            # Write JSON file
            with open(json_file_path, "w") as f:
                if self.pretty_print:
                    json.dump(events_list, f, indent=2)
                else:
                    json.dump(events_list, f)
            
            logger.info(f"Successfully converted {xml_file_path} to JSON: {json_file_path}")
            return json_file_path
            
        except ET.ParseError as e:
            logger.error(f"XML parsing error during conversion: {e}")
            return None
        except Exception as e:
            logger.error(f"Error converting XML to JSON: {e}")
            return None


class FileManager:
    """File manager component for rotating and processing files."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize file manager with configuration."""
        self.current_file = config.get("CURRENT_FILE", "./current.xml")
        self.temp_file = config.get("TEMP_FILE", "./temp.xml")
        self.rotation_interval = int(config.get("ROTATION_INTERVAL", 3600))  # 1 hour
        self.max_file_size = int(config.get("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10MB
        self.check_interval = 60  # Check every 60 seconds
        self.file_lock = threading.Lock()
        self.running = False
        self.rotation_thread = None
        self.s3_client = None
        self.format_converter = None
        self.tcp_server = None
        
    def start(self, file_lock: threading.Lock, s3_client: S3Client, format_converter: FormatConverter, tcp_server: TCPServer):
        """Start the file rotation thread."""
        self.file_lock = file_lock  # Share lock with TCP server
        self.s3_client = s3_client
        self.format_converter = format_converter
        self.tcp_server = tcp_server
        self.running = True
        
        # Initialize empty current file if it doesn't exist
        if not os.path.exists(self.current_file):
            with open(self.current_file, "w") as f:
                pass
        
        self.rotation_thread = threading.Thread(target=self.rotation_loop)
        self.rotation_thread.daemon = True
        self.rotation_thread.start()
        logger.info("File rotation thread started")
        
    def rotation_loop(self):
        """Main loop checking for rotation conditions."""
        last_rotation_time = time.time()
        
        while self.running:
            try:
                current_time = time.time()
                
                # Check if rotation is needed
                rotation_needed = False
                
                # Time-based rotation
                if current_time - last_rotation_time >= self.rotation_interval:
                    logger.info("Time-based rotation triggered")
                    rotation_needed = True
                
                # Size-based rotation
                if os.path.exists(self.current_file):
                    file_size = os.path.getsize(self.current_file)
                    if file_size >= self.max_file_size:
                        logger.info(f"Size-based rotation triggered: {file_size} bytes")
                        rotation_needed = True
                
                if rotation_needed:
                    self.rotate_file()
                    last_rotation_time = current_time
                
                # Sleep until next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in rotation loop: {e}")
                time.sleep(self.check_interval)  # Continue despite errors
    
    def rotate_file(self):
        """Rotate the current file, wrap in EVENTS tags, and upload to S3."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        
        try:
            # Acquire lock to prevent TCP server from writing during rotation
            with self.file_lock:
                # Get event count before rotation
                event_count = self.tcp_server.get_event_count() if self.tcp_server else 0
                
                # Skip if file is empty
                if not os.path.exists(self.current_file) or os.path.getsize(self.current_file) == 0:
                    logger.info("Skipping rotation for empty file")
                    return
                
                logger.info(f"Starting file rotation - Total events to upload: {event_count}")
                
                # Read current file content
                with open(self.current_file, "rb") as f:
                    content = f.read()
                
                # Wrap content in EVENTS tags with XML declaration for valid document
                wrapped_content = b'<?xml version="1.0" encoding="UTF-8"?>\n<EVENTS>\n' + content + b'\n</EVENTS>'
                
                # Write to temp file
                with open(self.temp_file, "wb") as f:
                    f.write(wrapped_content)
                
                # Validate XML
                try:
                    tree = ET.parse(self.temp_file)
                    root = tree.getroot()
                    event_count_in_file = len(root.findall('.//EVENT'))
                    logger.info(f"XML validation successful - found {event_count_in_file} events in file")
                    is_valid_xml = True
                except ET.ParseError as e:
                    logger.error(f"XML validation failed: {e}")
                    # Log first 500 chars of wrapped content for debugging
                    logger.debug(f"First 500 chars of wrapped content: {wrapped_content[:500]}")
                    is_valid_xml = False
                
                # Process according to output format
                if self.format_converter.is_json_output() and is_valid_xml:
                    # Convert to JSON
                    processed_file = self.format_converter.convert_to_json(self.temp_file)
                    if not processed_file:
                        logger.error("JSON conversion failed, falling back to XML")
                        processed_file = self.temp_file
                        file_extension = ".xml"
                    else:
                        file_extension = ".json"
                else:
                    # Use XML
                    processed_file = self.temp_file
                    file_extension = ".xml"
                
                # Generate S3 key with appropriate extension
                s3_key = f"{timestamp}{file_extension}"
                
                # Upload to S3
                if is_valid_xml:
                    success = self.s3_client.upload_file(processed_file, s3_key)
                else:
                    # Fallback: upload raw content
                    logger.warning("Uploading raw content due to XML validation failure")
                    fallback_key = f"{timestamp}_raw.xml"
                    success = self.s3_client.upload_file(self.current_file, fallback_key)
                
                if success:
                    # Reset current file
                    with open(self.current_file, "w") as f:
                        pass
                    
                    # Delete temp files
                    if os.path.exists(self.temp_file):
                        os.remove(self.temp_file)
                    if processed_file != self.temp_file and os.path.exists(processed_file):
                        os.remove(processed_file)
                    
                    # Reset event counter after successful upload
                    events_uploaded = self.tcp_server.get_and_reset_event_count() if self.tcp_server else event_count
                    
                    logger.info(f"File rotated and uploaded successfully: {s3_key} - Events uploaded: {events_uploaded}")
                else:
                    logger.error("Failed to upload rotated file to S3")
                
        except Exception as e:
            logger.error(f"Error during file rotation: {e}")
    
    def stop(self):
        """Stop the file rotation thread."""
        self.running = False
        if self.rotation_thread:
            self.rotation_thread.join(timeout=5)
        logger.info("File rotation thread stopped")


def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables."""
    config = {}
    
    # List of all supported environment variables
    env_vars = [
        "PORT", "BUCKET_NAME", "PREFIX", "ROTATION_INTERVAL", "MAX_FILE_SIZE",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "AWS_ENDPOINT_URL",
        "OUTPUT_FORMAT", "USE_DATE_FOLDERS", "PRETTY_PRINT_JSON",
        "CURRENT_FILE", "TEMP_FILE", "MAX_RETRIES", "RETRY_BASE_DELAY",
        # Security settings
        "BIND_HOST", "MAX_CONNECTIONS", "MAX_MESSAGE_SIZE",
        "RATE_LIMIT_ENABLED", "RATE_LIMIT_WINDOW", "RATE_LIMIT_MAX_EVENTS"
    ]
    
    # Load each variable if it exists
    for var in env_vars:
        value = os.environ.get(var)
        if value is not None:
            config[var] = value
    
    return config


def start_server():
    """Start the middleware server with all components."""
    # Load configuration
    config = load_config()
    
    # Validate required configuration
    if not config.get("BUCKET_NAME"):
        logger.error("BUCKET_NAME environment variable is required")
        sys.exit(1)
    
    # Create shared file lock
    file_lock = threading.Lock()
    
    # Initialize components
    try:
        tcp_server = TCPServer(config)
        s3_client = S3Client(config)
        format_converter = FormatConverter(config)
        file_manager = FileManager(config)
        
        # Start file manager
        file_manager.start(file_lock, s3_client, format_converter, tcp_server)
        
        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            tcp_server.stop()
            file_manager.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start TCP server (blocking call)
        tcp_server.start(file_lock)
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    start_server()
#!/usr/bin/env python3
"""
Test script to verify event logging functionality.
Sends test XML events to the server and monitors the logs.
"""

import socket
import time
import threading

def send_test_event(host='localhost', port=8080, event_id=1):
    """Send a single test XML event to the server."""
    event_xml = f"""<EVENT>
<plasectrxEventname>Test Event {event_id}</plasectrxEventname>
<plasectrxRecdate>2025-08-01T12:00:{event_id:02d}</plasectrxRecdate>
<plasectrxAuxin1>Test Input {event_id}</plasectrxAuxin1>
<plasectrxAuxin2>Test Description {event_id}</plasectrxAuxin2>
</EVENT>"""
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(event_xml.encode('utf-8'))
            print(f"Sent test event {event_id}")
    except Exception as e:
        print(f"Error sending event {event_id}: {e}")

def send_batch_events(host='localhost', port=8080, count=10, delay=0.1):
    """Send a batch of test events with a delay between each."""
    print(f"Sending {count} test events to {host}:{port}")
    for i in range(1, count + 1):
        send_test_event(host, port, i)
        if i < count:
            time.sleep(delay)
    print("Batch complete")

def main():
    """Main test function."""
    print("XML Event Logging Test")
    print("=====================")
    print()
    print("This script will send test events to verify logging functionality.")
    print("Make sure the server is running and monitor its logs.")
    print()
    
    # Send a small batch to test basic functionality
    print("Test 1: Sending 5 events with 0.5s delay")
    send_batch_events(count=5, delay=0.5)
    
    print("\nWaiting 2 seconds...")
    time.sleep(2)
    
    # Send a larger batch to test accumulation
    print("\nTest 2: Sending 20 events rapidly")
    send_batch_events(count=20, delay=0.05)
    
    print("\nTest complete. Check the server logs for:")
    print("- 'Received XML event from ACM' messages with incrementing counts")
    print("- 'Starting file rotation' message showing total events")
    print("- 'File rotated and uploaded successfully' message with event count")

if __name__ == "__main__":
    main()
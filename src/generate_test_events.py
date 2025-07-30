#!/usr/bin/env python3
"""
Test Event Generator for Daikin XML Listener

Generate and send test XML events to the middleware for testing purposes.
"""

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
<plasectrxCardno>{card_no}</plasectrxCardno>"""
    
    # Build the event XML
    event = f"""<EVENT>
<plasectrxGatewayDN>cn=544de4aa06914073,ou=gateways,dc=plasec</plasectrxGatewayDN>
<cn>38901f4a95d14013</cn>
<plasectrxRecdate>{timestamp}-0000</plasectrxRecdate>
<plasectrxPaneldate>{timestamp}-0400</plasectrxPaneldate>
<plasectrxRecdateUTC>{timestamp_utc}</plasectrxRecdateUTC>
<plasectrxPaneldateUTC>{timestamp_utc}</plasectrxPaneldateUTC>
<plasectrxLastacc>19700101000000Z</plasectrxLastacc>
<plasectrxEvtypename>{event_data["evtypename"]}</plasectrxEvtypename>
<plasectrxBackgroundColor></plasectrxBackgroundColor>
<plasectrxForegroundColor></plasectrxForegroundColor>
<plasectrxAckBackgroundColor></plasectrxAckBackgroundColor>
<plasectrxAckForegroundColor></plasectrxAckForegroundColor>
<plasectrxEventname>{event_data["eventname"]}</plasectrxEventname>
<plasectrxPanelname>elevator test</plasectrxPanelname>
<plasectrxSourcename>{event_data["sourcename"]}</plasectrxSourcename>
<plasectrxSourcelocation></plasectrxSourcelocation>
<plasectrxSourcealtname></plasectrxSourcealtname>
<plasectrxPointaddress>750</plasectrxPointaddress>
<plasectrxPointDN>cn=750,ou=points,dc=plasec</plasectrxPointDN>
<plasectrxEvtypeaddress>5</plasectrxEvtypeaddress>
<plasectrxSourceDN>cn=100,cn=0,cn=9,ou=panels,cn=544de4aa06914073,ou=gateways,dc=plasec</plasectrxSourceDN>
<plasectrxSourcetype>40</plasectrxSourcetype>
<plasectrxOperatorname></plasectrxOperatorname>
<plasectrxPri>10</plasectrxPri>
<plasectrxMsg></plasectrxMsg>
<plasectrxIdentityDN></plasectrxIdentityDN>{person_data}
<plasectrxCardno>{card_no if person_data else '0'}</plasectrxCardno>
<plasectrxEmbossedno></plasectrxEmbossedno>
<plasectrxMi></plasectrxMi>
<plasectrxIssuelevel>-1</plasectrxIssuelevel>
<plasectrxFacilityCode>0</plasectrxFacilityCode>
<plasectrxExpiredat>19700101000000Z</plasectrxExpiredat>
<plasectrxActivdat>19700101000000Z</plasectrxActivdat>
<plasectrxIssuedat>19700101000000Z</plasectrxIssuedat>
<plasectrxHasCamera>0</plasectrxHasCamera>
<plasectrxHasNotes>0</plasectrxHasNotes>
<plasectrxHasSoftTriggerSet>0</plasectrxHasSoftTriggerSet>
<plasectrxShowVideo>0</plasectrxShowVideo>
<plasectrxSeqno>0</plasectrxSeqno>
<plasectrxIsAlarm>{event_data["is_alarm"]}</plasectrxIsAlarm>
</EVENT>"""
    
    return event

def send_events(host, port, count, interval, event_type):
    """Send events to the TCP server."""
    try:
        # Connect to server
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((host, port))
        
        print(f"Connected to {host}:{port}")
        print(f"Sending {count} events at {interval}s intervals")
        
        # Send events
        for i in range(count):
            event = generate_event(event_type)
            client.sendall(event.encode())
            
            print(f"Sent event {i+1}/{count} ({event_type})")
            
            if i < count - 1:  # Don't sleep after the last event
                time.sleep(interval)
                
        client.close()
        print("Done sending events")
        
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Is the server running on {host}:{port}?")
    except Exception as e:
        print(f"Error: {e}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate and send test XML events")
    parser.add_argument("--host", default="localhost", help="Server hostname")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--count", type=int, default=10, help="Number of events to send")
    parser.add_argument("--interval", type=float, default=1.0, help="Interval between events (seconds)")
    parser.add_argument("--type", choices=["random", "alarm", "access_granted", "access_denied"], 
                        default="random", help="Event type")
    
    args = parser.parse_args()
    send_events(args.host, args.port, args.count, args.interval, args.type)

if __name__ == "__main__":
    main()
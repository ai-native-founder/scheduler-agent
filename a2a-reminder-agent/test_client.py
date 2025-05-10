"""
Simple client for testing the A2A Reminder Agent.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Agent URL
AGENT_URL = "http://localhost:10000/a2a"

async def send_reminder_request(message: str):
    """Send a reminder request to the A2A agent."""
    client = httpx.AsyncClient()
    
    # Create the A2A request JSON
    task_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    
    request_data = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "sendTaskSubscribe",
        "params": {
            "id": task_id,
            "sessionId": session_id,
            "message": {
                "role": "user",
                "parts": [
                    {
                        "type": "text",
                        "text": message
                    }
                ]
            },
            "pushNotificationConfig": None,
            "acceptedOutputModes": ["text"],
            "historyLength": 10
        }
    }
    
    try:
        logger.info(f"Sending request: {message}")
        response = await client.post(
            AGENT_URL,
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        # Process the response events
        if response.status_code == 200:
            text_response = response.text
            events = text_response.strip().split("\n\n")
            
            for event in events:
                if event.startswith("data:"):
                    try:
                        data = json.loads(event[5:])
                        process_event(data)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse event: {event}")
        else:
            logger.error(f"Request failed with status code: {response.status_code}")
            logger.error(response.text)
    
    finally:
        await client.aclose()

def process_event(event):
    """Process an event from the A2A agent."""
    if "result" in event:
        result = event["result"]
        if "status" in result:
            state = result["status"]["state"]
            logger.info(f"Task state: {state}")
            
            if result["status"].get("message"):
                message = result["status"]["message"]
                if message.get("parts"):
                    for part in message["parts"]:
                        if part["type"] == "text":
                            logger.info(f"Agent: {part['text']}")
    
    elif "artifact" in event:
        artifact = event["artifact"]
        if artifact.get("parts"):
            for part in artifact["parts"]:
                if part["type"] == "text":
                    logger.info(f"Final result: {part['text']}")

async def main():
    """Run the test client."""
    print("==== A2A Reminder Agent Test Client ====")
    print("Enter your reminder request (or 'exit' to quit):")
    
    while True:
        user_input = input("> ")
        if user_input.lower() == "exit":
            break
        
        await send_reminder_request(user_input)
        print("\nEnter another reminder request or 'exit' to quit:")

if __name__ == "__main__":
    asyncio.run(main())

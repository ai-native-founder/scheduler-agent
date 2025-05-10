"""
Test script for the reminder agent.
"""
import os
import datetime
from dotenv import load_dotenv
from agent import process_reminder

# Load environment variables
load_dotenv()

def test_reminder_agent():
    """Test the reminder agent with a sample reminder message."""
    # Check if the OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your_openai_api_key":
        print("⚠️ Error: Please set your OpenAI API key in the .env file.")
        return
    
    # Sample reminder message
    message = "Remind me to call John tomorrow at 3pm"
    
    print(f"Processing reminder: '{message}'")
    
    try:
        # Process the reminder message
        result = process_reminder(message)
        
        # Print the final message
        print("\nAgent response:")
        for msg in result.messages:
            if msg.type == "ai":
                print(f"AI: {msg.content}")
            elif msg.type == "human":
                print(f"Human: {msg.content}")
        
        print("\nScheduled reminders:")
        from scheduler import reminder_scheduler
        reminders = reminder_scheduler.get_all_reminders()
        
        if reminders:
            for reminder_id, details in reminders.items():
                print(f"ID: {reminder_id}")
                print(f"Time: {details['time']}")
                print(f"Message: {details['payload']['message']}")
                print(f"Webhook URL: {details['webhook_url']}")
                print("---")
        else:
            print("No reminders scheduled.")
            
    except Exception as e:
        print(f"Error testing agent: {str(e)}")

if __name__ == "__main__":
    test_reminder_agent()

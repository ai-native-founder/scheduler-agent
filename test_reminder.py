"""
Simple test script for the reminder agent to verify functionality.
"""
import os
from dotenv import load_dotenv
from agent import process_reminder

# Ensure environment variables are loaded
load_dotenv()

def main():
    # Check if OPENAI_API_KEY is set
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key":
        print("⚠️ Please set your OPENAI_API_KEY in the .env file")
        return
    
    # Sample reminder message
    reminder_message = "Remind me to call John tomorrow at 3pm"
    
    print(f"Processing reminder: '{reminder_message}'")
    print("-" * 50)
    
    # Process the reminder
    try:
        result = process_reminder(reminder_message)
        
        # Print messages from the result
        print("\nConversation:")
        for msg in result.messages:
            role = msg.type
            content = msg.content
            print(f"{role.capitalize()}: {content}")
            
        # Print scheduled reminders
        print("\nScheduled Reminders:")
        from scheduler import reminder_scheduler
        reminders = reminder_scheduler.get_all_reminders()
        
        if not reminders:
            print("No reminders were scheduled.")
        else:
            for reminder_id, details in reminders.items():
                print(f"ID: {reminder_id}")
                print(f"Time: {details['time']}")
                print(f"Message: {details['payload']['message']}")
                print(f"Webhook URL: {details['webhook_url']}")
                print("-" * 30)
                
    except Exception as e:
        print(f"Error running the reminder agent: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

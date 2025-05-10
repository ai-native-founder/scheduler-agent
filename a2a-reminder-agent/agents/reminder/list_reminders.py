"""
Utility script to list all scheduled reminders.
"""
import sys
import os
from dotenv import load_dotenv
from .scheduler import reminder_scheduler

load_dotenv()

def list_all_reminders():
    """List all scheduled reminders."""
    reminders = reminder_scheduler.get_all_reminders()
    
    if not reminders:
        print("No reminders are currently scheduled.")
        return
    
    print("\n----- Currently Scheduled Reminders -----")
    for reminder_id, details in reminders.items():
        print(f"\nReminder ID: {reminder_id}")
        print(f"Time: {details['time']}")
        message = details['payload'].get('message', 'No message specified')
        print(f"Message: {message}")
        print(f"Webhook URL: {details['webhook_url']}")
        print("-" * 40)

if __name__ == "__main__":
    list_all_reminders()

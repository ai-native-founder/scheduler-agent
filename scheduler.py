"""
Scheduler module using APScheduler to handle webhook triggers.
"""
import datetime
import logging
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReminderScheduler:
    """
    A scheduler for managing and triggering reminders via webhooks.
    """
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.jobs = {}
        logger.info("Scheduler initialized and started")
    
    def schedule_reminder(self, reminder_time, webhook_url, payload, reminder_id=None):
        """
        Schedule a reminder to trigger a webhook at the specified time.
        
        Args:
            reminder_time (datetime): When to trigger the reminder
            webhook_url (str): URL to send the webhook to
            payload (dict): Data to include in the webhook
            reminder_id (str, optional): Unique ID for the reminder
            
        Returns:
            str: The ID of the scheduled reminder
        """
        if reminder_id is None:
            reminder_id = f"reminder_{len(self.jobs) + 1}"
            
        # Create job to trigger webhook
        job = self.scheduler.add_job(
            self._trigger_webhook,
            trigger=DateTrigger(run_date=reminder_time),
            args=[webhook_url, payload, reminder_id],
            id=reminder_id
        )
        
        self.jobs[reminder_id] = {
            "job": job,
            "time": reminder_time,
            "webhook_url": webhook_url,
            "payload": payload
        }
        
        logger.info(f"Scheduled reminder {reminder_id} for {reminder_time}")
        return reminder_id
    
    def _trigger_webhook(self, webhook_url, payload, reminder_id):
        """
        Trigger the webhook for a scheduled reminder.
        
        Args:
            webhook_url (str): URL to send the webhook to
            payload (dict): Data to include in the webhook
            reminder_id (str): ID of the reminder
        """
        try:
            response = requests.post(webhook_url, json=payload)
            logger.info(f"Triggered reminder {reminder_id} - Status: {response.status_code}")
            # Remove job from tracking dict after it's executed
            if reminder_id in self.jobs:
                del self.jobs[reminder_id]
        except Exception as e:
            logger.error(f"Failed to trigger reminder {reminder_id}: {str(e)}")
    
    def cancel_reminder(self, reminder_id):
        """
        Cancel a scheduled reminder.
        
        Args:
            reminder_id (str): ID of the reminder to cancel
            
        Returns:
            bool: Whether the reminder was successfully canceled
        """
        if reminder_id in self.jobs:
            self.scheduler.remove_job(reminder_id)
            del self.jobs[reminder_id]
            logger.info(f"Canceled reminder {reminder_id}")
            return True
        logger.warning(f"Could not cancel reminder {reminder_id}: not found")
        return False
    
    def get_all_reminders(self):
        """
        Get all scheduled reminders.
        
        Returns:
            dict: Dictionary of all scheduled reminders
        """
        return {
            reminder_id: {
                "time": job_info["time"],
                "webhook_url": job_info["webhook_url"],
                "payload": job_info["payload"]
            } for reminder_id, job_info in self.jobs.items()
        }

# Create a global instance of the scheduler
reminder_scheduler = ReminderScheduler()

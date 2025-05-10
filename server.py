"""
FastAPI server for the reminder agent.
"""
import os
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from agent import process_reminder
from scheduler import reminder_scheduler

# Initialize FastAPI app
app = FastAPI(title="Reminder Agent API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReminderRequest(BaseModel):
    """Request model for creating a reminder."""
    message: str

class WebhookRequest(BaseModel):
    """Request model for receiving webhooks."""
    message: str
    scheduled_at: str

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Reminder Agent API is running. See /docs for API documentation."}

@app.post("/reminder")
async def create_reminder(request: ReminderRequest):
    """
    Create a new reminder from natural language input.
    The agent will parse the message and schedule a reminder.
    """
    try:
        # Process the reminder message
        result = process_reminder(request.message)
        # Extract the final message
        final_message = result.messages[-1].content
        return {"status": "success", "message": final_message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating reminder: {str(e)}")

@app.get("/reminders")
async def list_reminders():
    """List all active reminders."""
    reminders = reminder_scheduler.get_all_reminders()
    return {"reminders": reminders}

@app.delete("/reminder/{reminder_id}")
async def cancel_reminder(reminder_id: str):
    """Cancel a reminder by ID."""
    success = reminder_scheduler.cancel_reminder(reminder_id)
    if success:
        return {"status": "success", "message": f"Reminder {reminder_id} canceled"}
    else:
        raise HTTPException(status_code=404, detail=f"Reminder {reminder_id} not found")

@app.post("/webhook")
async def handle_webhook(data: WebhookRequest):
    """
    Webhook endpoint for receiving triggered reminders.
    In a real implementation, this would forward the reminder to the user.
    """
    # Log the received webhook (in a real app, this would notify the user)
    print(f"Reminder received: {data.message} (scheduled at {data.scheduled_at})")
    return {"status": "success", "message": "Webhook received"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

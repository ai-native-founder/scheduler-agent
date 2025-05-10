# Reminder Agent

A simple agent built using LangGraph that interprets natural language inputs and schedules webhook reminders.

## Features

- Natural language processing to interpret reminder requests
- Uses APScheduler for reliable scheduling
- Webhook trigger system to send reminders
- Simple API for creating and managing reminders

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your API keys:
```
OPENAI_API_KEY=your_openai_api_key
```

3. Run the server:
```bash
uvicorn server:app --reload
```

## Usage

Send a POST request to the `/reminder` endpoint with your reminder message:

```bash
curl -X POST http://localhost:8000/reminder -H "Content-Type: application/json" -d '{"message": "Remind me to call John tomorrow at 3pm"}'
```

The agent will interpret the message and schedule a webhook to be triggered at the specified time.

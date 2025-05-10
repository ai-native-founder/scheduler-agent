# A2A Reminder Agent

A reminder agent built with LangGraph that interprets natural language inputs and schedules webhook reminders using the A2A (Agent-to-Agent) protocol.

## Features

- Natural language processing to interpret reminder requests
- Uses APScheduler for reliable scheduling
- Webhook trigger system to send reminders
- Implements the A2A protocol for seamless agent-to-agent communication
- Supports streaming responses and push notifications

## Architecture

This agent is built using:

- **LangGraph**: For the agent workflow and state management
- **APScheduler**: For scheduling reminder tasks
- **A2A Protocol**: For standardized agent communication
- **OpenAI**: For natural language understanding

## Setup

1. Copy your OpenAI API key to the `.env` file:
```
OPENAI_API_KEY=your_openai_api_key
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the agent:
```bash
python -m agents.reminder
```

This will start the A2A Reminder Agent server on http://localhost:10000.

## Usage

The agent can be interacted with using any A2A-compatible client. You can send natural language requests like:

- "Remind me to call John tomorrow at 3pm"
- "Schedule a meeting with the team on Monday at 10am"
- "Set a reminder to take my medication every day at 8am"

The agent will interpret these requests, extract the time and message details, and schedule a reminder to be triggered at the specified time.

## API Endpoints

- `/.well-known/agent.json`: Provides agent metadata and capabilities (A2A discovery)
- `/.well-known/jwks.json`: Provides JWT keys for push notification authentication
- A2A standard JSON-RPC endpoints for task submission and management

## A2A Implementation

This agent follows the A2A protocol specification, implementing:

- Task submission endpoints
- Streaming response capabilities
- Push notification support
- Proper task state management

"""
Reminder agent built with LangGraph that interprets natural language
and schedules reminders using the scheduler module.
"""
import os
import datetime
import json
import uuid
from collections.abc import AsyncIterable
from typing import Any, Dict, List, Literal, Annotated, Optional

# Import MCP client for datetime
import mcp
import pytz  # For timezone handling in fallback mode

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field, validator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Import the scheduler implementation
from .scheduler import reminder_scheduler

# Create memory saver for LangGraph checkpointing
memory = MemorySaver()

def get_mcp_datetime_client():
    try:
        # Create an MCP client instance
        from mcp import ClientSession, StdioServerParameters
        session = ClientSession()
        
        # Connect to mcp-datetime server
        params = StdioServerParameters(command=["uvx", "mcp-datetime"])
        return session.connect_stdio_server(params)
    except Exception as e:
        print(f"Error connecting to MCP datetime server: {e}")
        return None

# Schema definition for reminder
class ReminderSchema(BaseModel):
    webhook_url: str = Field(..., description="URL to trigger when the reminder is due")
    time: str = Field(..., description="When to trigger the reminder in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)")
    message: str = Field(..., description="The reminder message")
    reminder_id: Optional[str] = Field(default=None, description="Unique identifier for this reminder")
    
    @validator('reminder_id', pre=True, always=True)
    def set_id(cls, v):
        # Always generate a new UUID if None is provided
        return v or str(uuid.uuid4())

# Tool definitions for the reminder agent
@tool
def schedule_reminder(
    webhook_url: Annotated[str, "URL to trigger when the reminder is due"],
    time: Annotated[str, "When to trigger the reminder in ISO format with timezone (YYYY-MM-DDTHH:MM:SS+HH:MM)"],
    message: Annotated[str, "The reminder message"],
    reminder_id: Annotated[str, "Unique identifier for this reminder"] = None
) -> str:
    """Schedule a reminder to be triggered at the specified time."""
    
    # Force schema validation and UUID generation
    reminder_data = ReminderSchema(
        webhook_url=webhook_url,
        time=time,
        message=message,
        reminder_id=reminder_id
    )
    
    try:
        # Parse the time with timezone awareness
        reminder_time = datetime.datetime.fromisoformat(reminder_data.time)
        if reminder_time.tzinfo is None:
            # Add current timezone if not specified
            current_tz = datetime.datetime.now().astimezone().tzinfo
            reminder_time = reminder_time.replace(tzinfo=current_tz)
    except ValueError:
        # If parsing fails, use current time + 1 hour as fallback
        reminder_time = datetime.datetime.now().astimezone() + datetime.timedelta(hours=1)
        reminder_data.time = reminder_time.isoformat()
        
    payload = {"message": reminder_data.message, "scheduled_at": reminder_data.time}
    
    scheduled_id = reminder_scheduler.schedule_reminder(
        reminder_time=reminder_time,
        webhook_url=reminder_data.webhook_url,
        payload=payload,
        reminder_id=reminder_data.reminder_id
    )
    
    return f"Reminder scheduled with ID: {scheduled_id}"

@tool
def get_current_datetime(format: Annotated[str, "Format for the datetime output (standard, iso, filename, japanese)"] = "iso") -> str:
    """Get the current date and time in the specified format.
    
    Args:
        format: The format to return the datetime in. Options include:
            - 'standard': Standard readable format (e.g., 'May 10, 2025, 6:54:53 AM')
            - 'iso': ISO 8601 format with timezone (e.g., '2025-05-10T06:54:53-03:00')
            - 'filename': Format suitable for filenames (e.g., '20250510065453')
            - 'japanese': Japanese format (e.g., '2025年5月10日 6時54分53秒')
    
    Returns:
        str: Formatted current datetime string
    """
    try:
        # Get the MCP client and use it to get the formatted datetime
        client = get_mcp_datetime_client()
        if client and hasattr(client, 'tools'):
            # Call the get_datetime tool on the MCP server
            result = client.tools.get_datetime(format=format)
            return result
        raise ValueError("MCP client tools not available")
    except Exception as e:
        # Log the error
        print(f"Error using MCP datetime: {e}")
        
        # Fallback to local datetime if MCP server fails
        now = datetime.datetime.now().astimezone()
        if format == "iso":
            return now.isoformat()
        elif format == "filename":
            return now.strftime("%Y%m%d%H%M%S")
        elif format == "japanese":
            return now.strftime("%Y年%m月%d日 %H時%M分%S秒")
        else:  # standard format
            return now.strftime("%B %d, %Y, %I:%M:%S %p")

@tool
def list_reminders() -> str:
    """List all currently scheduled reminders."""
    reminders = reminder_scheduler.get_all_reminders()
    
    if not reminders:
        return "You don't have any reminders scheduled."
    
    # Format the reminders in a readable way
    result = ["Here are your currently scheduled reminders:"]
    
    for reminder_id, details in reminders.items():
        scheduled_time = details["time"]
        # Convert to user's local time for display
        local_time = scheduled_time.astimezone()
        formatted_time = local_time.strftime('%Y-%m-%d %H:%M:%S %Z')
        
        message = details["payload"].get("message", "No message specified")
        result.append(f"\n- ID: {reminder_id}")
        result.append(f"  Time: {formatted_time}")
        result.append(f"  Message: {message}")
    
    return "\n".join(result)

# Response format class for structured agent responses
class ResponseFormat(BaseModel):
    """Respond to the user in this format."""
    status: Literal['input_required', 'completed', 'error'] = 'input_required'
    message: str

# State for the reminder agent
class AgentState(BaseModel):
    """State for the reminder agent."""
    messages: List[BaseMessage] = Field(default_factory=list)
    next: str = Field(default="")
    reminder_details: Dict[str, Any] = Field(default_factory=dict)

# Parser node to extract reminder details from natural language
def parser(state: AgentState) -> AgentState:
    """Parse the natural language input to extract reminder details."""
    messages = state.messages.copy()
    
    # Get current datetime using the tool instead of hardcoded value
    current_time = get_current_datetime(format="iso")
    
    # Add system message to instruct the LLM
    system_message = {
        "role": "system", 
        "content": """You are a reminder parsing assistant. 
        Extract the time and reminder details from the user's message.
        Use the schedule_reminder function to set up the reminder.
        
        CURRENT TIME: It is currently ${current_time}.
        
        You MUST use the current date and time as the reference point for all time calculations.
        Do NOT use hardcoded dates or times.
        
        When extracting time information:
        1. ALWAYS include timezone information in ISO format (e.g., 2025-05-10T10:30:00-03:00).
        2. Convert relative times (like 'tomorrow', 'next week', 'in an hour') to absolute timestamps.
        3. If the time is ambiguous, ask for clarification.
        
        Do NOT provide your own reminder_id value. The system will automatically generate a UUID.
        
        Set response status to input_required if you need more information from the user.
        Set response status to error if there is an error processing the request.
        Set response status to completed if the reminder was successfully scheduled.
        """.replace("${current_time}", current_time)
    }
    
    # Initialize OpenAI client with API key
    api_key = os.getenv("OPENAI_API_KEY")
    llm = ChatOpenAI(
        model="gpt-3.5-turbo", 
        temperature=0,
        openai_api_key=api_key
    )
    
    # Call the LLM to extract details
    response = llm.invoke(
        messages + [system_message],
        tools=[schedule_reminder],
        tool_choice={"type": "function", "function": {"name": "schedule_reminder"}}
    )
    
    # Extract the function call details
    if hasattr(response, "additional_kwargs") and "tool_calls" in response.additional_kwargs:
        tool_calls = response.additional_kwargs["tool_calls"]
        if tool_calls and len(tool_calls) > 0:
            function_call = tool_calls[0]["function"]
            reminder_args = json.loads(function_call["arguments"])
            
            # Generate a UUID if not present
            if "reminder_id" not in reminder_args or not reminder_args["reminder_id"]:
                reminder_args["reminder_id"] = str(uuid.uuid4())
            
            # Ensure schema validation is still happening
            try:
                # Validate against schema
                reminder_details = ReminderSchema(**reminder_args).dict()
                state.reminder_details = reminder_details
                state.next = "scheduler"
            except Exception as e:
                print(f"Schema validation error: {e}")
                # If validation fails, still ensure we have the data
                state.reminder_details = reminder_args
                state.next = "scheduler"
    else:
        state.next = "clarification"
        messages.append(
            AIMessage(content="I couldn't determine when to set the reminder. Please provide a clearer time.")
        )
    
    state.messages = messages + [response]
    return state

# Scheduler node to create the reminder
def scheduler(state: AgentState) -> AgentState:
    """Use the scheduler to create the reminder."""
    details = state.reminder_details
    messages = state.messages.copy()
    
    # Default webhook URL if not specified
    if "webhook_url" not in details or not details["webhook_url"]:
        details["webhook_url"] = "http://localhost:8000/webhook"
    
    # Ensure reminder_id is present
    if "reminder_id" not in details or not details["reminder_id"]:
        details["reminder_id"] = str(uuid.uuid4())
    
    # Schedule the reminder using the tool
    result = schedule_reminder(
        webhook_url=details["webhook_url"],
        time=details["time"],
        message=details["message"],
        reminder_id=details["reminder_id"]
    )
    
    messages.append(AIMessage(content=result))
    state.messages = messages
    state.next = END
    
    return state

# Clarification node to ask for more details
def clarification(state: AgentState) -> AgentState:
    """Ask for clarification on unclear inputs."""
    messages = state.messages.copy()
    
    # Initialize OpenAI client with API key
    api_key = os.getenv("OPENAI_API_KEY")
    llm = ChatOpenAI(
        model="gpt-3.5-turbo", 
        temperature=0,
        openai_api_key=api_key
    )
    
    response = llm.invoke(
        messages + [
            HumanMessage(content="Could you please provide a clearer time for when you want the reminder?")
        ]
    )
    
    messages.append(response)
    state.messages = messages
    state.next = "parser"
    
    return state

class ReminderAgent:
    SYSTEM_INSTRUCTION = (
        'You are a reminder scheduling assistant. '
        'Your job is to help users schedule reminders based on their natural language requests. '
        'You have access to the following tools:\n'
        '1. schedule_reminder: Schedule a reminder to be triggered at a specific time via webhook\n'
        '2. list_reminders: List all currently scheduled reminders\n'
        '3. get_current_datetime: Get the current date and time in various formats\n\n'
        'IMPORTANT: Always use the get_current_datetime tool to determine the current time.\n'
        'Never rely on hardcoded dates or times. The get_current_datetime tool provides accurate time with timezone information.\n\n'
        'If the user asks to see their reminders, use the list_reminders tool.\n'
        'If the user wants to schedule a reminder, use get_current_datetime first to determine the current time,\n'
        'then schedule the reminder relative to that time.\n'
        'If the time is unclear, ask for clarification.\n\n'
        'Set response status to input_required if the user needs to provide more information.\n'
        'Set response status to error if there is an error while processing the request.\n'
        'Set response status to completed if the reminder was successfully scheduled or listed.'
    )

    def __init__(self):
        """Initialize the reminder agent with the LangGraph components."""
        # Create the graph
        self.graph = self._create_reminder_graph()
        
        # Supported content types
        self.SUPPORTED_CONTENT_TYPES = ['text', 'text/plain']

    def _create_reminder_graph(self):
        """Create the LangGraph for the reminder agent using LangGraph 0.4.3 compatibility."""
        from langgraph.prebuilt import create_react_agent
        
        # Initialize LLM
        api_key = os.getenv("OPENAI_API_KEY")
        llm = ChatOpenAI(
            model="gpt-3.5-turbo", 
            temperature=0,
            openai_api_key=api_key
        )
        
        # Use create_react_agent which is available in LangGraph 0.4.3
        react_agent = create_react_agent(
            model=llm,
            tools=[schedule_reminder, list_reminders, get_current_datetime],
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION
        )
        
        return react_agent

    def invoke(self, query, sessionId) -> dict:
        """Process a reminder request and return the result."""
        config = {'configurable': {'thread_id': sessionId}}
        result = self.graph.invoke({"messages": [{"role": "user", "content": query}]}, config)
        return self._process_agent_response(result)

    async def stream(self, query, sessionId) -> AsyncIterable[dict[str, Any]]:
        """Stream the agent's response for a reminder request."""
        config = {'configurable': {'thread_id': sessionId}}

        # First, yield a message indicating we're processing
        yield {
            'is_task_complete': False,
            'require_user_input': False,
            'content': 'Processing your reminder request...',
        }
        
        # For agents with streaming, we'd implement real streaming here
        # But for now we'll just invoke normally and yield the final result
        result = self.graph.invoke({"messages": [{"role": "user", "content": query}]}, config)
        
        # Process the result and yield the response
        yield self._process_agent_response(result)

    def _process_agent_response(self, result):
        """Process the response from the react agent."""
        # Extract the last message from the result
        if isinstance(result, dict):
            messages = result.get("messages", [])
        else:
            # Handle the case where result is not a dictionary
            messages = getattr(result, "messages", [])
            
        if not messages:
            return {
                'is_task_complete': False,
                'require_user_input': True,
                'content': "I need more information to schedule your reminder."
            }
            
        # Get the last message from the agent
        for msg in reversed(messages):
            # Handle both dict and AIMessage objects
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                content = msg.get("content", "")
                break
            elif isinstance(msg, AIMessage):
                content = msg.content
                break
        else:
            content = "I need more information to schedule your reminder."
        
        # Determine the response type based on the content
        if "scheduled with ID" in content:
            return {
                'is_task_complete': True,
                'require_user_input': False,
                'content': content,
            }
        elif any(phrase in content.lower() for phrase in ["clearer", "more specific", "when", "time", "provide more", "could you clarify"]):
            return {
                'is_task_complete': False,
                'require_user_input': True,
                'content': content,
            }
        else:
            return {
                'is_task_complete': False,
                'require_user_input': True,
                'content': content,
            }

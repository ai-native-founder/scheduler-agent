"""
Reminder agent built with LangGraph that interprets natural language
and schedules reminders using the scheduler module.
"""
import os
import datetime
import json
from typing import Dict, Any, List, Annotated
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from scheduler import reminder_scheduler

# Load environment variables
load_dotenv()

# Initialize the LLM with compatibility settings for OpenAI 1.12.0
import os
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(
    model="gpt-3.5-turbo",
    temperature=0,
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    # Don't pass proxy settings to avoid compatibility issues with older OpenAI client
    client_kwargs={
        "api_key": os.getenv("OPENAI_API_KEY"),
    }
)

# Define the agent state using Pydantic for compatibility with LangGraph 0.4.3
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    """State for the reminder agent."""
    messages: List[BaseMessage] = Field(default_factory=list)
    next: str = Field(default="")
    reminder_details: Dict[str, Any] = Field(default_factory=dict)

# Define tools
@tool
def schedule_reminder(
    webhook_url: Annotated[str, "URL to trigger when the reminder is due"],
    time: Annotated[str, "When to trigger the reminder in ISO format (YYYY-MM-DDTHH:MM:SS)"],
    message: Annotated[str, "The reminder message"],
    reminder_id: Annotated[str, "Unique identifier for this reminder"] = None
) -> str:
    """Schedule a reminder to be triggered at the specified time."""
    reminder_time = datetime.datetime.fromisoformat(time)
    payload = {"message": message, "scheduled_at": time}
    
    reminder_id = reminder_scheduler.schedule_reminder(
        reminder_time=reminder_time,
        webhook_url=webhook_url,
        payload=payload,
        reminder_id=reminder_id
    )
    
    return f"Reminder scheduled with ID: {reminder_id}"

# The schedule_reminder function is already converted to a tool using the @tool decorator

# Parser node to extract reminder details from natural language
def parser(state: AgentState) -> AgentState:
    """Parse the natural language input to extract reminder details."""
    messages = state.messages.copy()
    
    # Add system message to instruct the LLM
    system_message = {
        "role": "system", 
        "content": """You are a reminder parsing assistant. 
        Extract the time and reminder details from the user's message.
        Use the schedule_reminder function to set up the reminder.
        Infer the exact date and time from the user's message, accounting for relative times like 'tomorrow', 'next week', etc.
        """
    }
    
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
            reminder_details = json.loads(function_call["arguments"])
            state.reminder_details = reminder_details
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
    messages = state.messages.copy()
    
    # Default webhook URL if not provided
    if "webhook_url" not in state.reminder_details:
        state.reminder_details["webhook_url"] = "http://localhost:8000/webhook"
    
    # Schedule the reminder
    result = schedule_reminder(**state.reminder_details)
    
    messages.append(AIMessage(content=f"✅ {result}"))
    state.messages = messages
    state.next = END
    
    return state

# Clarification node to ask for more details
def clarification(state: AgentState) -> AgentState:
    """Ask for clarification on unclear inputs."""
    messages = state.messages.copy()
    
    response = llm.invoke(
        messages + [
            HumanMessage(content="Could you please provide a clearer time for when you want the reminder?")
        ]
    )
    
    messages.append(response)
    state.messages = messages
    state.next = "parser"
    
    return state

# Create the graph
def create_reminder_graph():
    """Create the LangGraph for the reminder agent."""
    # Create graph with the AgentState model
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("parser", parser)
    graph.add_node("scheduler", scheduler)
    graph.add_node("clarification", clarification)
    
    # Add edges - connect nodes based on state.next decision
    graph.add_edge("parser", lambda state: state.next)
    graph.add_edge("scheduler", lambda state: state.next)
    graph.add_edge("clarification", lambda state: state.next)
    
    # Add entry point
    graph.set_entry_point("parser")
    
    # Compile the graph
    return graph.compile()

# Create the compiled graph
reminder_graph = create_reminder_graph()

def process_reminder(message: str):
    """Process a reminder message through the graph."""
    state = AgentState(messages=[HumanMessage(content=message)])
    result = reminder_graph.invoke(state)
    return result

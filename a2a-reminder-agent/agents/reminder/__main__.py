"""
Main entry point for the A2A Reminder Agent.
"""
import logging
import os

import click

# Import approach that works for direct running
import sys
import os

# Add the parent directory to the Python path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Now we can import regardless of how the script is run
try:
    # Try relative imports first (when running as a module)
    from .agent import ReminderAgent
    from .task_manager import AgentTaskManager
    from .scheduler import reminder_scheduler
except ImportError:
    # Fallback to direct imports from the current directory
    from agent import ReminderAgent
    from task_manager import AgentTaskManager
    from scheduler import reminder_scheduler
from common.server import A2AServer
from common.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    MissingAPIKeyError,
)
from common.utils.push_notification_auth import PushNotificationSenderAuth
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option('--host', 'host', default='localhost')
@click.option('--port', 'port', default=10000)
def main(host, port):
    """Starts the Reminder Agent server with A2A protocol."""
    try:
        if not os.getenv('OPENAI_API_KEY'):
            raise MissingAPIKeyError(
                'OPENAI_API_KEY environment variable not set.'
            )

        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        skill = AgentSkill(
            id='schedule_reminder',
            name='Reminder Scheduling Tool',
            description='Schedules reminders based on natural language instructions',
            tags=['reminders', 'scheduling', 'calendar'],
            examples=[
                'Remind me to call John tomorrow at 3pm',
                'Schedule a meeting with the team on Monday at 10am',
                'Set a reminder to take my medication every day at 8am'
            ],
        )
        agent_card = AgentCard(
            name='Reminder Agent',
            description='An agent that lists, retrieves and schedules reminders based on natural language instructions',
            url=f'http://{host}:{port}',
            version='1.0.0',
            defaultInputModes=ReminderAgent().SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ReminderAgent().SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()
        
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(
                agent=ReminderAgent(),
                notification_sender_auth=notification_sender_auth,
            ),
            host=host,
            port=port,
        )

        server.app.add_route(
            '/.well-known/jwks.json',
            notification_sender_auth.handle_jwks_endpoint,
            methods=['GET'],
        )
        
        # Agent.json endpoint for A2A discovery
        from starlette.responses import JSONResponse
        server.app.add_route(
            "/.well-known/agent.json",
            lambda request: JSONResponse(
                content=agent_card.model_dump()
            ),
            methods=["GET"],
        )
        
        # Add an endpoint to list all reminders
        # Note: reminder_scheduler is already imported at the top of the file
        @server.app.route("/reminders", methods=["GET"])
        async def list_reminders(request):
            reminders = reminder_scheduler.get_all_reminders()
            formatted_reminders = []
            
            for reminder_id, details in reminders.items():
                formatted_reminders.append({
                    "id": reminder_id,
                    "time": str(details["time"]),
                    "message": details["payload"].get("message", "No message"),
                    "webhook_url": details["webhook_url"]
                })
                
            return JSONResponse({
                "count": len(formatted_reminders),
                "reminders": formatted_reminders
            })
        
        logger.info(f'Starting Reminder Agent server on {host}:{port}')
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f'Error: {e}')
        exit(1)
    except Exception as e:
        logger.error(f'An error occurred during server startup: {e}')
        exit(1)


if __name__ == '__main__':
    main()

"""
Task manager for the reminder agent using the A2A protocol.
"""
import asyncio
import logging
import traceback

from collections.abc import AsyncIterable

import sys
import os

# Add parent directory to Python path if not already there
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Try different import approaches
try:
    # Try relative import first
    from .agent import ReminderAgent
except ImportError:
    try:
        # Try direct import
        from agent import ReminderAgent
    except ImportError:
        # Last resort: try absolute import with updated path
        from agents.reminder.agent import ReminderAgent
from common.server import utils
from common.server.task_manager import InMemoryTaskManager
from common.types import (
    Artifact,
    InternalError,
    InvalidParamsError,
    JSONRPCResponse,
    Message,
    PushNotificationConfig,
    SendTaskRequest,
    SendTaskResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from common.utils.push_notification_auth import PushNotificationSenderAuth


logger = logging.getLogger(__name__)


class AgentTaskManager(InMemoryTaskManager):
    def __init__(
        self,
        agent: ReminderAgent,
        notification_sender_auth: PushNotificationSenderAuth,
    ):
        super().__init__()
        self.agent = agent
        self.notification_sender_auth = notification_sender_auth

    async def _run_streaming_agent(self, request: SendTaskStreamingRequest):
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)

        # Ensure the task exists in the store before updating it
        await self.upsert_task(task_send_params)

        try:
            async for item in self.agent.stream(
                query, task_send_params.sessionId
            ):
                is_task_complete = item['is_task_complete']
                require_user_input = item['require_user_input']
                artifact = None
                message = None
                parts = [{'type': 'text', 'text': item['content']}]
                end_stream = False

                if not is_task_complete and not require_user_input:
                    task_state = TaskState.WORKING
                    message = Message(role='agent', parts=parts)
                elif require_user_input:
                    task_state = TaskState.INPUT_REQUIRED
                    message = Message(role='agent', parts=parts)
                    end_stream = True
                else:
                    task_state = TaskState.COMPLETED
                    artifact = Artifact(parts=parts, index=0, append=False)
                    end_stream = True

                task_status = TaskStatus(state=task_state, message=message)
                latest_task = await self.update_store(
                    task_send_params.id,
                    task_status,
                    None if artifact is None else [artifact],
                )
                await self.send_task_notification(latest_task)

                if artifact:
                    task_artifact_update_event = TaskArtifactUpdateEvent(
                        id=task_send_params.id, artifact=artifact
                    )
                    await self.enqueue_events_for_sse(
                        task_send_params.id, task_artifact_update_event
                    )

                task_update_event = TaskStatusUpdateEvent(
                    id=task_send_params.id, status=task_status, final=end_stream
                )
                await self.enqueue_events_for_sse(
                    task_send_params.id, task_update_event
                )

        except Exception as e:
            logger.error(f'An error occurred while streaming the response: {e}')
            await self.enqueue_events_for_sse(
                task_send_params.id,
                InternalError(
                    message=f'An error occurred while streaming the response: {e}'
                ),
            )

    def _validate_request(
        self, request: SendTaskRequest | SendTaskStreamingRequest
    ) -> JSONRPCResponse | None:
        task_send_params: TaskSendParams = request.params
        if not utils.are_modalities_compatible(
            task_send_params.acceptedOutputModes,
            self.agent.SUPPORTED_CONTENT_TYPES,
        ):
            logger.warning(
                'Unsupported output mode. Received %s, Support %s',
                task_send_params.acceptedOutputModes,
                self.agent.SUPPORTED_CONTENT_TYPES,
            )
            return JSONRPCResponse(
                id=request.id,
                error=InvalidParamsError(
                    message='Agent does not support the requested output mode'
                ),
            )

        message = task_send_params.message
        if len(message.parts) != 1:
            return JSONRPCResponse(
                id=request.id,
                error=InvalidParamsError(
                    message='Currently we only support one message part'
                ),
            )

        if not isinstance(message.parts[0], TextPart):
            return JSONRPCResponse(
                id=request.id,
                error=InvalidParamsError(
                    message='Currently we only support text modality'
                ),
            )

        return None

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """Handles the 'send task' request."""
        validation_error = self._validate_request(request)
        if validation_error:
            return validation_error

        try:
            task_send_params: TaskSendParams = request.params
            task_id = task_send_params.id
            task_status = TaskStatus(state=TaskState.WORKING)
            await self.update_store(task_id, task_status)

            query = self._get_user_query(task_send_params)
            agent_response = self.agent.invoke(query, task_send_params.sessionId)
            
            return await self._process_agent_response(request, agent_response)
        except Exception as e:
            logger.error(f'Error sending task: {e}')
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message='An error occurred during task processing'
                ),
            )

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        validation_error = self._validate_request(request)
        if validation_error:
            return validation_error

        try:
            # Set up push notification URL
            task_send_params: TaskSendParams = request.params
            
            # Ensure the task exists in the store before proceeding
            await self.upsert_task(task_send_params)
            
            push_notification_config = task_send_params.pushNotification
            if push_notification_config:
                is_verified = await self.set_push_notification_info(
                    task_send_params.id, push_notification_config
                )
                if not is_verified:
                    return JSONRPCResponse(
                        id=request.id,
                        error=InvalidParamsError(
                            message='Push notification URL is invalid'
                        ),
                    )

            sse_event_queue = await self.setup_sse_consumer(
                task_send_params.id, False
            )

            asyncio.create_task(self._run_streaming_agent(request))

            return self.dequeue_events_for_sse(
                request.id, task_send_params.id, sse_event_queue
            )
        except Exception as e:
            logger.error(f'Error in SSE stream: {e}')
            print(traceback.format_exc())
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message='An error occurred while streaming the response'
                ),
            )

    async def _process_agent_response(
        self, request: SendTaskRequest, agent_response: dict
    ) -> SendTaskResponse:
        """Processes the agent's response and updates the task store."""
        task_send_params: TaskSendParams = request.params
        task_id = task_send_params.id
        history_length = task_send_params.historyLength
        task_status = None

        parts = [{'type': 'text', 'text': agent_response['content']}]
        artifact = None
        if agent_response['require_user_input']:
            task_status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message=Message(role='agent', parts=parts),
            )
        else:
            task_status = TaskStatus(state=TaskState.COMPLETED)
            artifact = Artifact(parts=parts)
        task = await self.update_store(
            task_id, task_status, None if artifact is None else [artifact]
        )
        task_result = self.append_task_history(task, history_length)
        await self.send_task_notification(task)
        return SendTaskResponse(id=request.id, result=task_result)

    def _get_user_query(self, task_send_params: TaskSendParams) -> str:
        part = task_send_params.message.parts[0]
        if not isinstance(part, TextPart):
            raise ValueError('Only text parts are supported')
        return part.text

    async def send_task_notification(self, task: Task):
        if not await self.has_push_notification_info(task.id):
            logger.info(f'No push notification info found for task {task.id}')
            return
        push_info = await self.get_push_notification_info(task.id)

        logger.info(f'Notifying for task {task.id} => {task.status.state}')
        await self.notification_sender_auth.send_push_notification(
            push_info.url, data=task.model_dump(exclude_none=True)
        )

    async def on_resubscribe_to_task(
        self, request
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        task_id_params: TaskIdParams = request.params
        try:
            sse_event_queue = await self.setup_sse_consumer(
                task_id_params.id, True
            )
            return self.dequeue_events_for_sse(
                request.id, task_id_params.id, sse_event_queue
            )
        except Exception as e:
            logger.error(f'Error while reconnecting to SSE stream: {e}')
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message=f'An error occurred while reconnecting to stream: {e}'
                ),
            )

    async def set_push_notification_info(
        self, task_id: str, push_notification_config: PushNotificationConfig
    ):
        # Verify the ownership of notification URL by issuing a challenge request.
        is_verified = (
            await self.notification_sender_auth.verify_push_notification_url(
                push_notification_config.url
            )
        )
        if not is_verified:
            return False

        await super().set_push_notification_info(
            task_id, push_notification_config
        )
        return True

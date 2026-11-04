"""Shared constants for the session-level SSE event bus."""

from uuid import UUID

SESSION_EVENT_STREAM_KEY_PREFIX = "session_event_stream"
SESSION_EVENT_STREAM_TTL_SECONDS = 3600
SESSION_EVENT_STREAM_MAXLEN = 50000

HIL_INTERACTION_STATE_KEY_PREFIX = "hil_interaction_state"
HIL_INTERACTION_STATE_TTL_SECONDS = 3600
HIL_INTERACTION_LEASE_MS = 3600_000
HIL_LEASE_HEARTBEAT_SECONDS = 60
HIL_INTERRUPT_DEFAULT_TIMEOUT_SECONDS = 3600

HUMAN_IN_LOOP_RECV_STREAM_KEY_PREFIX = "human_in_loop_recv_stream"

SSE_HEARTBEAT_SECONDS = 15


def session_event_stream_key(session_id: UUID | str) -> str:
    return f"{SESSION_EVENT_STREAM_KEY_PREFIX}:{session_id}"


def hil_interaction_state_key(session_id: UUID | str) -> str:
    return f"{HIL_INTERACTION_STATE_KEY_PREFIX}:{session_id}"


def human_in_loop_recv_stream_key(session_task_id: UUID | str) -> str:
    return f"{HUMAN_IN_LOOP_RECV_STREAM_KEY_PREFIX}:{session_task_id}"

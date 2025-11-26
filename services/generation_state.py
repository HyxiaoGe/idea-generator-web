"""
Generation state management service.
Handles generation locking, throttling, and progress tracking.
"""
import time
import threading
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import streamlit as st


class GenerationStatus(Enum):
    """Status of a generation task."""
    IDLE = "idle"
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class GenerationTask:
    """Represents a generation task."""
    task_id: str
    prompt: str
    mode: str
    status: GenerationStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0  # 0.0 to 1.0
    estimated_duration: float = 10.0  # seconds
    error: Optional[str] = None
    result: Optional[Any] = None
    cancelled: bool = False


class GenerationStateManager:
    """
    Manages generation state across the application.
    Provides locking and progress tracking.
    """

    # Estimated generation times by resolution (seconds)
    ESTIMATED_TIMES = {
        "1K": 8.0,
        "2K": 12.0,
        "4K": 18.0,
    }

    def __init__(self):
        """Initialize the state manager."""
        self._lock = threading.Lock()

    @staticmethod
    def _get_state_key(key: str) -> str:
        """Get the full session state key."""
        return f"gen_state_{key}"

    @staticmethod
    def init_session_state():
        """Initialize generation state in session state."""
        keys = {
            "current_task": None,
            "generation_history": [],
            "is_generating": False,
        }
        for key, default in keys.items():
            full_key = GenerationStateManager._get_state_key(key)
            if full_key not in st.session_state:
                st.session_state[full_key] = default

    @staticmethod
    def is_generating() -> bool:
        """Check if a generation is currently in progress."""
        GenerationStateManager.init_session_state()
        return st.session_state.get(
            GenerationStateManager._get_state_key("is_generating"),
            False
        )

    @staticmethod
    def can_start_generation() -> tuple[bool, str]:
        """
        Check if a new generation can be started.

        Returns:
            Tuple of (can_start, reason_if_not)
        """
        GenerationStateManager.init_session_state()

        # Check if already generating
        if GenerationStateManager.is_generating():
            return False, "generation_in_progress"

        return True, ""

    @staticmethod
    def start_generation(
        prompt: str,
        mode: str = "basic",
        resolution: str = "1K"
    ) -> Optional[GenerationTask]:
        """
        Start a new generation task.

        Args:
            prompt: The generation prompt
            mode: Generation mode (basic, chat, batch, etc.)
            resolution: Image resolution

        Returns:
            GenerationTask if started, None if cannot start
        """
        GenerationStateManager.init_session_state()

        can_start, reason = GenerationStateManager.can_start_generation()
        if not can_start:
            return None

        task = GenerationTask(
            task_id=str(uuid.uuid4())[:8],
            prompt=prompt,
            mode=mode,
            status=GenerationStatus.GENERATING,
            created_at=datetime.now(),
            started_at=datetime.now(),
            estimated_duration=GenerationStateManager.ESTIMATED_TIMES.get(resolution, 10.0),
        )

        st.session_state[GenerationStateManager._get_state_key("current_task")] = task
        st.session_state[GenerationStateManager._get_state_key("is_generating")] = True

        return task

    @staticmethod
    def update_progress(progress: float):
        """Update the current task progress (0.0 to 1.0)."""
        task = st.session_state.get(GenerationStateManager._get_state_key("current_task"))
        if task:
            task.progress = min(max(progress, 0.0), 1.0)

    @staticmethod
    def complete_generation(result: Any = None, error: str = None):
        """
        Mark the current generation as complete.

        Args:
            result: The generation result
            error: Error message if failed
        """
        GenerationStateManager.init_session_state()

        task = st.session_state.get(GenerationStateManager._get_state_key("current_task"))
        if task:
            task.completed_at = datetime.now()
            task.progress = 1.0
            task.result = result

            if error:
                task.status = GenerationStatus.FAILED
                task.error = error
            elif task.cancelled:
                task.status = GenerationStatus.CANCELLED
            else:
                task.status = GenerationStatus.COMPLETED

            # Add to history
            history = st.session_state.get(
                GenerationStateManager._get_state_key("generation_history"),
                []
            )
            history.insert(0, task)
            # Keep last 20 tasks
            st.session_state[GenerationStateManager._get_state_key("generation_history")] = history[:20]

        st.session_state[GenerationStateManager._get_state_key("is_generating")] = False
        st.session_state[GenerationStateManager._get_state_key("current_task")] = None

    @staticmethod
    def cancel_generation():
        """
        Request cancellation of the current generation.
        Note: This only sets a flag; the actual API call cannot be cancelled.
        """
        task = st.session_state.get(GenerationStateManager._get_state_key("current_task"))
        if task:
            task.cancelled = True
            task.status = GenerationStatus.CANCELLED

    @staticmethod
    def is_cancelled() -> bool:
        """Check if the current generation has been cancelled."""
        task = st.session_state.get(GenerationStateManager._get_state_key("current_task"))
        return task.cancelled if task else False

    @staticmethod
    def get_current_task() -> Optional[GenerationTask]:
        """Get the current generation task."""
        return st.session_state.get(GenerationStateManager._get_state_key("current_task"))

    @staticmethod
    def get_estimated_remaining_time() -> float:
        """
        Get estimated remaining time for current generation.

        Returns:
            Estimated remaining seconds, or 0 if not generating
        """
        task = GenerationStateManager.get_current_task()
        if not task or not task.started_at:
            return 0.0

        elapsed = (datetime.now() - task.started_at).total_seconds()
        remaining = max(0, task.estimated_duration - elapsed)
        return remaining

    @staticmethod
    def get_elapsed_time() -> float:
        """Get elapsed time for current generation."""
        task = GenerationStateManager.get_current_task()
        if not task or not task.started_at:
            return 0.0
        return (datetime.now() - task.started_at).total_seconds()



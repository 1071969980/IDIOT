import asyncio
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, Any

T = TypeVar('T')

class BaseProcessor(Generic[T], ABC):
    """Base processor class with async queue management.

    This class provides a foundation for processing messages asynchronously
    using a queue-based system with context manager support.
    """

    def __init__(self):
        """Initialize the BaseProcessor.

        Args:
            max_size: Maximum size of the message queue
        """
        self._queue: asyncio.Queue[T] = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self._stop_event: asyncio.Event = asyncio.Event()

    async def push_message_until_finished(self, message: T) -> None:
        """Push a message to the queue and wait for processing to finish.

        Args:
            message: The message to process (type T)
        """
        await self.push_message(message)
        await self._queue.join()

    async def push_message(self, message: T) -> None:
        """Push a message to the processing queue.

        Args:
            message: The message to process (type T)

        Returns:
            bool: True if message was queued successfully, False if queue is full
        """
        self._queue.put_nowait(message)

    async def _process_loop(self) -> None:
        """Main processing loop that consumes messages from the queue."""

        while not self._stop_event.is_set():
            # Wait for either queue message or stop event
            get_message_task = asyncio.create_task(self._queue.get())
            wait_task = asyncio.create_task(self._stop_event.wait())

            done, pending = await asyncio.wait(
                [get_message_task, wait_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()

            # If stop event was triggered first, break the loop
            if wait_task in done:
                break

            # Otherwise process the message
            message = get_message_task.result()
            try:
                await self._process_message(message)
            except Exception:
                pass

            self._queue.task_done()

    @abstractmethod
    async def _process_message(self, message: T) -> None:
        """Process a single message. Must be implemented by subclasses.

        Args:
            message: The message to process
        """
        pass

    async def _start_processing(self) -> None:
        """Start the background processing task."""
        if self._processing_task is None or self._processing_task.done():
            self._stop_event.clear()
            self._processing_task = asyncio.create_task(self._process_loop())

    async def _stop_processing(self) -> None:
        """Stop the background processing task."""
        if self._processing_task and not self._processing_task.done():
            self._stop_event.set()
            try:
                await asyncio.wait_for(
                    self._processing_task,
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                self._processing_task.cancel()

            self._processing_task = None

    async def __aenter__(self):
        """Enter the async context manager."""
        await self._start_processing()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the async context manager."""
        await self._stop_processing()

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    @property
    def is_processing(self) -> bool:
        """Check if processing task is active."""
        return self._processing_task is not None and not self._processing_task.done()

    async def drain_queue(self) -> None:
        """Wait for all pending messages to be processed."""
        await self._queue.join()
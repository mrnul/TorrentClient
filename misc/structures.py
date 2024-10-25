import asyncio
from typing import Any


class QueueExt(asyncio.Queue):
    """An extended asyncio.Queue that signals when it's non-empty."""

    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize)
        self.non_empty: asyncio.Event = asyncio.Event()

    def put_nowait(self, item: Any):
        """
        Put an item into the queue without blocking.

        If the queue was empty before, set the non_empty event.
        """
        super().put_nowait(item)
        self.non_empty.set()

    def get_nowait(self) -> Any:
        """
        Get an item from the queue without blocking.

        If the queue becomes empty after this operation, clear the non_empty event.
        """
        item = super().get_nowait()
        if self.qsize() == 0:
            self.non_empty.clear()
        return item


class SetExt(set):
    """An extended set that signals when it becomes empty or non-empty."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.non_empty: asyncio.Event = asyncio.Event()
        self.empty: asyncio.Event = asyncio.Event()


    def _set_events(self):
        """
        Update asyncio.Events depending on the length of the set
        """
        if len(self):
            self.non_empty.set()
            self.empty.clear()
        else:
            self.non_empty.clear()
            self.empty.set()

    def add(self, __element: Any):
        """
        Add an element to the set.

        If the set was empty before, set the non_empty event.
        """
        super().add(__element)
        self._set_events()

    def discard(self, __element: Any):
        """
        Remove an element from the set.

        If the set becomes empty after this operation, set the empty event.
        """
        super().discard(__element)
        self._set_events()

    def difference_update(self, *s):
        """
        Remove all elements of another set from this set.

        If the set becomes empty after this operation, set the empty event.
        """
        super().difference_update(*s)
        self._set_events()

    def update(self, *s):
        """
        Update a set with the union of itself and others.

        If the set was empty before, set the non_empty event.
        """
        super().update(*s)
        self._set_events()

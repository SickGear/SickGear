from __future__ import annotations

import typing
from collections import deque

from .events import Event


class StreamMatrix:
    """Efficient way to store events for concurrent streams."""

    __slots__ = (
        "_matrix",
        "_count",
        "_event_cursor_id",
        "_stream_count",
    )

    def __init__(self) -> None:
        self._matrix: dict[int | None, deque[Event]] = {}
        self._count: int = 0
        self._stream_count: int = 0
        self._event_cursor_id: int = 0

    def __len__(self) -> int:
        return self._count

    def __bool__(self) -> bool:
        return self._count > 0

    @property
    def streams(self) -> list[int]:
        return sorted(i for i in self._matrix if i is not None)

    @property
    def stream_count(self) -> int:
        return self._stream_count

    def append(self, event: Event) -> None:
        matrix_idx = getattr(event, "stream_id", None)

        event._id = self._event_cursor_id
        self._event_cursor_id += 1

        if matrix_idx not in self._matrix:
            self._matrix[matrix_idx] = deque()
            if matrix_idx is not None:
                self._stream_count += 1

        self._matrix[matrix_idx].append(event)

        self._count += 1

    def extend(self, events: typing.Iterable[Event]) -> None:
        triaged_events: dict[int | None, list[Event]] = {}

        for event in events:
            matrix_idx = getattr(event, "stream_id", None)

            event._id = self._event_cursor_id

            self._event_cursor_id += 1
            self._count += 1

            if matrix_idx not in triaged_events:
                triaged_events[matrix_idx] = []

            triaged_events[matrix_idx].append(event)

        for k, v in triaged_events.items():
            if k not in self._matrix:
                self._matrix[k] = deque()
                if k is not None:
                    self._stream_count += 1

            self._matrix[k].extend(v)

    def appendleft(self, event: Event) -> None:
        matrix_idx = getattr(event, "stream_id", None)
        event._id = self._event_cursor_id
        self._event_cursor_id += 1

        if matrix_idx not in self._matrix:
            self._matrix[matrix_idx] = deque()
            if matrix_idx is not None:
                self._stream_count += 1

        self._matrix[matrix_idx].appendleft(event)

        self._count += 1

    def popleft(self, stream_id: int | None = None) -> Event | None:
        if self._count == 0:
            return None

        matrix = self._matrix
        have_global_event: bool = None in matrix and bool(matrix[None])
        any_stream_event: bool = (
            bool(matrix) if not have_global_event else len(matrix) > 1
        )

        if stream_id is None and any_stream_event:
            matrix_dict_iter = matrix.__iter__()

            stream_id = next(matrix_dict_iter)

            if stream_id is None:
                stream_id = next(matrix_dict_iter)

        if (
            stream_id is not None
            and have_global_event
            and stream_id in matrix
            and matrix[None][0]._id < matrix[stream_id][0]._id
        ):
            stream_id = None
        elif have_global_event and stream_id not in matrix:
            stream_id = None

        if stream_id not in matrix:
            return None

        stream = matrix[stream_id]
        ev = stream.popleft()

        if ev is not None:
            self._count -= 1

            if stream_id is not None and not stream:
                del matrix[stream_id]
                self._stream_count -= 1

        return ev

    def count(
        self,
        stream_id: int | None = None,
        excl_event: tuple[type[Event], ...] | None = None,
    ) -> int:
        if stream_id is None:
            return self._count
        if stream_id == -1:
            return 0 if None not in self._matrix else len(self._matrix[None])
        if stream_id not in self._matrix:
            return 0

        return len(
            self._matrix[stream_id]
            if excl_event is None
            else [e for e in self._matrix[stream_id] if not isinstance(e, excl_event)]
        )

    def discard(self, stream_id: int) -> None:
        """Drop a stream's events without consuming connection-level events."""
        events = self._matrix.pop(stream_id, None)
        if events is not None:
            self._count -= len(events)
            self._stream_count -= 1

    def has(
        self,
        stream_id: int | None = None,
        excl_event: tuple[type[Event], ...] | None = None,
    ) -> bool:
        if stream_id is None:
            return self._count > 0
        if stream_id not in self._matrix:
            return False

        if excl_event is not None:
            return any(
                e for e in self._matrix[stream_id] if not isinstance(e, excl_event)
            )

        return bool(self._matrix[stream_id])

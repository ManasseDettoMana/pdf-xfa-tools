"""Job description, progress reporting and cancellation.

The core must stay usable from the CLI, the tests and the GUI, so it cannot
depend on Qt signals.  Instead every long-running operation accepts a small
:class:`JobContext`: it reports progress through a plain callable and checks a
plain callable to find out whether the user asked to stop.  The GUI adapts those
callables to Qt signals in :mod:`xfatools.gui.workers`; the CLI prints to stderr;
the tests pass nothing at all.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .errors import CancelledError

#: ``(completed, total, message)`` - ``total`` may be 0 when it is not known.
ProgressFn = Callable[[int, int, str], None]

#: Returns ``True`` once the user has asked to cancel.
CancelFn = Callable[[], bool]


@dataclass
class JobContext:
    """Progress and cancellation plumbing handed to core operations.

    ``metadata`` is a per-job scratch space: a handler that learns something the
    caller should report - which extraction strategy actually ran, say - leaves
    it here instead of widening the handler signature.  Because every job gets
    its own context, this stays thread-safe.
    """

    on_progress: ProgressFn | None = None
    is_cancelled: CancelFn | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def progress(self, completed: int, total: int = 0, message: str = "") -> None:
        if self.on_progress is not None:
            self.on_progress(completed, total, message)

    def check_cancelled(self) -> None:
        """Raise :class:`CancelledError` if cancellation was requested."""
        if self.is_cancelled is not None and self.is_cancelled():
            raise CancelledError("Operazione annullata dall'utente.")

    @property
    def cancelled(self) -> bool:
        return bool(self.is_cancelled and self.is_cancelled())


#: A context that reports nothing and never cancels - the default everywhere.
NULL_CONTEXT = JobContext()


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class Job:
    """One input file and what the user wants done with it."""

    source: Path
    target_format: str
    options: dict[str, Any] = field(default_factory=dict)
    output_dir: Path | None = None
    status: JobStatus = JobStatus.PENDING

    def __post_init__(self) -> None:
        self.source = Path(self.source)
        if self.output_dir is not None:
            self.output_dir = Path(self.output_dir)

    @property
    def destination_dir(self) -> Path:
        return self.output_dir or self.source.parent


@dataclass
class JobResult:
    """The outcome of running a :class:`Job`."""

    job: Job
    status: JobStatus
    outputs: list[Path] = field(default_factory=list)
    message: str = ""
    hint: str = ""
    warnings: list[str] = field(default_factory=list)
    badge: str = ""
    detail: str = ""
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status is JobStatus.DONE

    @property
    def primary_output(self) -> Path | None:
        return self.outputs[0] if self.outputs else None


class Timer:
    """Context manager measuring wall-clock duration of an operation."""

    def __init__(self) -> None:
        self.elapsed = 0.0
        self._start = 0.0

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info) -> None:
        self.elapsed = time.perf_counter() - self._start


def unique_path(path: Path) -> Path:
    """Return ``path``, or ``name (2).ext`` etc. if it already exists.

    Overwriting a user's file silently is never acceptable, and prompting per
    file would stall a batch, so collisions are resolved by numbering.
    """
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    for counter in range(2, 1000):
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
    raise OSError(f"Impossibile trovare un nome libero per {path}")

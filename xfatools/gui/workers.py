"""Background execution.

Every call into :mod:`xfatools.core` happens on a worker thread.  The UI thread
only ever receives signals, which is what keeps the window responsive while a
300-page OCR run is in flight.

Cancellation is cooperative: a shared :class:`threading.Event` is exposed to the
core through ``JobContext.is_cancelled``, and long loops poll it between pages.
Nothing is killed mid-write, so a cancelled batch never leaves a truncated file.
"""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ..core import registry
from ..core.job import Job, JobContext, JobResult, JobStatus
from ..core.probe import PdfProfile, probe_pdf


class WorkerSignals(QObject):
    """Signals emitted from a worker thread; Qt marshals them to the UI thread.

    Always give this a parent.  Workers hold a reference to it across thread
    boundaries, and an unparented instance can have its C++ side torn down while
    a worker is still running.
    """

    progress = Signal(int, int, int, str)  # token, completed, total, message
    finished = Signal(int, object)  # token, JobResult
    probed = Signal(int, object)  # token, PdfProfile or None


class ConversionWorker(QRunnable):
    """Runs exactly one :class:`Job` and reports the result."""

    def __init__(self, token: int, job: Job, signals: WorkerSignals, cancel: Event) -> None:
        super().__init__()
        self.token = token
        self.job = job
        self.signals = signals
        self._cancel = cancel
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        ctx = JobContext(
            on_progress=lambda done, total, message: self.signals.progress.emit(
                self.token, done, total, message
            ),
            is_cancelled=self._cancel.is_set,
        )
        # run_job never raises: a failure comes back as a JobResult, so one bad
        # file can never take down the pool or strand the queue.
        result = registry.run_job(self.job, ctx)
        self.signals.finished.emit(self.token, result)


class ProbeWorker(QRunnable):
    """Inspects a dropped PDF so the queue can show its detected type."""

    def __init__(self, token: int, path: Path, signals: WorkerSignals) -> None:
        super().__init__()
        self.token = token
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        profile: PdfProfile | None
        try:
            profile = probe_pdf(self.path)
        except Exception:
            # Probing is advisory. A file we cannot inspect still converts, and
            # the queue simply falls back to showing its extension.
            profile = None
        self.signals.probed.emit(self.token, profile)


class JobRunner(QObject):
    """Owns the thread pool and tracks one batch of conversions."""

    job_progress = Signal(int, int, int, str)
    job_finished = Signal(int, object)
    file_probed = Signal(int, object)
    batch_finished = Signal(list)  # list[JobResult]
    batch_progress = Signal(int, int)  # completed, total

    def __init__(self, max_workers: int = 0, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.set_max_workers(max_workers)

        # Parented to the runner so its lifetime is explicit: an unparented
        # QObject can be destroyed while workers still hold a reference to it,
        # and the next emit then fails with "Signal source has been deleted".
        self._signals = WorkerSignals(self)
        self._signals.progress.connect(self.job_progress)
        self._signals.finished.connect(self._on_job_finished)
        self._signals.probed.connect(self.file_probed)

        self._cancel = Event()
        self._pending = 0
        self._total = 0
        self._results: list[JobResult] = []

    # -- configuration ----------------------------------------------------

    def set_max_workers(self, count: int) -> None:
        if count <= 0:
            count = max(1, min(4, os.cpu_count() or 2))
        self.pool.setMaxThreadCount(count)

    @property
    def running(self) -> bool:
        return self._pending > 0

    # -- probing ----------------------------------------------------------

    def probe(self, token: int, path: Path) -> None:
        self.pool.start(ProbeWorker(token, Path(path), self._signals))

    # -- batches ----------------------------------------------------------

    def start(self, jobs: list[tuple[int, Job]]) -> None:
        """Queue a batch. ``jobs`` pairs each row token with its job."""
        if not jobs or self.running:
            return
        self._cancel.clear()
        self._results = []
        self._pending = len(jobs)
        self._total = len(jobs)
        self.batch_progress.emit(0, self._total)
        for token, job in jobs:
            self.pool.start(ConversionWorker(token, job, self._signals, self._cancel))

    def cancel(self) -> None:
        """Ask the batch to stop.

        The pool is deliberately *not* cleared: a dropped worker would never
        emit ``finished``, leaving the batch permanently short of results and
        the UI stuck showing "running".  Instead every queued job still runs,
        sees the cancel flag on its first check and returns immediately, so the
        queue drains in milliseconds and every row gets a final status.
        """
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def wait(self, timeout_ms: int = 5000) -> bool:
        return self.pool.waitForDone(timeout_ms)

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Stop everything and wait for the pool before the window goes away.

        Covers probe workers too, which are not part of a batch and would
        otherwise still be running when Qt tears the object tree down.
        """
        self._cancel.set()
        self.pool.waitForDone(timeout_ms)

    # -- internals --------------------------------------------------------

    def _on_job_finished(self, token: int, result: JobResult) -> None:
        self._results.append(result)
        self.job_finished.emit(token, result)

        self._pending -= 1
        self.batch_progress.emit(self._total - self._pending, self._total)

        if self._pending <= 0:
            self._pending = 0
            self.batch_finished.emit(list(self._results))


def summarise(results: list[JobResult]) -> tuple[int, int, int]:
    """``(succeeded, failed, skipped)`` for a finished batch."""
    ok = sum(1 for r in results if r.status is JobStatus.DONE)
    failed = sum(1 for r in results if r.status is JobStatus.FAILED)
    skipped = sum(
        1 for r in results if r.status in (JobStatus.SKIPPED, JobStatus.CANCELLED)
    )
    return ok, failed, skipped

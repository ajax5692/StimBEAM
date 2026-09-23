import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from django.conf import settings
from django.db import transaction

from .models import AnalysisRun
from .notifications import notify_analysis_completed, notify_analysis_failed


def get_analysis_inputs(analysis_run: AnalysisRun) -> Dict[str, Any]:
    """
    Validate and retrieve input parameters for an AnalysisRun instance.

    Args:
        analysis_run: The AnalysisRun database model instance.

    Returns:
        A dictionary containing validated paths and numerical parameters.

    Raises:
        FileNotFoundError: If the raw .mesc file cannot be found on disk.
        ValueError: If default diameter or tau are less than or equal to zero.
    """
    mesc_file_path = Path(analysis_run.imaging_session.mesc_file_path)

    if not mesc_file_path.exists():
        raise FileNotFoundError(
            f"MESC file does not exist on disk: {mesc_file_path}"
        )

    if analysis_run.default_diameter <= 0:
        raise ValueError("Default diameter must be greater than 0.")

    if analysis_run.tau <= 0:
        raise ValueError("Tau must be greater than 0.")

    return {
        "analysis_run_id": analysis_run.pk,
        "mesc_file_path": str(mesc_file_path),
        "unit_indices": analysis_run.unit_indices,
        "default_diameter": analysis_run.default_diameter,
        "tau": analysis_run.tau,
    }


def build_analysis_command(analysis_run: AnalysisRun, result_file: Path) -> List[str]:
    """
    Construct the CLI command list to execute the Suite2P analysis runner.

    Args:
        analysis_run: The target AnalysisRun model instance.
        result_file: Path where the runner will write its JSON result.

    Returns:
        A list of command-line arguments ready for subprocess invocation.
    """
    inputs = get_analysis_inputs(analysis_run)

    suite2p_python = getattr(settings, "SUITE2P_PYTHON_PATH", "python")
    analysis_runner = getattr(settings, "SUITE2P_RUNNER_SCRIPT", "")

    command = [
        str(suite2p_python),
        "-u",
        str(analysis_runner),
        "--mesc-file",
        inputs["mesc_file_path"],
        "--units",
        *[str(unit) for unit in inputs["unit_indices"]],
        "--diameter",
        str(inputs["default_diameter"]),
        "--tau",
        str(inputs["tau"]),
        "--result-file",
        str(result_file),
    ]

    return command


def run_suite2p_analysis(
    analysis_run: AnalysisRun,
    logger_func: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    Execute Suite2P registration as an isolated subprocess, streaming logs live to the terminal
    matching the exact texts written to the pipeline runlog .txt file.

    Args:
        analysis_run: The target AnalysisRun model instance.
        logger_func: Optional callable to stream log messages to the console.

    Returns:
        Parsed JSON dictionary with output paths and calculated frame rate.

    Raises:
        RuntimeError: If Suite2P exits with a non-zero code or omits result JSON.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        result_file = Path(temp_dir) / "imaging_analysis_result.json"
        command = build_analysis_command(analysis_run, result_file)

        # Enforce unbuffered UTF-8 environment variables so every line prints immediately
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        def emit(msg: str):
            if logger_func:
                logger_func(msg)
            else:
                print(msg, flush=True)

        emit(f"\n[Run #{analysis_run.pk}] Starting Suite2P analysis...")
        emit(f"[Run #{analysis_run.pk}] MESC File: {analysis_run.imaging_session.mesc_file_path}")
        emit(f"[Run #{analysis_run.pk}] Unit Indices: {analysis_run.unit_indices}")
        emit("-" * 60)

        output_lines: List[str] = []

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,
        )

        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                output_lines.append(line)
                emit(line.rstrip("\r\n"))

        process.wait()
        emit("-" * 60)

        if process.returncode != 0:
            error_details = "".join(output_lines).strip() or f"Process exited with code {process.returncode}"
            raise RuntimeError(f"Suite2P analysis failed:\n{error_details}")

        if not result_file.exists():
            raise RuntimeError(
                f"Suite2P completed without producing an analysis result file.\nLog:\n{''.join(output_lines)}"
            )

        result: Dict[str, Any] = json.loads(
            result_file.read_text(encoding="utf-8")
        )

        return result


def execute_analysis(
    analysis_run: AnalysisRun,
    logger_func: Optional[Callable[[str], None]] = None,
) -> AnalysisRun:
    """
    Execute analysis and update AnalysisRun instance fields and status.

    Args:
        analysis_run: The AnalysisRun database instance to process.
        logger_func: Optional callback for streaming live log lines.

    Returns:
        The updated AnalysisRun instance.
    """
    try:
        result = run_suite2p_analysis(analysis_run, logger_func=logger_func)

        analysis_run.frame_rate = round(float(result["frame_rate"]), 2)
        analysis_run.output_log_path = result.get("parameter_log_path", "")
        analysis_run.output_path = result.get("output_path", "")

        analysis_run.save(
            update_fields=[
                "frame_rate",
                "output_log_path",
                "output_path",
            ]
        )

        analysis_run.mark_completed()
        # Trigger Success Notification
        notify_analysis_completed(analysis_run)
        
        # Automatically update the parent ImagingSession to 'Yes'
        session = analysis_run.imaging_session
        if session and session.analysis_performed != "Y":
            session.analysis_performed = "Y"
            session.save(update_fields=["analysis_performed"])

        if logger_func:
            logger_func(f"[Run #{analysis_run.pk}] Detected Frame Rate: {analysis_run.frame_rate} Hz")
            logger_func(f"[Run #{analysis_run.pk}] Output Folder: {analysis_run.output_path}")
            logger_func(f"[Run #{analysis_run.pk}] Full Runlog File: {analysis_run.output_log_path}")

        return analysis_run

    except KeyboardInterrupt:
        shutdown_msg = "Analysis interrupted by user or worker shutdown."
        analysis_run.mark_failed(shutdown_msg)
        # Trigger Failure Notification
        notify_analysis_failed(analysis_run, shutdown_msg)
        raise

    except Exception as exc:
        analysis_run.mark_failed(str(exc))
        # Trigger Failure Notification
        notify_analysis_failed(analysis_run, str(exc))
        raise


def claim_next_pending_analysis(stale_threshold_hours: int = 4) -> Optional[AnalysisRun]:
    """
    Atomically find and claim the oldest pending AnalysisRun using row-level locking.
    Automatically recovers any orphaned runs stuck in RUNNING status past the stale threshold.

    Args:
        stale_threshold_hours: Maximum hours a job may remain RUNNING before being auto-failed.

    Returns:
        The claimed AnalysisRun in RUNNING status, or None if queue is empty.
    """
    with transaction.atomic():
        from datetime import timedelta
        from django.utils import timezone

        stale_cutoff = timezone.now() - timedelta(hours=stale_threshold_hours)
        stale_runs = (
            AnalysisRun.objects
            .select_for_update(skip_locked=True)
            .filter(
                status=AnalysisRun.StatusChoices.RUNNING,
                started_at__lt=stale_cutoff,
            )
        )
        for stale_run in stale_runs:
            stale_run.mark_failed(
                f"Analysis timed out or was interrupted (running longer than {stale_threshold_hours}h)."
            )

        analysis_run = (
            AnalysisRun.objects
            .select_for_update(skip_locked=True)
            .filter(status=AnalysisRun.StatusChoices.PENDING)
            .order_by("created_at")
            .first()
        )

        if analysis_run is None:
            return None

        analysis_run.mark_running()
        return analysis_run


def process_next_analysis(
    logger_func: Optional[Callable[[str], None]] = None,
) -> Optional[AnalysisRun]:
    """
    Claim and execute the next pending analysis job in the queue with live log output.

    Args:
        logger_func: Optional callback for streaming terminal messages.

    Returns:
        The processed AnalysisRun, or None if no pending jobs were found.
    """
    analysis_run = claim_next_pending_analysis()
    if analysis_run is None:
        return None

    execute_analysis(analysis_run, logger_func=logger_func)
    return analysis_run
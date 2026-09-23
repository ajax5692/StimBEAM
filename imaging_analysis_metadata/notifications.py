import logging
import os
import urllib.error
import urllib.request
from typing import Optional

from django.conf import settings

from .models import AnalysisRun

logger = logging.getLogger(__name__)


def send_ntfy_push(
    topic: str,
    message: str,
    title: str = "",
    tags: str = "",
    priority: str = "default",
    server: str = "https://ntfy.sh",
) -> bool:
    """
    Sends an instant push notification via ntfy HTTP API using Python standard library.
    Safe and non-blocking: never raises exceptions to callers.
    """
    base_url = getattr(settings, "NTFY_SERVER", server).rstrip("/")
    url = f"{base_url}/{topic}"
    data = message.encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    if title:
        try:
            title.encode("latin-1")
            req.add_header("Title", title)
        except UnicodeEncodeError:
            from email.header import Header
            req.add_header("Title", Header(title, "utf-8").encode())
    if priority:
        req.add_header("Priority", priority)
    if tags:
        req.add_header("Tags", tags)
        
    token = getattr(settings, "NTFY_AUTH_TOKEN", None)
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as exc:
        logger.warning("Could not dispatch ntfy notification to '%s': %s", topic, exc)
        return False


def notify_analysis_completed(analysis_run: AnalysisRun) -> None:
    """Dispatches a green success alert when Suite2P finishes."""
    try:
        topic = getattr(settings, "NTFY_TOPIC", None)
        if not getattr(settings, "NTFY_ENABLED", False) or not topic:
            return

        # Calculate run duration if timestamps exist
        duration_str = ""
        if analysis_run.started_at and analysis_run.completed_at:
            seconds = int((analysis_run.completed_at - analysis_run.started_at).total_seconds())
            duration_str = f" in {seconds // 60}m {seconds % 60}s"

        body = (
            f"Animal: {analysis_run.animal_id}\n"
            f"Acquisition: {analysis_run.imaging_session.acquisition_date}\n"
            f"Frame Rate: {analysis_run.frame_rate} Hz\n"
            f"Output: {analysis_run.output_path}"
        )

        send_ntfy_push(
            topic=topic,
            title=f"Suite2P Completed: Run #{analysis_run.pk} ({analysis_run.animal_id}){duration_str}",
            message=body,
            tags="microscope,white_check_mark",
            priority="default",
        )
    except Exception as exc:
        logger.warning(
            "Error generating completed notification for Run #%s: %s",
            getattr(analysis_run, "pk", "Unknown"),
            exc,
        )


def notify_analysis_failed(analysis_run: AnalysisRun, error_message: str) -> None:
    """Dispatches a high-priority red alert when Suite2P fails."""
    try:
        topic = getattr(settings, "NTFY_TOPIC", None)
        if not getattr(settings, "NTFY_ENABLED", False) or not topic:
            return

        body = (
            f"Animal: {analysis_run.animal_id}\n"
            f"Acquisition: {analysis_run.imaging_session.acquisition_date}\n"
            f"Error: {error_message[:200]}"
        )

        send_ntfy_push(
            topic=topic,
            title=f"Suite2P Failed: Run #{analysis_run.pk} ({analysis_run.animal_id})",
            message=body,
            tags="warning,x",
            priority="high",
        )
    except Exception as exc:
        logger.warning(
            "Error generating failed notification for Run #%s: %s",
            getattr(analysis_run, "pk", "Unknown"),
            exc,
        )
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict, Union

from django.conf import settings
from django.db import transaction

from .models import TrainingSession
from .training_data_processing.extract_licking import (
    extractLicking_lickTriggeredReward,
)


class TrainingAnalysisMetrics(TypedDict):
    n_trials: int
    trials_with_lick: int
    excluded_trials: int
    length_of_trial: float
    stimulus_onset: float
    stimulus_duration: float
    reward_onset: float
    punish_onset: float
    integral_stimulus: Dict[str, float]
    d_prime: float
    hit_rate: float
    false_alarm_rate: float
    n_go_trials: int
    n_nogo_trials: int
    n_hits: int
    n_misses: int
    n_false_alarms: int
    n_correct_rejections: int
    criterion_c: float


def get_analysis_inputs(training_session: TrainingSession) -> Dict[str, Any]:
    """
    Validate and retrieve analysis inputs from a TrainingSession instance.

    Args:
        training_session: The target TrainingSession model instance.

    Returns:
        Dictionary containing verified file paths, unit range, and animal metadata.

    Raises:
        FileNotFoundError: If the raw Bpod .mat file is missing from disk.
    """
    bpod_file_path = Path(training_session.bpod_file_path)

    if not bpod_file_path.exists():
        raise FileNotFoundError(
            f"BPod session file does not exist on disk: {bpod_file_path}"
        )

    return {
        "training_session_id": training_session.pk,
        "bpod_file_path": str(bpod_file_path),
        "training_unit_range": training_session.training_unit_range,
        "animal_id": training_session.animal.animal_id,
        "training_date": str(training_session.training_date),
    }


def execute_training_analysis(
    training_session: TrainingSession,
    output_dir: Optional[Union[str, Path]] = None,
) -> TrainingSession:
    """
    Execute lick extraction and analysis for a given TrainingSession instance.
    Generates high-res plot figures and exported Excel trace data.

    Args:
        training_session: TrainingSession instance to process.
        output_dir: Optional destination folder. Defaults to media/training_analysis/<animal>/<date>/session_<id>/.

    Returns:
        The updated TrainingSession instance.
    """
    try:
        inputs = get_analysis_inputs(training_session)
        bpod_file = inputs["bpod_file_path"]

        if output_dir is None:
            media_root = getattr(settings, "MEDIA_ROOT", Path(settings.BASE_DIR) / "media")
            output_dir = (
                Path(media_root)
                / "training_analysis"
                / str(inputs["animal_id"])
                / str(inputs["training_date"])
                / f"session_{training_session.pk}"
            )

        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        result = extractLicking_lickTriggeredReward(
            sessionfilename=bpod_file,
            unit_range=inputs.get("training_unit_range"),
            show_plots=False,
            save_plots=True,
            output_dir=str(target_dir),
            export_excel=True,
            smooth_traces=True,
            smooth_window=6500,
            block_plots=False,
        )

        if not result:
            raise RuntimeError("Lick extraction returned empty result.")

        stem = Path(bpod_file).stem
        plot_file = target_dir / f"{stem}_lick_traces.png"
        raster_file = target_dir / f"{stem}_lick_occurrence.png"
        excel_file = target_dir / f"Individual_licking_traces_{stem}.xlsx"

        # Construct relative media URLs or relative paths if under MEDIA_ROOT
        media_root_str = str(getattr(settings, "MEDIA_ROOT", ""))

        def to_relative_media_path(full_path: Path) -> str:
            p = str(full_path)
            if media_root_str and p.startswith(media_root_str):
                rel = os.path.relpath(p, media_root_str).replace("\\", "/")
                return f"{settings.MEDIA_URL.rstrip('/')}/{rel}"
            return p

        training_session.output_plot_path = to_relative_media_path(plot_file) if plot_file.exists() else ""
        training_session.output_raster_path = to_relative_media_path(raster_file) if raster_file.exists() else ""
        training_session.output_excel_path = to_relative_media_path(excel_file) if excel_file.exists() else ""
        training_session.output_log_path = str(target_dir)

        # Copy plots directly to raw input folder
        raw_input_dir = Path(bpod_file).parent
        if raw_input_dir.exists():
            try:
                if plot_file.exists():
                    shutil.copy2(plot_file, raw_input_dir / f"{stem}_lick_traces.png")
                if raster_file.exists():
                    shutil.copy2(raster_file, raw_input_dir / f"{stem}_lick_occurrence.png")
            except Exception as copy_err:
                print(f"Notice: Could not copy plot image to raw input folder {raw_input_dir}: {copy_err}")

        # Store structured metrics (stimulus onset to reward onset integral)
        intgr_stim = {str(k): round(float(v), 4) for k, v in result.get("intgrStimulus", {}).items()}

        metrics: TrainingAnalysisMetrics = {
            "n_trials": int(result.get("nTrials", 0)),
            "trials_with_lick": int(result.get("trialsWithLick", 0)),
            "excluded_trials": int(result.get("excludedTrials", 0)),
            "length_of_trial": round(float(result.get("lengthOfTrial", 0.0)), 2),
            "stimulus_onset": round(float(result.get("stimulus_onset", 0.0)), 2),
            "stimulus_duration": round(float(result.get("stimulus_duration", 0.0)), 2),
            "reward_onset": round(float(result.get("reward_onset", 0.0)), 2),
            "punish_onset": round(float(result.get("punish_onset", 0.0)), 2),
            "integral_stimulus": intgr_stim,
            "d_prime": round(float(result.get("d_prime", 0.0)), 3),
            "hit_rate": round(float(result.get("hit_rate", 0.0)), 4),
            "false_alarm_rate": round(float(result.get("false_alarm_rate", 0.0)), 4),
            "n_go_trials": int(result.get("n_go_trials", 0)),
            "n_nogo_trials": int(result.get("n_nogo_trials", 0)),
            "n_hits": int(result.get("n_hits", 0)),
            "n_misses": int(result.get("n_misses", 0)),
            "n_false_alarms": int(result.get("n_false_alarms", 0)),
            "n_correct_rejections": int(result.get("n_correct_rejections", 0)),
            "criterion_c": round(float(result.get("criterion_c", 0.0)), 3),
        }

        training_session.metrics_json = metrics
        training_session.mark_completed()
        return training_session

    except KeyboardInterrupt:
        training_session.mark_failed("Analysis interrupted by user or worker shutdown.")
        raise

    except Exception as exc:
        training_session.mark_failed(str(exc))
        raise


def claim_next_pending_training_session(stale_threshold_hours: int = 2) -> Optional[TrainingSession]:
    """
    Atomically find and claim the oldest pending TrainingSession using row-level locking.
    Automatically recovers any orphaned sessions stuck in RUNNING status past the stale threshold.

    Args:
        stale_threshold_hours: Maximum hours a session may remain RUNNING before being auto-failed.

    Returns:
        The claimed TrainingSession instance in RUNNING status, or None.
    """
    with transaction.atomic():
        from datetime import timedelta
        from django.utils import timezone

        stale_cutoff = timezone.now() - timedelta(hours=stale_threshold_hours)
        stale_sessions = (
            TrainingSession.objects
            .select_for_update(skip_locked=True)
            .filter(
                status=TrainingSession.StatusChoices.RUNNING,
                started_at__lt=stale_cutoff,
            )
        )
        for stale_s in stale_sessions:
            stale_s.mark_failed(
                f"Training analysis timed out or was interrupted (running longer than {stale_threshold_hours}h)."
            )

        session = (
            TrainingSession.objects
            .select_for_update(skip_locked=True)
            .filter(status=TrainingSession.StatusChoices.PENDING)
            .order_by("created_at")
            .first()
        )

        if session is None:
            return None

        session.mark_running()
        return session


def process_next_training_analysis() -> Optional[TrainingSession]:
    """
    Fetch and execute the next pending training analysis job.

    Returns:
        The processed TrainingSession, or None if no pending jobs were found.
    """
    session = claim_next_pending_training_session()
    if session is None:
        return None

    execute_training_analysis(session)
    return session
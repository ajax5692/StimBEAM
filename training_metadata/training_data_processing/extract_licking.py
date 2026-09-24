"""
Extracts, corrects, aligns, and analyzes lick port data from Bpod SessionData files
for lick-triggered reward protocols (Visual Go / No-Go tasks).

Supports restricting analysis to user-specified training unit/trial ranges and customizable plot styles.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict, Union

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import pandas as pd
import scipy.io as sio
from scipy.signal import windows
from scipy.stats import norm


DEFAULT_PLOT_STYLE: Dict[str, Any] = {
    "figsize": (10, 6),
    "dpi": 300,
    "go_color": "#006837",
    "nogo_color": "#d73027",
    "stimulus_color": "#cccccc",
    "stimulus_alpha": 0.8,
    "reward_color": "#777777",
    "punish_color": "darkgray",
    "raster_linewidth": 1.2,
    "trace_linewidth": 2.0,
    "font_size_label": 11,
    "font_size_title": 12,
    "font_size_legend": 10,
}


class ExtractionResult(TypedDict):
    sessionfilename: str
    nTrials: int
    trialsWithLick: int
    excludedTrials: int
    lengthOfTrial: float
    time_axis: npt.NDArray[np.float64]
    Ylicktr: npt.NDArray[np.float64]
    Ylicktr_avg: Dict[int, npt.NDArray[np.float64]]
    Excluded: npt.NDArray[np.bool_]
    intgrStimulus: Dict[int, float]
    stimulus_onset: float
    stimulus_duration: float
    reward_onset: float
    punish_onset: float
    figures: List[plt.Figure]
    unit_range: Optional[str]
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


from animals_metadata.utils import parse_unit_ranges
from .bpod_io import (
    _get_field,
    _has_field,
    _integrate_trapz,
    _to_1d_array,
    _to_2d_array,
    determine_session_timing,
    load_bpod_session,
)


def extract_trial_lick_matrix(
    session_data: Any,
    time_axis: npt.NDArray[np.float64],
    selected_trials: Set[int],
) -> Tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_], int, Dict[int, npt.NDArray[np.float64]]]:
    """
    Extract individual lick event timestamps and populate the high-resolution binary matrix
    strictly for the specified unit/trial range.

    Args:
        session_data: Bpod SessionData object.
        time_axis: 1D array of 0.1ms time increments.
        selected_trials: Set of 1-based trial indices to process.

    Returns:
        Tuple of (Ylicktr, Excluded, trialsWithLick, trial_lick_events).
    """
    n_trials = int(session_data.nTrials)
    y_lick_matrix = np.zeros((n_trials, len(time_axis)), dtype=np.float64)
    excluded = np.zeros(n_trials, dtype=bool)
    trials_with_lick = 0
    trial_lick_events: Dict[int, npt.NDArray[np.float64]] = {}

    for i in range(n_trials):
        trial_num = i + 1

        # If trial is outside the user-specified unit range, exclude it from analysis
        if trial_num not in selected_trials:
            excluded[i] = True
            continue

        trial = session_data.RawEvents.Trial[i]
        states = trial.States
        events = trial.Events

        if _has_field(states, "WaitingForTrigger_Start"):
            wfts = _to_1d_array(_get_field(states, "WaitingForTrigger_Start"))
            trial_lag = float(wfts[1]) if len(wfts) > 1 else 0.0
            end_of_trial = _to_1d_array(_get_field(states, "StillDrinking"))
            if len(end_of_trial) == 0:
                end_of_trial = _to_1d_array(_get_field(states, "ITI"))
        elif _has_field(states, "WaitingForTrigger"):
            wft = _to_1d_array(_get_field(states, "WaitingForTrigger"))
            trial_lag = float(wft[1]) if len(wft) > 1 else 0.0
            end_of_trial = _to_1d_array(_get_field(states, "StillDrinking"))
            if len(end_of_trial) == 0:
                end_of_trial = _to_1d_array(_get_field(states, "ITI"))
        elif _has_field(states, "InitialDelay"):
            init_delay = _to_2d_array(_get_field(states, "InitialDelay"))
            trial_lag = float(init_delay[-1, 0]) if init_delay.size > 0 else 0.0
            end_of_trial = _to_1d_array(_get_field(states, "ITI"))
            if len(end_of_trial) == 0:
                end_of_trial = _to_1d_array(_get_field(states, "StillDrinking"))
        else:
            trial_lag = 0.0
            end_of_trial = np.array([0.0, 0.0], dtype=np.float64)

        if not _has_field(events, "Port1In"):
            continue

        port_in = list(_to_1d_array(_get_field(events, "Port1In")))
        if len(port_in) == 0:
            continue

        trials_with_lick += 1

        if _has_field(events, "Port1Out"):
            port_out = list(_to_1d_array(_get_field(events, "Port1Out")))
        else:
            if len(port_in) == 1 and len(end_of_trial) > 0 and port_in[0] >= end_of_trial[0]:
                port_out = [float(end_of_trial[-1])]
            else:
                excluded[i] = True
                continue

        corr_one_needed = False
        if len(port_in) > 0 and len(port_out) > 0 and port_in[0] > port_out[0]:
            if len(port_out) > 1:
                port_out.pop(0)
            elif len(port_out) == 1:
                corr_one_needed = True

        if len(port_in) > 0 and len(port_out) > 0 and port_in[-1] > port_out[-1]:
            if len(end_of_trial) > 0:
                port_out.append(float(end_of_trial[-1]))

        if corr_one_needed and len(port_out) > 0:
            port_out.pop(0)

        if len(port_in) != len(port_out) or len(port_in) == 0:
            excluded[i] = True
            continue

        if not all(p_in < p_out for p_in, p_out in zip(port_in, port_out)):
            excluded[i] = True
            continue

        licks = np.array(port_in, dtype=np.float64) - trial_lag
        licks_out = np.array(port_out, dtype=np.float64) - trial_lag

        valid_mask = licks >= 0
        licks = licks[valid_mask]
        licks_out = licks_out[valid_mask]

        if len(licks) == 0:
            trials_with_lick -= 1
            continue

        trial_lick_events[i] = licks

        y = np.zeros(len(time_axis), dtype=np.float64)
        for k in range(len(licks)):
            i1 = int(np.round(licks[k] * 1e4))
            i2 = int(np.round(licks_out[k] * 1e4))
            i1 = max(0, min(i1, len(time_axis) - 1))
            i2 = max(0, min(i2, len(time_axis) - 1))
            if i2 >= i1:
                y[i1 : i2 + 1] = 1.0

        y_lick_matrix[i, :] = y

    return y_lick_matrix, excluded, trials_with_lick, trial_lick_events


def compute_smoothed_averages_and_integrals(
    y_lick_matrix: npt.NDArray[np.float64],
    trial_types_raw: npt.NDArray[np.int_],
    excluded: npt.NDArray[np.bool_],
    max_trial_type: int,
    time_axis: npt.NDArray[np.float64],
    smooth_traces: bool,
    smooth_window: int,
    so: float,
    ro: float,
) -> Tuple[Dict[int, npt.NDArray[np.float64]], Dict[int, float], float]:
    """
    Compute trial-averaged lick envelopes, apply Gaussian convolution, and calculate stimulus integrals
    strictly over the included (non-excluded) trials within the unit range.
    """
    gw = windows.gaussian(smooth_window, std=(smooth_window - 1) / 5.0)
    gw = gw / np.sum(gw)

    intgr_stimulus: Dict[int, float] = {}
    y_lick_avg: Dict[int, npt.NDArray[np.float64]] = {}
    max_ampl = 0.0

    for tt in range(1, max_trial_type + 1):
        type_mask = (trial_types_raw == tt) & (~excluded)
        if np.any(type_mask):
            subset = y_lick_matrix[type_mask, :]
            y_mean = np.mean(subset, axis=0) if subset.shape[0] > 1 else subset[0, :]
            if smooth_traces:
                ygf = np.convolve(y_mean, gw, mode="same")
                y_lick_avg[tt] = ygf
                intgr_stimulus[tt] = _integrate_trapz(time_axis, ygf, so, ro)
            else:
                y_lick_avg[tt] = y_mean
                intgr_stimulus[tt] = _integrate_trapz(time_axis, y_mean, so, ro)

            if np.max(y_lick_avg[tt]) > max_ampl:
                max_ampl = float(np.max(y_lick_avg[tt]))

    return y_lick_avg, intgr_stimulus, max_ampl


def compute_signal_detection_metrics(
    trial_types_raw: npt.NDArray[np.int_],
    selected_indices: List[int],
    excluded: npt.NDArray[np.bool_],
    session_data: Any,
    trial_lick_events: Dict[int, npt.NDArray[np.float64]],
    so: float,
    ro: float,
) -> Dict[str, Any]:
    """
    Calculate Signal Detection Theory metrics: d' (sensitivity index), Criterion c,
    Hit Rate, and False Alarm Rate for visual Go vs. No-Go discrimination tasks.

    Uses the standard Hautus (1995) log-linear adjustment for extreme rates (0 or 1):
        HitRate_adj = (Hits + 0.5) / (n_go + 1)
        FARate_adj = (FAs + 0.5) / (n_nogo + 1)
        d' = Z(HitRate_adj) - Z(FARate_adj)
        c = -0.5 * (Z(HitRate_adj) + Z(FARate_adj))
    """
    trial_outcomes_raw = _to_1d_array(_get_field(session_data, "TrialOutcomes")).astype(int)
    has_outcomes = len(trial_outcomes_raw) > 0

    hits = 0
    misses = 0
    fas = 0
    crs = 0
    n_go = 0
    n_nogo = 0

    response_end = max(ro, so + 1.0) if ro > 0 else (so + 2.0)

    for i in selected_indices:
        if excluded[i]:
            continue

        tt = int(trial_types_raw[i]) if i < len(trial_types_raw) else 0

        if tt == 1:  # Visual Go stimulus
            n_go += 1
            if has_outcomes and i < len(trial_outcomes_raw):
                # In Bpod Visual Go/NoGo protocol: outcome 1 = Hit, outcome 0 = Miss
                outcome = trial_outcomes_raw[i]
                if outcome == 1:
                    hits += 1
                else:
                    misses += 1
            else:
                licks = trial_lick_events.get(i, np.array([], dtype=np.float64))
                licked = np.any((licks >= so) & (licks <= response_end))
                if licked:
                    hits += 1
                else:
                    misses += 1

        elif tt == 2:  # Visual No-Go stimulus
            n_nogo += 1
            if has_outcomes and i < len(trial_outcomes_raw):
                # In Bpod Visual Go/NoGo protocol: outcome 2 = False Alarm, outcome 3 = Correct Rejection
                outcome = trial_outcomes_raw[i]
                if outcome == 2:
                    fas += 1
                else:
                    crs += 1
            else:
                licks = trial_lick_events.get(i, np.array([], dtype=np.float64))
                licked = np.any((licks >= so) & (licks <= response_end))
                if licked:
                    fas += 1
                else:
                    crs += 1

    # Raw empirical rates
    raw_hit_rate = round(hits / n_go, 4) if n_go > 0 else 0.0
    raw_fa_rate = round(fas / n_nogo, 4) if n_nogo > 0 else 0.0

    # Hautus (1995) log-linear adjustment for normal quantile conversion
    adj_hit_rate = (hits + 0.5) / (n_go + 1) if n_go > 0 else 0.5
    adj_fa_rate = (fas + 0.5) / (n_nogo + 1) if n_nogo > 0 else 0.5

    z_hit = float(norm.ppf(adj_hit_rate))
    z_fa = float(norm.ppf(adj_fa_rate))

    d_prime = round(float(z_hit - z_fa), 3)
    criterion_c = round(float(-0.5 * (z_hit + z_fa)), 3)

    return {
        "d_prime": d_prime,
        "hit_rate": raw_hit_rate,
        "false_alarm_rate": raw_fa_rate,
        "n_go_trials": n_go,
        "n_nogo_trials": n_nogo,
        "n_hits": hits,
        "n_misses": misses,
        "n_false_alarms": fas,
        "n_correct_rejections": crs,
        "criterion_c": criterion_c,
    }


def generate_lick_figures(
    sessionfilename: str,
    time_axis: npt.NDArray[np.float64],
    length_of_trial: float,
    n_trials: int,
    trial_types_raw: npt.NDArray[np.int_],
    excluded: npt.NDArray[np.bool_],
    trial_lick_events: Dict[int, npt.NDArray[np.float64]],
    y_lick_avg: Dict[int, npt.NDArray[np.float64]],
    max_trial_type: int,
    max_ampl: float,
    vis_stim_start: float,
    vis_stim_end: float,
    so: float,
    ro: float,
    po: float,
    save_plots: bool,
    output_dir: Optional[Union[str, Path]],
    show_plots: bool,
    block_plots: bool,
    unit_range_label: Optional[str] = None,
    plot_style: Optional[Dict[str, Any]] = None,
) -> List[plt.Figure]:
    """
    Render and optionally save raster plot and average licking trace figures.
    """
    style = {**DEFAULT_PLOT_STYLE, **(plot_style or {})}
    figs: List[plt.Figure] = []
    filename_base = os.path.basename(sessionfilename)

    color_go = style.get("go_color", "#006837")
    color_nogo = style.get("nogo_color", "#d73027")
    stim_color = style.get("stimulus_color", "#cccccc")
    stim_alpha = style.get("stimulus_alpha", 0.8)
    reward_color = style.get("reward_color", "#777777")
    punish_color = style.get("punish_color", "darkgray")
    raster_lw = style.get("raster_linewidth", 1.2)
    trace_lw = style.get("trace_linewidth", 2.0)
    fig_size = style.get("figsize", (10, 6))
    plot_dpi = style.get("dpi", 300)

    # Color palette
    tp = np.array([
        [0.0, 0.4, 0.2],    # Go
        [0.85, 0.2, 0.15],  # No-Go
    ])
    if max_trial_type > 2:
        extra_colors = plt.cm.tab10(np.linspace(0, 1, max_trial_type))[:, :3]
        tp = np.vstack([tp, extra_colors[2:]])

    range_suffix = f" (Units {unit_range_label})" if unit_range_label else ""

    # FIGURE 1: Raster Plot
    fig1, ax1 = plt.subplots(figsize=fig_size)
    if hasattr(fig1.canvas, "manager") and fig1.canvas.manager:
        fig1.canvas.manager.set_window_title(f"licks occurrence file: {filename_base}")

    ax1.axvspan(vis_stim_start, vis_stim_end, color=stim_color, alpha=stim_alpha, label="Video", zorder=0)
    if ro > 0:
        ax1.axvline(ro, color=reward_color, linestyle="--", linewidth=1.5, label="Reward", zorder=1)
    if po > 0:
        ax1.axvline(po, color=punish_color, linestyle="--", linewidth=1.5, label="Punishment", zorder=1)

    lgnd_plotted = set()
    for i in range(n_trials):
        if i in trial_lick_events and not excluded[i]:
            tt = trial_types_raw[i]
            color = color_go if tt == 1 else (color_nogo if tt == 2 else (tp[tt - 1] if tt <= len(tp) else "blue"))
            label = ("Go trials" if tt == 1 else "NoGo trials") if tt not in lgnd_plotted else None
            if label:
                lgnd_plotted.add(tt)
            ax1.vlines(trial_lick_events[i], ymin=0, ymax=1, color=color, linewidth=raster_lw, label=label, zorder=2)

    ax1.set_ylim(0, 3)
    ax1.set_xlim(0, max(length_of_trial, 1.0))
    ax1.set_ylabel("Licking", fontsize=style.get("font_size_label", 11))
    ax1.set_xlabel("Time (s)", fontsize=style.get("font_size_label", 11))
    clean_stem = Path(sessionfilename).stem.replace("_", " ")
    ax1.set_title(f"Lick Occurrences - {clean_stem}{range_suffix}", fontsize=style.get("font_size_title", 12), fontweight="bold")
    ax1.legend(loc="upper right", frameon=False, fontsize=style.get("font_size_legend", 10))
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.tick_params(direction="out")
    figs.append(fig1)

    # FIGURE 2: Averaged Licking Traces
    fig2, ax2 = plt.subplots(figsize=fig_size)
    if hasattr(fig2.canvas, "manager") and fig2.canvas.manager:
        fig2.canvas.manager.set_window_title(f"licks traces file: {filename_base}")

    n_go = int(np.sum((trial_types_raw == 1) & (~excluded)))
    n_nogo = int(np.sum((trial_types_raw == 2) & (~excluded)))

    ax2.axvspan(vis_stim_start, vis_stim_end, color=stim_color, alpha=stim_alpha, label="Video", zorder=0)
    if ro > 0:
        ax2.axvline(ro, color=reward_color, linestyle="--", linewidth=1.5, label="Reward", zorder=1)
    if po > 0:
        ax2.axvline(po, color=punish_color, linestyle="--", linewidth=1.5, label="Punishment", zorder=1)

    if 1 in y_lick_avg:
        ax2.plot(time_axis, y_lick_avg[1], color=color_go, linewidth=trace_lw, label=f"Go trials (={n_go})", zorder=3)
    if 2 in y_lick_avg:
        ax2.plot(time_axis, y_lick_avg[2], color=color_nogo, linewidth=trace_lw, label=f"NoGo trials (={n_nogo})", zorder=3)

    for tt in range(3, max_trial_type + 1):
        if tt in y_lick_avg:
            ax2.plot(time_axis, y_lick_avg[tt], linewidth=trace_lw, label=f"Trial type {tt}", zorder=3)

    x_max_view = 20.0 if length_of_trial >= 18.0 else max(length_of_trial, 1.0)
    ax2.set_xlim(0, x_max_view)
    ax2.set_xticks(np.arange(0, x_max_view + 1, 5))

    y_max_view = 0.30 if max_ampl <= 0.295 else float(np.ceil(max_ampl * 10) / 10)
    ax2.set_ylim(0, y_max_view)
    ax2.set_yticks(np.arange(0, y_max_view + 0.01, 0.05))

    ax2.set_ylabel("Licking", fontsize=style.get("font_size_label", 11))
    ax2.set_xlabel("Time (s)", fontsize=style.get("font_size_label", 11))
    ax2.set_title(f"Average licking trace - {clean_stem}{range_suffix}", fontsize=style.get("font_size_title", 12), fontweight="bold")
    ax2.legend(loc="upper right", frameon=False, fontsize=style.get("font_size_legend", 10))
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.tick_params(direction="out")
    figs.append(fig2)

    if save_plots and output_dir:
        os.makedirs(output_dir, exist_ok=True)
        stem = Path(sessionfilename).stem
        fig1.savefig(os.path.join(output_dir, f"{stem}_lick_occurrence.png"), dpi=plot_dpi, bbox_inches="tight")
        fig2.savefig(os.path.join(output_dir, f"{stem}_lick_traces.png"), dpi=plot_dpi, bbox_inches="tight")

    if show_plots:
        plt.show(block=block_plots)

    return figs


def export_licking_traces_excel(
    sessionfilename: str,
    time_axis: npt.NDArray[np.float64],
    y_lick_matrix: npt.NDArray[np.float64],
    selected_trials: List[int],
    output_dir: Optional[Union[str, Path]] = None,
    step: int = 500,
) -> Path:
    """
    Export downsampled trial-by-trial licking arrays for the selected units to Excel (.xlsx).
    """
    target_dir = Path(output_dir) if output_dir else Path(sessionfilename).parent
    target_dir.mkdir(parents=True, exist_ok=True)
    xls_path = target_dir / f"Individual_licking_traces_{Path(sessionfilename).stem}.xlsx"

    x_down = time_axis[::step]
    data_dict: Dict[str, Any] = {"t": x_down}

    for trial_num in selected_trials:
        idx = trial_num - 1
        data_dict[f"Trial_{trial_num}"] = y_lick_matrix[idx, ::step]

    df_export = pd.DataFrame(data_dict)
    df_export.to_excel(xls_path, index=False)
    print(f"Licking data exported to: {xls_path}")
    return xls_path


def extractLicking_lickTriggeredReward(
    sessionfilename: Optional[Union[str, Path]] = None,
    unit_range: Optional[Union[str, List[int], range, Set[int]]] = None,
    show_plots: bool = True,
    save_plots: bool = False,
    output_dir: Optional[Union[str, Path]] = None,
    export_excel: bool = False,
    smooth_traces: bool = True,
    smooth_window: int = 6500,
    block_plots: bool = True,
    start_trial: int = 1,
    plot_style: Optional[Dict[str, Any]] = None,
) -> Optional[ExtractionResult]:
    """
    Extract, align, smooth, and analyze licking kinematics from a Bpod session file,
    restricted strictly to the specified training unit/trial range.

    Args:
        sessionfilename: Path to the .mat Bpod session file.
        unit_range: Specified unit range (e.g. '10:21,25:55' or '3:174'). If None, all trials are analyzed.
        show_plots: Display interactive matplotlib plot windows.
        save_plots: Save high-resolution PNG plots to output_dir.
        output_dir: Destination folder for plots and Excel exports.
        export_excel: Export downsampled licking matrices to .xlsx.
        smooth_traces: Apply Gaussian convolution to averaged licking traces.
        smooth_window: Gaussian smoothing kernel size in time steps (default: 6500 = 0.65s).
        block_plots: Keep matplotlib windows open interactively.
        start_trial: Optional minimum trial index fallback (default: 1).
        plot_style: Optional dictionary overriding default colors, DPI, or figure dimensions.

    Returns:
        ExtractionResult dictionary containing summary metrics, traces, and figures.
    """
    if sessionfilename is None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            sessionfilename = filedialog.askopenfilename(
                title="Select the Bpod file",
                filetypes=[("MATLAB Files", "*.mat"), ("All Files", "*.*")],
            )
            root.destroy()
        except Exception:
            raise ValueError("No sessionfilename provided and GUI file picker unavailable.")

    if not sessionfilename:
        print("No file selected.")
        return None

    sessionfilename_str = str(sessionfilename)
    session_data = load_bpod_session(sessionfilename_str)

    total_session_trials = int(session_data.nTrials)
    trial_types_raw = _to_1d_array(session_data.TrialTypes).astype(int)
    max_trial_type = int(np.max(trial_types_raw)) if len(trial_types_raw) > 0 else 1

    # Parse and validate selected unit range
    parsed_units = parse_unit_ranges(unit_range)
    if parsed_units:
        valid_selected_trials = [t for t in parsed_units if 1 <= t <= total_session_trials]
        unit_range_label = str(unit_range).strip()
    else:
        valid_selected_trials = list(range(1, total_session_trials + 1))
        unit_range_label = None

    if not valid_selected_trials:
        valid_selected_trials = list(range(1, total_session_trials + 1))
        unit_range_label = None

    selected_trials_set = set(valid_selected_trials)
    n_selected_trials = len(valid_selected_trials)

    (
        length_of_trial,
        so,
        so2,
        ro,
        po,
        vis_stim_start,
        vis_stim_end,
    ) = determine_session_timing(session_data, selected_trials=valid_selected_trials)

    dt = 0.0001
    x = np.arange(0, length_of_trial + dt, dt, dtype=np.float64)

    y_lick_matrix, excluded, trials_with_lick, trial_lick_events = extract_trial_lick_matrix(
        session_data=session_data,
        time_axis=x,
        selected_trials=selected_trials_set,
    )

    y_lick_avg, intgr_stimulus, max_ampl = compute_smoothed_averages_and_integrals(
        y_lick_matrix=y_lick_matrix,
        trial_types_raw=trial_types_raw,
        excluded=excluded,
        max_trial_type=max_trial_type,
        time_axis=x,
        smooth_traces=smooth_traces,
        smooth_window=smooth_window,
        so=so,
        ro=ro,
    )

    # Calculate excluded count within the selected unit range
    selected_indices = [t - 1 for t in valid_selected_trials]
    excluded_in_selection = int(np.sum(excluded[selected_indices]))

    # Signal Detection Theory analysis (d', Hit Rate, False Alarm Rate)
    sdt_metrics = compute_signal_detection_metrics(
        trial_types_raw=trial_types_raw,
        selected_indices=selected_indices,
        excluded=excluded,
        session_data=session_data,
        trial_lick_events=trial_lick_events,
        so=so,
        ro=ro,
    )

    filename_base = os.path.basename(sessionfilename_str)
    print("\n" + "=" * 60)
    print(f"File: {filename_base}")
    if unit_range_label:
        print(f"Selected Unit Range: {unit_range_label} ({n_selected_trials} trials)")
    print(f"Number of analyzed trials: {n_selected_trials} trials")
    print(f"Licked in: {trials_with_lick - excluded_in_selection} trials")
    print(f"No lick in: {n_selected_trials - trials_with_lick} trials")
    print(f"Excluded trials: {excluded_in_selection}")
    print("-" * 60)
    for tt in intgr_stimulus:
        label = "go trial" if tt == 1 else "no-go trial"
        print(f"Integral Stimulus period ({so:.2f}s to {ro:.2f}s), {label} (type {tt}) curve: {intgr_stimulus[tt]:.3f}")
    if sdt_metrics["n_go_trials"] > 0 or sdt_metrics["n_nogo_trials"] > 0:
        print(
            f"Sensitivity (d'): {sdt_metrics['d_prime']:.3f} | Criterion (c): {sdt_metrics['criterion_c']:.3f}\n"
            f"Hit Rate: {sdt_metrics['hit_rate'] * 100:.1f}% ({sdt_metrics['n_hits']}/{sdt_metrics['n_go_trials']}) | "
            f"False Alarm Rate: {sdt_metrics['false_alarm_rate'] * 100:.1f}% ({sdt_metrics['n_false_alarms']}/{sdt_metrics['n_nogo_trials']})"
        )
    print("=" * 60 + "\n")

    figs: List[plt.Figure] = []
    if show_plots or save_plots:
        figs = generate_lick_figures(
            sessionfilename=sessionfilename_str,
            time_axis=x,
            length_of_trial=length_of_trial,
            n_trials=total_session_trials,
            trial_types_raw=trial_types_raw,
            excluded=excluded,
            trial_lick_events=trial_lick_events,
            y_lick_avg=y_lick_avg,
            max_trial_type=max_trial_type,
            max_ampl=max_ampl,
            vis_stim_start=vis_stim_start,
            vis_stim_end=vis_stim_end,
            so=so,
            ro=ro,
            po=po,
            save_plots=save_plots,
            output_dir=output_dir,
            show_plots=show_plots,
            block_plots=block_plots,
            unit_range_label=unit_range_label,
            plot_style=plot_style,
        )

    if export_excel:
        export_licking_traces_excel(
            sessionfilename=sessionfilename_str,
            time_axis=x,
            y_lick_matrix=y_lick_matrix,
            selected_trials=valid_selected_trials,
            output_dir=output_dir,
        )

    return {
        "sessionfilename": sessionfilename_str,
        "nTrials": n_selected_trials,
        "trialsWithLick": trials_with_lick,
        "excludedTrials": excluded_in_selection,
        "lengthOfTrial": length_of_trial,
        "time_axis": x,
        "Ylicktr": y_lick_matrix,
        "Ylicktr_avg": y_lick_avg,
        "Excluded": excluded,
        "intgrStimulus": intgr_stimulus,
        "stimulus_onset": so,
        "stimulus_duration": so2,
        "reward_onset": ro,
        "punish_onset": po,
        "figures": figs,
        "unit_range": unit_range_label,
        **sdt_metrics,
    }


if __name__ == "__main__":
    if len(sys.argv) > 2:
        extractLicking_lickTriggeredReward(sys.argv[1], unit_range=sys.argv[2], show_plots=True)
    elif len(sys.argv) > 1:
        extractLicking_lickTriggeredReward(sys.argv[1], show_plots=True)
    else:
        extractLicking_lickTriggeredReward()

import json
from datetime import date
from typing import Any, Dict, List, Optional

from django.apps import apps
from django.utils import timezone

from animals_metadata.models import Animal, ViralInjection, VisionCheck


class MouseTrackerService:
    """
    Service layer providing data aggregation, colony metrics calculation,
    and profile serialization for the Laboratory Dashboard & Mouse Tracker.
    """

    PIPELINE_STAGES = (
        "Intake",
        "Vision Check",
        "Virus Injection",
        "Surgery",
        "Behavior Training",
        "Finished",
        "Culled",
    )

    @classmethod
    def preload_colony_data(cls) -> Dict[str, Any]:
        """
        Pre-fetch related records across installed optional apps to avoid N+1 queries.
        """
        has_training = apps.is_installed("training_metadata")
        has_imaging = apps.is_installed("imaging_metadata")

        body_weights_by_animal: Dict[int, Dict[str, Any]] = {}
        training_by_animal: Dict[int, List[Any]] = {}
        if has_training:
            try:
                from training_metadata.models import MouseBodyWeight, TrainingSession

                trackers = MouseBodyWeight.objects.prefetch_related("entries").all()
                for t in trackers:
                    body_weights_by_animal[t.animal_id] = {
                        "tracker": t,
                        "water_start": t.water_restriction_start_date,
                        "entries": list(t.entries.all().order_by("date", "id")),
                    }
                ts_qs = TrainingSession.objects.all().order_by("-training_date")
                for ts in ts_qs:
                    training_by_animal.setdefault(ts.animal_id, []).append(ts)
            except Exception:
                pass

        vision_by_animal: Dict[int, List[VisionCheck]] = {}
        for vc in VisionCheck.objects.all().order_by("-id"):
            vision_by_animal.setdefault(vc.animal_id_id, []).append(vc)

        virus_by_animal: Dict[int, List[ViralInjection]] = {}
        for vi in (
            ViralInjection.objects.select_related(
                "virus_id", "virus_id_2", "virus_id_3", "injecting_person", "surgery_person"
            )
            .all()
            .order_by("-injection_date")
        ):
            virus_by_animal.setdefault(vi.animal_id_id, []).append(vi)

        imaging_by_animal: Dict[int, List[Any]] = {}
        if has_imaging:
            try:
                from imaging_metadata.models import ImagingSession

                ims_qs = (
                    ImagingSession.objects.prefetch_related("analysis_runs")
                    .all()
                    .order_by("-acquisition_date")
                )
                for im in ims_qs:
                    imaging_by_animal.setdefault(im.animal_id, []).append(im)
            except Exception:
                pass

        return {
            "body_weights": body_weights_by_animal,
            "training": training_by_animal,
            "vision": vision_by_animal,
            "virus": virus_by_animal,
            "imaging": imaging_by_animal,
        }

    @classmethod
    def is_animal_active(cls, animal: Animal) -> bool:
        """
        Check if an animal is considered active (alive and not finished/culled).
        """
        return (
            animal.status != Animal.StatusChoices.DEAD
            and animal.status not in ["Dead", "Culled"]
            and animal.pipeline_stage
            not in [
                Animal.PipelineStageChoices.FINISHED,
                Animal.PipelineStageChoices.CULLED,
                "Finished",
                "Culled",
                "Dead",
            ]
        )

    @classmethod
    def is_animal_water_restricted(cls, animal: Animal, is_active: bool) -> bool:
        """
        An animal is water-restricted strictly if it is currently active AND in Behavior Training.
        """
        return is_active and (
            animal.pipeline_stage
            in [Animal.PipelineStageChoices.BEHAVIOR_TRAINING, "Behavior Training"]
        )

    @classmethod
    def calculate_restriction_string(
        cls,
        is_water_restricted: bool,
        water_start: Optional[date],
        today: date,
    ) -> str:
        """
        Format the descriptive water restriction string.
        """
        if is_water_restricted:
            if water_start:
                days_diff = (today - water_start).days + 1
                if days_diff >= 1:
                    return f"Day {days_diff} (Since {water_start})"
                return f"Starts {water_start}"
            return "Active Training (Date not set)"
        elif water_start:
            return f"Not on restriction (Prior start: {water_start})"
        return "Not on restriction"

    @classmethod
    def build_animal_profile(
        cls,
        animal: Animal,
        preloaded: Dict[str, Any],
        today: date,
    ) -> Dict[str, Any]:
        """
        Assemble the complete JSON-serializable profile dictionary for a single animal.
        """
        bw_data = preloaded["body_weights"].get(animal.id, {})
        entries = bw_data.get("entries", [])
        water_start = bw_data.get("water_start")

        baseline_weight = entries[0].body_weight_g if entries else None
        latest_entry = entries[-1] if entries else None
        latest_weight = latest_entry.body_weight_g if latest_entry else None
        latest_pct = latest_entry.percent_body_weight if latest_entry else None

        is_active = cls.is_animal_active(animal)
        is_water_restricted = cls.is_animal_water_restricted(animal, is_active)
        weighed_today = bool(entries and entries[-1].date == today)
        restriction_day_str = cls.calculate_restriction_string(
            is_water_restricted, water_start, today
        )

        weights_list = [
            {
                "date": str(e.date),
                "weight_g": e.body_weight_g,
                "pct": e.percent_body_weight,
                "notes": "",
            }
            for e in entries
        ]

        v_list = [
            {
                "type": vc.get_vision_test_type_display()
                if hasattr(vc, "get_vision_test_type_display")
                else vc.vision_test_type,
                "result": vc.get_vision_test_result_display()
                if hasattr(vc, "get_vision_test_result_display")
                else vc.vision_test_result,
                "data_path": vc.data_path or "",
            }
            for vc in preloaded["vision"].get(animal.id, [])
        ]

        inj_list = []
        for vi in preloaded["virus"].get(animal.id, []):
            injections_summary = []
            if vi.virus_id:
                injections_summary.append(
                    f"{vi.virus_id.virus_id} ({vi.volume_ul} nL, {vi.site or 'V1'}, {vi.depth or 0} μm)"
                )
            if vi.virus_id_2:
                injections_summary.append(
                    f"{vi.virus_id_2.virus_id} ({vi.volume_nl_2} nL, {vi.site_2 or 'V1'}, {vi.depth_2 or 0} μm)"
                )
            if vi.virus_id_3:
                injections_summary.append(
                    f"{vi.virus_id_3.virus_id} ({vi.volume_nl_3} nL, {vi.site_3 or 'V1'}, {vi.depth_3 or 0} μm)"
                )

            inj_list.append({
                "date": str(vi.injection_date) if vi.injection_date else "—",
                "person": (
                    (vi.injecting_person.first_name or vi.injecting_person.username)
                    if vi.injecting_person
                    else "—"
                ),
                "surgery_date": str(vi.surgery_date) if vi.surgery_date else "—",
                "surgery_person": (
                    (vi.surgery_person.first_name or vi.surgery_person.username)
                    if vi.surgery_person
                    else "—"
                ),
                "injections": injections_summary,
                "expression": vi.expression or "",
                "notes": vi.notes or "",
            })

        im_list = []
        for im in preloaded["imaging"].get(animal.id, []):
            runs = []
            if hasattr(im, "analysis_runs"):
                for r in im.analysis_runs.all():
                    runs.append({
                        "id": r.id,
                        "status": r.status,
                        "frame_rate": str(r.frame_rate) if r.frame_rate else "—",
                        "completed_at": r.completed_at.strftime("%Y-%m-%d %H:%M")
                        if r.completed_at
                        else "—",
                    })
            im_list.append({
                "date": str(im.acquisition_date),
                "region": im.imaging_region or "V1",
                "mesc_file": im.mesc_file_path or "",
                "units": im.measurement_unit_ranges or "",
                "need_for_analysis": im.get_need_for_analysis_display()
                if hasattr(im, "get_need_for_analysis_display")
                else (im.need_for_analysis or "—"),
                "analysis_performed": im.get_analysis_performed_display()
                if hasattr(im, "get_analysis_performed_display")
                else (im.analysis_performed or "—"),
                "notes": im.notes or "",
                "runs": runs,
            })

        train_list = [
            {
                "id": ts.id,
                "date": str(ts.training_date) if ts.training_date else "—",
                "bpod_file": ts.bpod_file_path or "",
                "units": ts.training_unit_range or "",
                "status": ts.get_status_display()
                if hasattr(ts, "get_status_display")
                else (ts.status or "—"),
                "plot_path": ts.output_plot_path or "",
                "raster_path": ts.output_raster_path or "",
                "excel_path": ts.output_excel_path or "",
                "metrics": ts.metrics_json or {},
                "notes": ts.notes or "",
            }
            for ts in preloaded["training"].get(animal.id, [])
        ]

        # Chronological d' performance history for completed training sessions
        d_prime_history: List[Dict[str, Any]] = []
        raw_training = preloaded["training"].get(animal.id, [])
        sorted_training = sorted(
            [ts for ts in raw_training if getattr(ts, "training_date", None)],
            key=lambda x: (x.training_date, x.id),
        )
        for ts in sorted_training:
            metrics = ts.metrics_json or {}
            if "d_prime" in metrics and metrics["d_prime"] is not None:
                d_prime_history.append({
                    "session_id": ts.id,
                    "date": str(ts.training_date),
                    "d_prime": float(metrics["d_prime"]),
                    "hit_rate": float(metrics.get("hit_rate", 0.0)),
                    "false_alarm_rate": float(metrics.get("false_alarm_rate", 0.0)),
                    "units": ts.training_unit_range or "",
                    "n_go": metrics.get("n_go_trials", 0),
                    "n_nogo": metrics.get("n_nogo_trials", 0),
                    "hits": metrics.get("n_hits", 0),
                    "misses": metrics.get("n_misses", 0),
                    "fas": metrics.get("n_false_alarms", 0),
                    "crs": metrics.get("n_correct_rejections", 0),
                    "criterion_c": metrics.get("criterion_c", 0.0),
                })

        # Master Timeline collation
        timeline: List[Dict[str, Any]] = []
        if animal.dob:
            timeline.append({
                "date": str(animal.dob),
                "type": "dob",
                "title": "Date of Birth",
                "desc": f"Born (DOB: {animal.dob})",
            })
        for vi in inj_list:
            if vi["date"] != "—":
                timeline.append({
                    "date": vi["date"],
                    "type": "virus",
                    "title": "Viral Injection",
                    "desc": "; ".join(vi["injections"])
                    if vi["injections"]
                    else "Viral injection performed",
                })
            if vi["surgery_date"] != "—":
                timeline.append({
                    "date": vi["surgery_date"],
                    "type": "surgery",
                    "title": "Surgery",
                    "desc": f"Surgery performed by {vi['surgery_person']}",
                })
        if water_start:
            timeline.append({
                "date": str(water_start),
                "type": "water",
                "title": "Water Restriction Started",
                "desc": f"Water restriction protocol initiated on {water_start}",
            })
        for ts in train_list:
            if ts["date"] != "—":
                timeline.append({
                    "date": ts["date"],
                    "type": "training",
                    "title": "Behavior Training Session",
                    "desc": f"BPod Session: {ts['units'] or 'All units'} (Status: {ts['status']})",
                })
        for im in im_list:
            timeline.append({
                "date": im["date"],
                "type": "imaging",
                "title": "2P Imaging Session",
                "desc": f"Acquisition: {im['region']} ({im['units'] or 'All units'})",
            })
        if weights_list:
            timeline.append({
                "date": weights_list[-1]["date"],
                "type": "weight",
                "title": "Latest Body Weight",
                "desc": f"{weights_list[-1]['weight_g']} g ({weights_list[-1]['pct']}% baseline)",
            })
        timeline.sort(key=lambda x: x["date"], reverse=True)

        return {
            "id": animal.id,
            "animal_id": animal.animal_id,
            "sex": animal.get_sex_display()
            if hasattr(animal, "get_sex_display")
            else animal.sex,
            "genotype": animal.get_genotype_display()
            if hasattr(animal, "get_genotype_display")
            else animal.genotype,
            "owner": (
                (animal.owner.first_name or animal.owner.username)
                if animal.owner
                else "—"
            ),
            "cage_id": animal.cage_id or "—",
            "ogr_id": animal.ogr_id or "—",
            "project_id": animal.project_id or "—",
            "status": animal.get_status_display()
            if hasattr(animal, "get_status_display")
            else (animal.status or "Alive"),
            "pipeline_stage": animal.get_pipeline_stage_display()
            if hasattr(animal, "get_pipeline_stage_display")
            else (animal.pipeline_stage or "Intake"),
            "dob": str(animal.dob) if animal.dob else "—",
            "age_in_days": animal.age_in_days,
            "baseline_weight": baseline_weight,
            "latest_weight": latest_weight,
            "latest_pct": latest_pct,
            "water_start_date": str(water_start) if water_start else "",
            "restriction_day_str": restriction_day_str,
            "is_active": is_active,
            "is_water_restricted": is_water_restricted,
            "weighed_today": weighed_today,
            "weights": weights_list,
            "vision": v_list,
            "viruses": inj_list,
            "training_sessions": train_list,
            "d_prime_history": d_prime_history,
            "imaging": im_list,
            "timeline": timeline,
        }

    @classmethod
    def compute_pipeline_distribution(
        cls, animals_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Compute pipeline stages distribution summary using a single-pass O(N) bucket accumulator.
        """
        stage_map = {stage.lower(): stage for stage in cls.PIPELINE_STAGES}
        buckets: Dict[str, List[str]] = {stage: [] for stage in cls.PIPELINE_STAGES}

        for a in animals_data:
            stage_key = (a.get("pipeline_stage") or "").strip().lower()
            status_key = (a.get("status") or "").strip().lower()

            canonical_stage = stage_map.get(stage_key) or stage_map.get(status_key)
            if canonical_stage:
                buckets[canonical_stage].append(a["animal_id"])

        return [
            {
                "stage": stage,
                "count": len(buckets[stage]),
                "animals": buckets[stage],
            }
            for stage in cls.PIPELINE_STAGES
        ]

    @classmethod
    def get_recent_admin_activity(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch recent administration log records.
        """
        recent_activity: List[Dict[str, Any]] = []
        try:
            from django.contrib.admin.models import LogEntry

            entries = (
                LogEntry.objects.select_related("content_type", "user")
                .order_by("-action_time")[:limit]
            )
            for e in entries:
                recent_activity.append({
                    "time": e.action_time.strftime("%Y-%m-%d %H:%M"),
                    "object_repr": e.object_repr,
                    "change_message": e.get_change_message() or "Updated record",
                    "user": e.user.username if e.user else "System",
                })
        except Exception:
            pass
        return recent_activity

    @classmethod
    def get_tracker_dashboard_context(
        cls, today: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Assemble the complete context payload for the tracker view.
        """
        if today is None:
            today = timezone.now().date()

        animals_qs = Animal.objects.select_related("owner").all().order_by("animal_id")
        preloaded = cls.preload_colony_data()

        animals_data: List[Dict[str, Any]] = []
        not_weighed_today_animals: List[Animal] = []
        active_count = 0
        water_restricted_count = 0

        for animal in animals_qs:
            profile = cls.build_animal_profile(animal, preloaded, today)
            animals_data.append(profile)

            if profile["is_active"]:
                active_count += 1

            if profile["is_water_restricted"]:
                water_restricted_count += 1
                if not profile["weighed_today"]:
                    not_weighed_today_animals.append(animal)

        pipeline_distribution = cls.compute_pipeline_distribution(animals_data)
        recent_activity = cls.get_recent_admin_activity(limit=10)

        return {
            "title": "Laboratory Dashboard & Mouse Tracker",
            "total_mice": len(animals_data),
            "active_mice": active_count,
            "water_restricted_mice": water_restricted_count,
            "not_weighed_today_count": len(not_weighed_today_animals),
            "not_weighed_today_animals": not_weighed_today_animals,
            "pipeline_distribution": pipeline_distribution,
            "recent_activity": recent_activity,
            "animals_data": animals_data,
            "animals_json": json.dumps(animals_data),
            "today": today,
        }


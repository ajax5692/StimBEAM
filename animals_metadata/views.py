import json
from datetime import date
from django.apps import apps
from django.contrib.admin.views.decorators import staff_member_required
from django.db import models
from django.shortcuts import render
from django.utils import timezone

from animals_metadata.models import Animal, VisionCheck, ViralInjection


@staff_member_required
def mouse_tracker_view(request):
    today = timezone.now().date()

    # Query all animals
    animals_qs = Animal.objects.all().order_by("animal_id")

    # Safe optional queries for modular apps
    has_training = apps.is_installed("training_metadata")
    has_imaging = apps.is_installed("imaging_metadata")
    has_imaging_analysis = apps.is_installed("imaging_analysis_metadata")

    # Pre-fetch body weights if training_metadata is active
    body_weights_by_animal = {}
    if has_training:
        try:
            from training_metadata.models import MouseBodyWeight, BodyWeightEntry
            trackers = MouseBodyWeight.objects.prefetch_related("entries").all()
            for t in trackers:
                body_weights_by_animal[t.animal_id] = {
                    "tracker": t,
                    "water_start": t.water_restriction_start_date,
                    "entries": list(t.entries.all().order_by("date", "id")),
                }
        except Exception:
            pass

    # Pre-fetch vision checks
    vision_by_animal = {}
    for vc in VisionCheck.objects.all().order_by("-id"):
        vision_by_animal.setdefault(vc.animal_id_id, []).append(vc)

    # Pre-fetch viral injections
    virus_by_animal = {}
    for vi in ViralInjection.objects.select_related("virus_id", "virus_id_2", "virus_id_3").all().order_by("-injection_date"):
        virus_by_animal.setdefault(vi.animal_id_id, []).append(vi)

    # Pre-fetch imaging sessions & analysis runs
    imaging_by_animal = {}
    if has_imaging:
        try:
            from imaging_metadata.models import ImagingSession
            ims_qs = ImagingSession.objects.prefetch_related("analysis_runs").all().order_by("-acquisition_date")
            for im in ims_qs:
                imaging_by_animal.setdefault(im.animal_id, []).append(im)
        except Exception:
            pass

    # Build detailed serializable animal dictionary
    animals_data = []
    not_weighed_today_animals = []
    water_restricted_count = 0
    active_count = 0

    for a in animals_qs:
        bw_data = body_weights_by_animal.get(a.id, {})
        entries = bw_data.get("entries", [])
        water_start = bw_data.get("water_start")

        # Baseline weight (from first entry or null)
        baseline_weight = entries[0].body_weight_g if entries else None
        latest_entry = entries[-1] if entries else None
        latest_weight = latest_entry.body_weight_g if latest_entry else None
        latest_pct = latest_entry.percent_body_weight if latest_entry else None

        is_active = a.status != Animal.StatusChoices.DEAD and a.pipeline_stage not in ["Finished", "Culled"]
        if is_active:
            active_count += 1

        is_water_restricted = bool(
            water_start
            or a.pipeline_stage in ["Behavior Training", "Water Restriction"]
            or a.status == "Water restriction"
        )
        if is_water_restricted:
            water_restricted_count += 1

        # Check if weighed today
        weighed_today = False
        if entries and entries[-1].date == today:
            weighed_today = True

        if is_active and is_water_restricted and not weighed_today:
            not_weighed_today_animals.append(a)

        # Days on water restriction
        restriction_day_str = "Not on restriction"
        if water_start:
            days_diff = (today - water_start).days + 1
            if days_diff >= 1:
                restriction_day_str = f"Day {days_diff} (Since {water_start})"
            else:
                restriction_day_str = f"Starts {water_start}"
        elif is_water_restricted:
            restriction_day_str = "Active (Date not set)"

        # Prepare weights history list
        weights_list = []
        for e in entries:
            weights_list.append({
                "date": str(e.date),
                "weight_g": e.body_weight_g,
                "pct": e.percent_body_weight,
                "notes": "",
            })

        # Prepare vision checks list
        v_list = []
        for vc in vision_by_animal.get(a.id, []):
            v_list.append({
                "type": vc.get_vision_test_type_display() if hasattr(vc, "get_vision_test_type_display") else vc.vision_test_type,
                "result": vc.get_vision_test_result_display() if hasattr(vc, "get_vision_test_result_display") else vc.vision_test_result,
                "data_path": vc.data_path or "",
            })

        # Prepare virus injections list
        inj_list = []
        for vi in virus_by_animal.get(a.id, []):
            injections_summary = []
            if vi.virus_id:
                injections_summary.append(f"{vi.virus_id.virus_id} ({vi.volume_ul} nL, {vi.site or 'V1'}, {vi.depth or 0} μm)")
            if vi.virus_id_2:
                injections_summary.append(f"{vi.virus_id_2.virus_id} ({vi.volume_nl_2} nL, {vi.site_2 or 'V1'}, {vi.depth_2 or 0} μm)")
            if vi.virus_id_3:
                injections_summary.append(f"{vi.virus_id_3.virus_id} ({vi.volume_nl_3} nL, {vi.site_3 or 'V1'}, {vi.depth_3 or 0} μm)")

            inj_list.append({
                "date": str(vi.injection_date) if vi.injection_date else "—",
                "person": vi.get_injecting_person_display() if hasattr(vi, "get_injecting_person_display") else (vi.injecting_person or "—"),
                "surgery_date": str(vi.surgery_date) if vi.surgery_date else "—",
                "surgery_person": vi.get_surgery_person_display() if hasattr(vi, "get_surgery_person_display") else (vi.surgery_person or "—"),
                "injections": injections_summary,
                "expression": vi.expression or "",
                "notes": vi.notes or "",
            })

        # Prepare imaging sessions list
        im_list = []
        for im in imaging_by_animal.get(a.id, []):
            runs = []
            if hasattr(im, "analysis_runs"):
                for r in im.analysis_runs.all():
                    runs.append({
                        "id": r.id,
                        "status": r.status,
                        "frame_rate": str(r.frame_rate) if r.frame_rate else "—",
                        "completed_at": r.completed_at.strftime("%Y-%m-%d %H:%M") if r.completed_at else "—",
                    })
            im_list.append({
                "date": str(im.acquisition_date),
                "region": im.imaging_region or "V1",
                "mesc_file": im.mesc_file_path or "",
                "units": im.measurement_unit_ranges or "",
                "need_for_analysis": im.get_need_for_analysis_display() if hasattr(im, "get_need_for_analysis_display") else (im.need_for_analysis or "—"),
                "analysis_performed": im.get_analysis_performed_display() if hasattr(im, "get_analysis_performed_display") else (im.analysis_performed or "—"),
                "notes": im.notes or "",
                "runs": runs,
            })

        # Build master timeline for this animal
        timeline = []
        if a.dob:
            timeline.append({"date": str(a.dob), "type": "dob", "title": "Date of Birth", "desc": f"Born (DOB: {a.dob})"})
        for vi in inj_list:
            if vi["date"] != "—":
                timeline.append({"date": vi["date"], "type": "virus", "title": "Viral Injection", "desc": "; ".join(vi["injections"]) if vi["injections"] else "Viral injection performed"})
            if vi["surgery_date"] != "—":
                timeline.append({"date": vi["surgery_date"], "type": "surgery", "title": "Surgery", "desc": f"Surgery performed by {vi['surgery_person']}"})
        if water_start:
            timeline.append({"date": str(water_start), "type": "water", "title": "Water Restriction Started", "desc": f"Water restriction protocol initiated on {water_start}"})
        for im in im_list:
            timeline.append({"date": im["date"], "type": "imaging", "title": "2P Imaging Session", "desc": f"Acquisition: {im['region']} ({im['units'] or 'All units'})"})
        if weights_list:
            timeline.append({"date": weights_list[-1]["date"], "type": "weight", "title": "Latest Body Weight", "desc": f"{weights_list[-1]['weight_g']} g ({weights_list[-1]['pct']}% baseline)"})
        timeline.sort(key=lambda x: x["date"], reverse=True)

        animals_data.append({
            "id": a.id,
            "animal_id": a.animal_id,
            "sex": a.get_sex_display() if hasattr(a, "get_sex_display") else a.sex,
            "genotype": a.get_genotype_display() if hasattr(a, "get_genotype_display") else a.genotype,
            "owner": a.get_owner_display() if hasattr(a, "get_owner_display") else (a.owner or "—"),
            "cage_id": a.cage_id or "—",
            "ogr_id": a.ogr_id or "—",
            "project_id": a.project_id or "—",
            "status": a.get_status_display() if hasattr(a, "get_status_display") else (a.status or "Alive"),
            "pipeline_stage": a.get_pipeline_stage_display() if hasattr(a, "get_pipeline_stage_display") else (a.pipeline_stage or "Intake"),
            "dob": str(a.dob) if a.dob else "—",
            "age_in_days": a.age_in_days,
            "baseline_weight": baseline_weight,
            "latest_weight": latest_weight,
            "latest_pct": latest_pct,
            "water_start_date": str(water_start) if water_start else "",
            "restriction_day_str": restriction_day_str,
            "weights": weights_list,
            "vision": v_list,
            "viruses": inj_list,
            "imaging": im_list,
            "timeline": timeline,
        })

    # Pipeline stages distribution summary
    pipeline_stages = [
        "Intake",
        "Vision Check",
        "Virus Injection",
        "Surgery",
        "Behavior Training",
        "Finished",
        "Culled",
    ]
    pipeline_distribution = []
    for stage in pipeline_stages:
        matching = [a for a in animals_data if a["pipeline_stage"].lower() == stage.lower() or a["status"].lower() == stage.lower()]
        pipeline_distribution.append({
            "stage": stage,
            "count": len(matching),
            "animals": [m["animal_id"] for m in matching],
        })

    # Recent activity logs
    recent_activity = []
    try:
        from django.contrib.admin.models import LogEntry
        entries = LogEntry.objects.select_related("content_type", "user").order_by("-action_time")[:10]
        for e in entries:
            recent_activity.append({
                "time": e.action_time.strftime("%Y-%m-%d %H:%M"),
                "object_repr": e.object_repr,
                "change_message": e.get_change_message() or "Updated record",
                "user": e.user.username if e.user else "System",
            })
    except Exception:
        pass

    context = {
        "title": "Laboratory Dashboard & Mouse Tracker",
        "total_mice": animals_qs.count(),
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

    return render(request, "admin/mouse_tracker.html", context)
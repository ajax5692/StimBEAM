import os
from pathlib import Path
import re

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from animals_metadata.utils import (
    BaseTrackChangesAdmin,
    CopyablePathInput,
    is_same_mesc_file,
    parse_unit_ranges,
    render_copyable_path_widget,
)

from .models import ImagingSession, MouseImagingRecord, TrackChanges


class ImagingSessionAdminForm(forms.ModelForm):
    class Meta:
        model = ImagingSession
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "analysis_performed" in self.fields:
            # Exclude RECORD_DELETED so users only see Yes, No, or Blank in the dropdown
            user_allowed_choices = [
                ("", "---------"),
                (ImagingSession.AnalysisPerformedChoices.YES.value, ImagingSession.AnalysisPerformedChoices.YES.label),
                (ImagingSession.AnalysisPerformedChoices.NO.value, ImagingSession.AnalysisPerformedChoices.NO.label),
            ]
            self.fields["analysis_performed"].choices = user_allowed_choices


class ImagingSessionInlineFormSet(forms.BaseInlineFormSet):
    """
    Formset validator checking intra-submission collisions between multiple forms
    submitted simultaneously in the inline table.
    """
    def clean(self):
        super().clean()
        valid_forms = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if self._should_delete_form(form):
                continue
            date = form.cleaned_data.get("acquisition_date")
            mesc_file = form.cleaned_data.get("mesc_file_path")
            unit_range = form.cleaned_data.get("measurement_unit_ranges")
            if date and mesc_file and unit_range:
                valid_forms.append((form, date, mesc_file, unit_range))

        # Check for duplicate same MESC file with identical unit numbers within submitted forms
        for i in range(len(valid_forms)):
            form_i, date_i, file_i, units_i = valid_forms[i]
            parsed_i = parse_unit_ranges(units_i)
            for j in range(i + 1, len(valid_forms)):
                form_j, date_j, file_j, units_j = valid_forms[j]
                if date_i == date_j and is_same_mesc_file(file_i, file_j):
                    parsed_j = parse_unit_ranges(units_j)
                    if parsed_i == parsed_j:
                        filename = Path(file_j).name or file_j
                        err_msg = (
                            f"Duplicate session: The MESC file '{filename}' cannot be uploaded multiple times "
                            f"on {date_j} with identical unit numbers ({units_j})."
                        )
                        form_j.add_error("measurement_unit_ranges", err_msg)


class ImagingSessionInline(admin.TabularInline):
    model = ImagingSession
    formset = ImagingSessionInlineFormSet
    fk_name = "tracker"
    extra = 0
    fields = (
        "acquisition_date",
        "mesc_file_path",
        "measurement_unit_ranges",
        "imaging_region",
        "need_for_analysis",
        "analysis_performed",
        "notes",
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "mesc_file_path":
            kwargs["widget"] = CopyablePathInput(attrs={"style": "width: 100%; min-width: 200px;"}, tooltip="Copy MESC file path")
            return db_field.formfield(**kwargs)
        if db_field.name == "measurement_unit_ranges":
            kwargs["widget"] = forms.TextInput(attrs={"style": "min-width: 110px;"})
            return db_field.formfield(**kwargs)
        if db_field.name == "imaging_region":
            kwargs["widget"] = forms.TextInput(attrs={"style": "min-width: 100px;"})
            return db_field.formfield(**kwargs)
        if db_field.name == "notes":
            kwargs["widget"] = forms.TextInput(attrs={"style": "min-width: 140px;"})
            return db_field.formfield(**kwargs)
        if db_field.name == "analysis_performed":
            formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
            if formfield:
                user_allowed_choices = [
                    ("", "---------"),
                    (ImagingSession.AnalysisPerformedChoices.YES.value, ImagingSession.AnalysisPerformedChoices.YES.label),
                    (ImagingSession.AnalysisPerformedChoices.NO.value, ImagingSession.AnalysisPerformedChoices.NO.label),
                ]
                formfield.choices = user_allowed_choices
            return formfield
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(MouseImagingRecord)
class MouseImagingRecordAdmin(SimpleHistoryAdmin):
    inlines = [ImagingSessionInline]
    list_select_related = ("animal", "animal__owner")

    list_display = (
        "get_animal_id",
        "get_owner",
        "get_total_sessions",
        "get_latest_acquisition_date",
        "get_pipeline_stage",
    )

    list_filter = (
        "animal__owner",
        "animal__status",
        "animal__pipeline_stage",
    )

    search_fields = (
        "animal__animal_id",
        "animal__owner__username",
        "animal__owner__first_name",
        "animal__owner__last_name",
        "notes",
    )

    ordering = (
        "animal__animal_id",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    (
                        "animal",
                        "get_owner_display",
                        "notes",
                    ),
                ),
            },
        ),
    )

    readonly_fields = (
        "get_owner_display",
    )

    formfield_overrides = {
        models.TextField: {
            "widget": forms.Textarea(
                attrs={
                    "rows": 1,
                    "style": "height: 36px; width: 100%; min-width: 250px; max-width: 450px; resize: vertical;",
                    "placeholder": "Notes...",
                }
            ),
        },
    }

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("animal",)
        return self.readonly_fields

    @admin.display(description="Animal ID", ordering="animal__animal_id")
    def get_animal_id(self, obj):
        return obj.animal.animal_id if obj.animal else "-"

    @admin.display(description="Owner", ordering="animal__owner")
    def get_owner(self, obj):
        if obj.animal and obj.animal.owner:
            return obj.animal.owner.first_name if obj.animal.owner.first_name else obj.animal.owner.username
        return "-"

    @admin.display(description="Owner")
    def get_owner_display(self, obj):
        if obj and obj.animal and obj.animal.owner:
            owner_name = obj.animal.owner.first_name if obj.animal.owner.first_name else obj.animal.owner.username
            return f"{owner_name}"
        return "-"

    @admin.display(description="Total Sessions")
    def get_total_sessions(self, obj):
        return obj.sessions.count()

    @admin.display(description="Last Imaging Day")
    def get_latest_acquisition_date(self, obj):
        latest = obj.sessions.order_by("-acquisition_date", "-id").first()
        return latest.acquisition_date if latest else "-"

    @admin.display(description="Pipeline Stage", ordering="animal__pipeline_stage")
    def get_pipeline_stage(self, obj):
        return obj.animal.get_pipeline_stage_display() if (obj.animal and hasattr(obj.animal, "get_pipeline_stage_display")) else (obj.animal.pipeline_stage if obj.animal else "-")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("sessions")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        saved_instances = []
        for instance in instances:
            if isinstance(instance, ImagingSession):
                if not instance.animal_id and form.instance.animal_id:
                    instance.animal = form.instance.animal
                instance.tracker = form.instance
            instance.save()
            saved_instances.append(instance)
        for deleted_obj in formset.deleted_objects:
            deleted_obj.delete()
        formset.save_m2m()

        # Check all sessions for this record: warn every time the record is saved if any share MESC file on the same date with overlapping or different unit ranges
        animal = form.instance.animal if hasattr(form.instance, "animal") else None
        all_sessions = list(ImagingSession.objects.filter(animal=animal)) if animal else []
        warned_pairs = set()
        for i in range(len(all_sessions)):
            sess_i = all_sessions[i]
            if not sess_i.acquisition_date or not sess_i.mesc_file_path:
                continue
            units_i = parse_unit_ranges(sess_i.measurement_unit_ranges)
            for j in range(i + 1, len(all_sessions)):
                sess_j = all_sessions[j]
                if sess_i.acquisition_date == sess_j.acquisition_date and is_same_mesc_file(sess_i.mesc_file_path, sess_j.mesc_file_path):
                    pair_key = tuple(sorted([sess_i.pk, sess_j.pk]))
                    if pair_key in warned_pairs:
                        continue
                    warned_pairs.add(pair_key)
                    units_j = parse_unit_ranges(sess_j.measurement_unit_ranges)
                    overlap = set(units_i) & set(units_j) if (units_i and units_j) else set()
                    filename = Path(sess_i.mesc_file_path).name or sess_i.mesc_file_path
                    animal_id = form.instance.animal.animal_id if form.instance.animal else ""
                    if overlap:
                        desc_text = "overlapping unit ranges"
                    else:
                        desc_text = "different unit ranges"

                    messages.warning(
                        request,
                        format_html(
                            '<strong>Notice:</strong> The MESC file <code>{}</code> is uploaded multiple times on <strong>{}</strong> for animal <strong>{}</strong> with {} (<code>{}</code> and <code>{}</code>).',
                            filename,
                            sess_i.acquisition_date,
                            animal_id,
                            desc_text,
                            sess_i.measurement_unit_ranges,
                            sess_j.measurement_unit_ranges,
                        ),
                    )

    def response_add(self, request, obj, post_url_continue=None):
        if "_save" in request.POST:
            self.message_user(request, f"Imaging record for {obj.animal.animal_id} was saved successfully.")
            return redirect(reverse("admin:imaging_metadata_mouseimagingrecord_change", args=[obj.pk]))
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_save" in request.POST:
            self.message_user(request, f"Imaging record for {obj.animal.animal_id} was saved successfully.")
            return redirect(reverse("admin:imaging_metadata_mouseimagingrecord_change", args=[obj.pk]))
        return super().response_change(request, obj)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["subtitle"] = None
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "resolve-mesc-file/",
                self.admin_site.admin_view(self.resolve_mesc_file_view),
                name="imaging_resolve_mesc_file",
            ),
            path(
                "<int:record_id>/delete-session/<int:session_id>/",
                self.admin_site.admin_view(self.delete_session_view),
                name="imaging_delete_session",
            ),
        ]
        return custom_urls + urls

    def resolve_mesc_file_view(self, request):
        if not self.has_change_permission(request):
            return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)

        filename = request.GET.get("filename", "").strip()
        animal_id = request.GET.get("animal_id", "").strip()
        client_dir = request.GET.get("client_dir", "").strip()
        dropped_path = request.GET.get("dropped_path", "").strip()

        if not filename and not dropped_path:
            return JsonResponse({"status": "error", "message": "No filename provided"}, status=400)

        if dropped_path and not filename:
            filename = Path(dropped_path).name

        # Extract date from filename: YYYY-MM-DD (e.g. m67_behaveAlpha_2025-10-07.mesc) or YYYYMMDD
        date_str = None
        hyphen_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
        if hyphen_match:
            y, mo, d = hyphen_match.group(1), hyphen_match.group(2), hyphen_match.group(3)
            if 2000 <= int(y) <= 2100 and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
                date_str = f"{y}-{mo}-{d}"
        if not date_str:
            date_match = re.search(r"(?:^|[_-])(\d{4})(\d{2})(\d{2})(?:[_-](\d{6}))?", filename)
            if date_match:
                y, mo, d = date_match.group(1), date_match.group(2), date_match.group(3)
                if 2000 <= int(y) <= 2100 and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
                    date_str = f"{y}-{mo}-{d}"

        # Extract animal ID from filename (token before first underscore or hyphen, or matching animal_id)
        # e.g. "m67_behaveAlpha_2025-10-07.mesc" -> "m67"
        file_animal_id = None
        if animal_id and (
            filename.lower().startswith(animal_id.lower() + "_")
            or filename.lower().startswith(animal_id.lower() + "-")
        ):
            file_animal_id = animal_id
        else:
            animal_match = re.match(r"^([a-zA-Z0-9]+)[_-]", filename)
            if animal_match:
                file_animal_id = animal_match.group(1)
            else:
                from animals_metadata.models import Animal
                for a_id in Animal.objects.values_list("animal_id", flat=True):
                    if a_id and (
                        filename.lower().startswith(a_id.lower() + "_")
                        or filename.lower().startswith(a_id.lower() + "-")
                    ):
                        file_animal_id = a_id
                        break

        # Build candidate directories to look for the file on disk
        candidates_to_check = []
        if dropped_path:
            candidates_to_check.append(Path(dropped_path))

        if client_dir:
            candidates_to_check.append(Path(client_dir) / filename)

        # Check sessions for this animal
        if animal_id:
            animal_paths = ImagingSession.objects.filter(
                animal__animal_id__iexact=animal_id
            ).exclude(mesc_file_path="").values_list("mesc_file_path", flat=True)
            for p in animal_paths:
                parent_dir = Path(p).parent
                candidates_to_check.append(parent_dir / filename)
                if parent_dir.is_dir():
                    try:
                        for sub in parent_dir.iterdir():
                            if sub.is_dir():
                                candidates_to_check.append(sub / filename)
                    except (PermissionError, OSError):
                        pass

        # Check all sessions in DB
        all_paths = ImagingSession.objects.exclude(mesc_file_path="").values_list(
            "mesc_file_path", flat=True
        ).distinct()
        for p in all_paths:
            parent_dir = Path(p).parent
            candidates_to_check.append(parent_dir / filename)

        # Check candidate files
        seen = set()
        resolved_path = None
        for cand in candidates_to_check:
            try:
                cand_str = str(cand).lower()
                if cand_str in seen:
                    continue
                seen.add(cand_str)
                if cand.is_file():
                    resolved_path = str(cand.resolve())
                    break
            except (PermissionError, OSError):
                continue

        # If not yet found, check Desktop subdirectories
        if not resolved_path:
            try:
                desktop = Path.home() / "Desktop"
                if desktop.is_dir():
                    cand = desktop / filename
                    if cand.is_file():
                        resolved_path = str(cand.resolve())
                    else:
                        for match in desktop.glob(f"*/{filename}"):
                            if match.is_file():
                                resolved_path = str(match.resolve())
                                break
                        if not resolved_path:
                            for match in desktop.glob(f"*/*/{filename}"):
                                if match.is_file():
                                    resolved_path = str(match.resolve())
                                    break
            except Exception:
                pass

        # Suggested dir for fallback
        suggested_dir = ""
        latest_session = ImagingSession.objects.filter(
            animal__animal_id__iexact=animal_id
        ).exclude(mesc_file_path="").order_by("-id").first()
        if not latest_session:
            latest_session = ImagingSession.objects.exclude(mesc_file_path="").order_by("-id").first()
        if latest_session and latest_session.mesc_file_path:
            suggested_dir = str(Path(latest_session.mesc_file_path).parent)

        if resolved_path:
            resolved_path_str = os.path.normpath(resolved_path)
            return JsonResponse({
                "status": "success",
                "found": True,
                "filepath": resolved_path_str,
                "filename": filename,
                "detected_date": date_str,
                "detected_animal_id": file_animal_id,
                "suggested_dir": os.path.dirname(resolved_path_str),
            })
        else:
            fallback_path = os.path.normpath(os.path.join(suggested_dir, filename)) if suggested_dir else filename
            return JsonResponse({
                "status": "success",
                "found": False,
                "filepath": fallback_path,
                "filename": filename,
                "detected_date": date_str,
                "detected_animal_id": file_animal_id,
                "suggested_dir": suggested_dir,
            })

    def delete_session_view(self, request, record_id, session_id):
        if not self.has_change_permission(request):
            raise PermissionDenied

        record = get_object_or_404(MouseImagingRecord, pk=record_id)
        session = ImagingSession.objects.filter(pk=session_id).first()
        if not session:
            messages.warning(request, "Imaging session not found or already deleted.")
            return redirect(reverse("admin:imaging_metadata_mouseimagingrecord_change", args=[record_id]))

        if session.tracker_id != record.pk and session.animal_id != record.animal_id:
            messages.error(request, "This imaging session does not belong to this animal.")
            return redirect(reverse("admin:imaging_metadata_mouseimagingrecord_change", args=[record_id]))

        date_str = str(session.acquisition_date)
        animal_str = str(session.animal.animal_id) if session.animal else ""
        session.delete()
        messages.success(
            request,
            f"Imaging session ({date_str}) for animal {animal_str} was deleted successfully.",
        )
        return redirect(reverse("admin:imaging_metadata_mouseimagingrecord_change", args=[record_id]))


@admin.register(ImagingSession)
class ImagingSessionAdmin(SimpleHistoryAdmin):
    form = ImagingSessionAdminForm
    list_select_related = ("animal",)

    list_display = (
        "animal",
        "acquisition_date",
        "imaging_region",
        "measurement_unit_ranges",
        "display_mesc_file_path",
        "display_analysis_requirement",
        "display_analysis_performed",
    )

    list_filter = (
        "acquisition_date",
        "animal__animal_id",
        "need_for_analysis",
        "analysis_performed",
    )

    search_fields = (
        "animal__animal_id",
    )

    ordering = ("-acquisition_date",)

    def has_module_permission(self, request):
        return False

    @admin.display(description="MESC File Path", ordering="mesc_file_path")
    def display_mesc_file_path(self, obj):
        return render_copyable_path_widget(obj.mesc_file_path, tooltip="Copy MESC file path")

    @admin.display(description="Required for Analysis?", ordering="need_for_analysis")
    def display_analysis_requirement(self, obj):
        verdict = obj.need_for_analysis
        if not verdict:
            return "-"
        label = obj.get_need_for_analysis_display() if hasattr(obj, "get_need_for_analysis_display") else verdict
        color = "#4ade80" if verdict == "Y" else "#ff4d4f"
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            label,
        )

    @admin.display(description="Analysis Performed?", ordering="analysis_performed")
    def display_analysis_performed(self, obj):
        verdict = obj.analysis_performed
        if not verdict:
            return "-"
        label = obj.get_analysis_performed_display() if hasattr(obj, "get_analysis_performed_display") else verdict

        if verdict == ImagingSession.AnalysisPerformedChoices.YES:
            color = "#4ade80"
        elif verdict == ImagingSession.AnalysisPerformedChoices.RECORD_DELETED:
            color = "#f59e0b"
        else:
            color = "#ff4d4f"

        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            label,
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.animal_id and obj.acquisition_date and obj.mesc_file_path:
            other_sessions = ImagingSession.objects.filter(
                animal=obj.animal,
                acquisition_date=obj.acquisition_date,
            ).exclude(pk=obj.pk)
            for other in other_sessions:
                if is_same_mesc_file(obj.mesc_file_path, other.mesc_file_path):
                    filename = Path(obj.mesc_file_path).name or obj.mesc_file_path
                    units_curr = parse_unit_ranges(obj.measurement_unit_ranges)
                    units_other = parse_unit_ranges(other.measurement_unit_ranges)
                    overlap = set(units_curr) & set(units_other) if (units_curr and units_other) else set()
                    if overlap:
                        desc_text = "overlapping unit ranges"
                    else:
                        desc_text = "different unit ranges"
                    messages.warning(
                        request,
                        format_html(
                            '<strong>Notice:</strong> The MESC file <code>{}</code> is uploaded multiple times on <strong>{}</strong> for animal <strong>{}</strong> with {} (<code>{}</code> and <code>{}</code>).',
                            filename,
                            obj.acquisition_date,
                            obj.animal.animal_id,
                            desc_text,
                            obj.measurement_unit_ranges,
                            other.measurement_unit_ranges,
                        ),
                    )
                    break


@admin.register(TrackChanges)
class TrackChangesAdmin(BaseTrackChangesAdmin):
    pass
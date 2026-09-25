import json
from pathlib import Path

from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from animals_metadata.utils import (
    CopyablePathInput,
    get_user_initials,
    render_output_resource_row,
)
from imaging_metadata.models import ImagingSession

from .models import AnalysisRun, TrackChanges


class ImagingSessionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.animal.animal_id} - {obj.acquisition_date} (Units: {obj.measurement_unit_ranges})"
    
    
class AnalysisRunAdminForm(forms.ModelForm):
    imaging_session = ImagingSessionChoiceField(
        queryset=ImagingSession.objects.select_related("animal").all()
    )

    class Meta:
        model = AnalysisRun
        fields = "__all__"
        widgets = {
            "output_log_path": CopyablePathInput(
                attrs={"class": "vTextField", "style": "width: 100%; max-width: 600px;"},
                tooltip="Copy Log file path",
            ),
            "output_path": CopyablePathInput(
                attrs={"class": "vTextField", "style": "width: 100%; max-width: 600px;"},
                tooltip="Copy Suite2P output path",
            ),
        }

@admin.register(AnalysisRun)
class AnalysisRunAdmin(SimpleHistoryAdmin):
    form = AnalysisRunAdminForm
    list_select_related = ("imaging_session__animal",)

    list_display = (
        "id",
        "animal_id",
        "display_imaging_session",
        "display_status",
        "frame_rate",
        "created_at",
        "started_at",
        "completed_at",
        "display_output_resources",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "imaging_session__animal__animal_id",
        "imaging_session__mesc_file_path",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "created_at",
        "frame_rate",
        "started_at",
        "completed_at",
        "error_message",
    )

    @admin.display(description="Animal ID")
    def animal_id(self, obj):
        return obj.animal_id

    @admin.display(description="Imaging Session", ordering="imaging_session__acquisition_date")
    def display_imaging_session(self, obj):
        if not obj.imaging_session:
            return "-"
        session = obj.imaging_session
        unit_str = f"({session.measurement_unit_ranges})" if session.measurement_unit_ranges else ""
        return format_html(
            '<div style="line-height: 1.25;">'
            '<div>{} - {}</div>'
            '<div style="font-size: 11px; color: #94a3b8; font-weight: 500;">{}</div>'
            '</div>',
            session.animal.animal_id,
            session.acquisition_date,
            unit_str,
        )

    @admin.display(description="Status", ordering="status")
    def display_status(self, obj):
        if obj.status == AnalysisRun.StatusChoices.RUNNING:
            return format_html(
                '<span style="display: inline-flex; align-items: center; gap: 6px; color: #60a5fa; font-weight: 600;">'
                '<span>{}</span>'
                '<span style="'
                'width: 12px;'
                'height: 12px;'
                'border: 2px solid rgba(255,255,255,0.35);'
                'border-top-color: currentColor;'
                'border-radius: 50%;'
                'display: inline-block;'
                'animation: analysis-spin 0.8s linear infinite;'
                'flex-shrink: 0;'
                '"></span>'
                '</span>',
                "Running",
            )
        elif obj.status == AnalysisRun.StatusChoices.COMPLETED:
            return format_html(
                '<span style="display: inline-flex; align-items: center; gap: 4px; color: #4ade80; font-weight: 600;">'
                '<span>{}</span>'
                '</span>',
                "✓ Completed",
            )
        elif obj.status == AnalysisRun.StatusChoices.FAILED:
            return format_html(
                '<span style="display: inline-flex; align-items: center; gap: 4px; color: #f87171; font-weight: 600;" title="{}">'
                '<span>{}</span>'
                '</span>',
                obj.error_message or "Analysis failed",
                "✗ Failed",
            )
        return format_html(
            '<span style="color: #facc15; font-weight: 600;">{}</span>',
            "Pending",
        )

    @admin.display(description="Output Resource Path")
    def display_output_resources(self, obj):
        output_path = obj.output_path
        log_path = obj.output_log_path

        # ---------------------------------------------------------
        # Fallback for older AnalysisRun records where
        # output_log_path was not stored in the database.
        # ---------------------------------------------------------
        if not log_path and output_path:
            output_dir = Path(output_path)
            old_log = output_dir / "pipeline_log.txt"

            if old_log.exists():
                log_path = str(old_log)
            else:
                run_logs = list(
                    output_dir.glob("*_runlog.txt")
                )
                if run_logs:
                    newest_log = max(
                        run_logs,
                        key=lambda path: path.stat().st_mtime,
                    )
                    log_path = str(newest_log)

        log_row = render_output_resource_row(
            run_id=obj.pk or 0,
            field_name="output_log_path",
            label="• Log:",
            file_path=log_path,
            copy_tooltip="Copy Log file path",
            edit_tooltip="Edit Log file path",
        )
        suite2p_row = render_output_resource_row(
            run_id=obj.pk or 0,
            field_name="output_path",
            label="• Suite2P:",
            file_path=output_path,
            copy_tooltip="Copy Suite2P output path",
            edit_tooltip="Edit Suite2P output path",
        )

        return format_html(
            '<div style="white-space: normal; min-width: 450px;">'
            '{}'
            '<div style="height: 8px;"></div>'
            '{}'
            '</div>',
            log_row,
            suite2p_row,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:run_id>/update-output-path/",
                self.admin_site.admin_view(self.update_output_path_view),
                name="imaging_analysis_metadata_analysisrun_update_output_path",
            ),
        ]
        return custom_urls + urls

    def update_output_path_view(self, request, run_id):
        if request.method != "POST":
            return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

        try:
            run = AnalysisRun.objects.select_related("imaging_session__animal").get(pk=run_id)
        except AnalysisRun.DoesNotExist:
            return JsonResponse({"status": "error", "message": "AnalysisRun not found"}, status=404)

        if not self.has_change_permission(request, run):
            return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)

        if request.content_type == "application/json":
            try:
                data = json.loads(request.body.decode("utf-8"))
            except Exception:
                data = {}
            field = data.get("field")
            value = data.get("value", "")
        else:
            field = request.POST.get("field")
            value = request.POST.get("value", "")

        if field not in ("output_log_path", "output_path"):
            return JsonResponse({"status": "error", "message": "Invalid field specified"}, status=400)

        value = (value or "").strip()
        setattr(run, field, value)
        run._history_user = request.user
        run._change_reason = f"Updated {field} via Output Resource Path editor"
        run.save(update_fields=[field])

        return JsonResponse({
            "status": "success",
            "field": field,
            "value": value,
            "message": f"Successfully updated {field}",
        })

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # Sync the parent ImagingSession with the chosen status
        session = obj.imaging_session
        if session:
            if obj.status == AnalysisRun.StatusChoices.COMPLETED:
                session.analysis_performed = "Y"
                session.save(update_fields=["analysis_performed"])
            elif obj.status == AnalysisRun.StatusChoices.FAILED:
                session.analysis_performed = "N"
                session.save(update_fields=["analysis_performed"])


@admin.register(TrackChanges)
class TrackChangesAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "animal_id",
        "action",
        "changed_at",
        "display_changed_by",
        "changes",
    )

    list_filter = (
        "category",
        "action",
        "changed_at",
    )

    search_fields = (
        "animal_id",
        "changed_by",
        "changes",
    )

    ordering = (
        "-changed_at",
    )

    readonly_fields = (
        "category",
        "animal_id",
        "action",
        "changed_at",
        "changed_by",
        "changes",
    )

    @admin.display(description="Changed by", ordering="changed_by")
    def display_changed_by(self, obj):
        return get_user_initials(obj.changed_by)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

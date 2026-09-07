from pathlib import Path

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

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
        "output_log_path",
        "output_path",
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

        log_text = log_path or "Not available"
        output_text = output_path or "Not available"

        return format_html(
            '<div style="white-space: normal; min-width: 450px;">'

                '<div style="display: grid; '
                'grid-template-columns: max-content max-content 1fr; '
                'column-gap: 6px; '
                'align-items: start;">'

                    '<button type="button" '
                'class="pstim-copy-button" '
                'data-copy-text="{}" '
                'title="Copy MESC file path" '
                'aria-label="Copy MESC file path">'

                    '<svg '
                    'width="16" '
                    'height="16" '
                    'viewBox="0 0 24 24" '
                    'fill="none" '
                    'stroke="currentColor" '
                    'stroke-width="2" '
                    'stroke-linecap="round" '
                    'stroke-linejoin="round" '
                    'aria-hidden="true">'

                        '<rect '
                        'x="8" '
                        'y="8" '
                        'width="12" '
                        'height="12" '
                        'rx="2">'
                        '</rect>'

                        '<path '
                        'd="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2">'
                        '</path>'

                    '</svg>'

                '</button>'

                    '<strong>• Log:</strong>'

                    '<span style="overflow-wrap: anywhere;">'
                    '{}'
                    '</span>'

                '</div>'

                '<div style="height: 8px;"></div>'

                '<div style="display: grid; '
                'grid-template-columns: max-content max-content 1fr; '
                'column-gap: 6px; '
                'align-items: start;">'

                    '<button type="button" '
                'class="pstim-copy-button" '
                'data-copy-text="{}" '
                'title="Copy MESC file path" '
                'aria-label="Copy MESC file path">'

                    '<svg '
                    'width="16" '
                    'height="16" '
                    'viewBox="0 0 24 24" '
                    'fill="none" '
                    'stroke="currentColor" '
                    'stroke-width="2" '
                    'stroke-linecap="round" '
                    'stroke-linejoin="round" '
                    'aria-hidden="true">'

                        '<rect '
                        'x="8" '
                        'y="8" '
                        'width="12" '
                        'height="12" '
                        'rx="2">'
                        '</rect>'

                        '<path '
                        'd="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2">'
                        '</path>'

                    '</svg>'

                '</button>'

                    '<strong>• Suite2P:</strong>'

                    '<span style="overflow-wrap: anywhere;">'
                    '{}'
                    '</span>'

                '</div>'

            '</div>',
            log_text,
            log_text,
            output_text,
            output_text,
        )

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


from animals_metadata.utils import get_user_initials


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

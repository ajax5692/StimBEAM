from django.contrib import admin
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from animals_metadata.utils import (
    BaseTrackChangesAdmin,
    render_copyable_path_widget,
)

from .models import ImagingSession, TrackChanges


@admin.register(ImagingSession)
class ImagingSessionAdmin(SimpleHistoryAdmin):
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
        color = "#4ade80" if verdict == "Y" else "#ff4d4f"
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            label,
        )


@admin.register(TrackChanges)
class TrackChangesAdmin(BaseTrackChangesAdmin):
    pass
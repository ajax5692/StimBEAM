from django.contrib import admin
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
        "need_for_analysis",
        "analysis_performed",
    )

    list_filter = (
        "acquisition_date",
        "animal__animal_id",
    )

    search_fields = (
        "animal__animal_id",
    )

    ordering = ("-acquisition_date",)

    @admin.display(description="MESC File Path", ordering="mesc_file_path")
    def display_mesc_file_path(self, obj):
        return render_copyable_path_widget(obj.mesc_file_path, tooltip="Copy MESC file path")


@admin.register(TrackChanges)
class TrackChangesAdmin(BaseTrackChangesAdmin):
    pass
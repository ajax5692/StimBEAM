from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from animals_metadata.utils import BaseAsyncJobModel
from .utils import parse_unit_ranges


class AnalysisRun(BaseAsyncJobModel):
    imaging_session = models.ForeignKey(
        "imaging_metadata.ImagingSession",
        on_delete=models.PROTECT,
        related_name="analysis_runs",
    )
    
    frame_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Frame rate detected by the imaging analysis pipeline (Hz).",
    )
    
    default_diameter = models.FloatField(
        default=12.0,
        validators=[MinValueValidator(0.01)],
        help_text="Expected cell diameter used for Suite2p cell detection.",
    )

    tau = models.FloatField(
        default=0.7,
        validators=[MinValueValidator(0.01)],
        help_text="Calcium indicator decay time constant used for analysis.",
    )

    output_log_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to the pipeline log generated for this analysis run.",
    )

    output_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Base directory containing Suite2p analysis outputs.",
    )

    notes = models.TextField(
        blank=True,
    )

    @property
    def animal_id(self):
        return self.imaging_session.animal.animal_id
    
    @property
    def unit_indices(self):
        return parse_unit_ranges(
            self.imaging_session.measurement_unit_ranges
        )

    def mark_completed(self) -> None:
        super().mark_completed()
        if self.imaging_session and self.imaging_session.analysis_performed != "Y":
            self.imaging_session.analysis_performed = "Y"
            self.imaging_session.save(update_fields=["analysis_performed"])

    def mark_failed(self, error_message: str = "") -> None:
        super().mark_failed(error_message)
        if self.imaging_session and self.imaging_session.analysis_performed != "N":
            self.imaging_session.analysis_performed = "N"
            self.imaging_session.save(update_fields=["analysis_performed"])

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Analysis Run"
        verbose_name_plural = "Analysis Runs"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.animal_id} - "
            f"{self.imaging_session.acquisition_date} - "
            f"Run {self.pk or 'New'}"
        )


class TrackChanges(models.Model):

    class CategoryChoices(models.TextChoices):
        ANALYSIS_RUN = "analysis_run", "Analysis Run"

    class ActionChoices(models.TextChoices):
        CREATED = "+", "Created"
        UPDATED = "~", "Updated"
        DELETED = "-", "Deleted"

    category = models.CharField(
        max_length=30,
        choices=CategoryChoices.choices,
    )

    animal_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    action = models.CharField(
        max_length=1,
        choices=ActionChoices.choices,
    )

    changed_at = models.DateTimeField()

    changed_by = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    changes = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Track Change"
        verbose_name_plural = "Track Changes"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.get_category_display()} - {self.animal_id}"
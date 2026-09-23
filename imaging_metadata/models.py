from django.db import models
from simple_history.models import HistoricalRecords

from animals_metadata.utils import validate_non_overlapping_session_units
from .validators import validate_measurement_unit_ranges


class ImagingSession(models.Model):
    animal = models.ForeignKey(
        "animals_metadata.Animal",
        on_delete=models.PROTECT,
        related_name="imaging_sessions",
    )

    acquisition_date = models.DateField()

    imaging_region = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    mesc_file_path = models.CharField(
        max_length=500,
        help_text="Path to the source .mesc file.",
    )

    measurement_unit_ranges = models.CharField(
        max_length=200,
        validators=[validate_measurement_unit_ranges],
        help_text="Example: 10:21,25:55",
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )
    
    class NeedForAnalysisChoices(models.TextChoices):
        YES = 'Y', 'Yes'
        NO  = 'N', 'No'
        
    need_for_analysis = models.TextField(
        blank=True,
        null=True,
        choices=NeedForAnalysisChoices.choices,
        verbose_name="Required for Analysis?"
    )
    
    class AnalysisPerformedChoices(models.TextChoices):
        YES = 'Y', 'Yes'
        NO  = 'N', 'No'
        RECORD_DELETED = 'D', 'Record Deleted'  # System-managed label
        
    analysis_performed = models.TextField(
        blank=True,
        null=True,
        choices=AnalysisPerformedChoices.choices,
        verbose_name="Analysis Performed?"
    )

    def clean(self):
        super().clean()
        if hasattr(self, "animal_id") and self.animal_id and self.acquisition_date and self.measurement_unit_ranges:
            validate_non_overlapping_session_units(
                model_class=ImagingSession,
                animal=self.animal,
                session_date=self.acquisition_date,
                unit_range_str=self.measurement_unit_ranges,
                date_field_name="acquisition_date",
                unit_field_name="measurement_unit_ranges",
                exclude_pk=self.pk,
                model_name="imaging session",
            )

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if not update_fields or any(f in update_fields for f in ("animal", "animal_id", "acquisition_date", "measurement_unit_ranges")):
            self.clean()
        super().save(*args, **kwargs)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Imaging Session"
        verbose_name_plural = "Imaging Sessions"
        ordering = ["-acquisition_date"]

    def __str__(self):
        if self.measurement_unit_ranges:
            return f"{self.animal.animal_id} - {self.acquisition_date} ({self.measurement_unit_ranges})"
        return f"{self.animal.animal_id} - {self.acquisition_date}"


class TrackChanges(models.Model):

    class CategoryChoices(models.TextChoices):
        IMAGING_SESSION = "imaging_session", "Imaging Session"

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
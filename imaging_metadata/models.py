from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from animals_metadata.utils import (
    is_same_mesc_file,
    parse_unit_ranges,
    validate_measurement_unit_ranges,
)


class MouseImagingRecord(models.Model):
    animal = models.OneToOneField(
        "animals_metadata.Animal",
        on_delete=models.CASCADE,
        related_name="imaging_record",
        verbose_name="Animal ID",
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Imaging Record"
        verbose_name_plural = "Imaging Records"
        ordering = ["animal__animal_id"]

    def __str__(self):
        return f"{self.animal.animal_id}"


class ImagingSession(models.Model):
    tracker = models.ForeignKey(
        MouseImagingRecord,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name="Imaging Record",
        null=True,
        blank=True,
    )

    animal = models.ForeignKey(
        "animals_metadata.Animal",
        on_delete=models.PROTECT,
        related_name="imaging_sessions",
        null=True,
        blank=True,
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
        if hasattr(self, "tracker") and self.tracker and not (hasattr(self, "animal") and self.animal):
            self.animal = self.tracker.animal
        super().clean()
        if (
            hasattr(self, "animal_id")
            and self.animal_id
            and self.acquisition_date
            and self.mesc_file_path
            and self.measurement_unit_ranges
        ):
            current_units = parse_unit_ranges(self.measurement_unit_ranges)
            existing_sessions = ImagingSession.objects.filter(
                animal=self.animal,
                acquisition_date=self.acquisition_date,
            )
            if self.pk:
                existing_sessions = existing_sessions.exclude(pk=self.pk)

            for other in existing_sessions:
                if is_same_mesc_file(self.mesc_file_path, other.mesc_file_path):
                    other_units = parse_unit_ranges(other.measurement_unit_ranges)
                    if current_units == other_units:
                        filename = Path(self.mesc_file_path).name or self.mesc_file_path
                        raise ValidationError({
                            "measurement_unit_ranges": (
                                f"The MESC file '{filename}' is already registered for animal '{self.animal}' "
                                f"on {self.acquisition_date} with the same unit numbers ({self.measurement_unit_ranges}). "
                                f"Uploading the same file with identical unit numbers is not allowed."
                            )
                        })

    def save(self, *args, **kwargs):
        if self.tracker_id and not self.animal_id:
            self.animal = self.tracker.animal
        elif self.animal_id and not self.tracker_id:
            tracker, _ = MouseImagingRecord.objects.get_or_create(animal=self.animal)
            self.tracker = tracker
        update_fields = kwargs.get("update_fields")
        if not update_fields or any(
            f in update_fields
            for f in (
                "animal",
                "animal_id",
                "tracker",
                "tracker_id",
                "acquisition_date",
                "mesc_file_path",
                "measurement_unit_ranges",
            )
        ):
            self.clean()
        super().save(*args, **kwargs)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Imaging Session"
        verbose_name_plural = "Imaging Sessions"
        ordering = ["-acquisition_date"]

    def __str__(self):
        if self.measurement_unit_ranges:
            return f"{self.animal.animal_id if self.animal else 'Unknown'} - {self.acquisition_date} ({self.measurement_unit_ranges})"
        return f"{self.animal.animal_id if self.animal else 'Unknown'} - {self.acquisition_date}"


class TrackChanges(models.Model):

    class CategoryChoices(models.TextChoices):
        IMAGING_SESSION = "imaging_session", "Imaging Session"
        MOUSE_IMAGING = "mouse_imaging", "Imaging Record"

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
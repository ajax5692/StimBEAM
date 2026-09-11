from django.db import models
from simple_history.models import HistoricalRecords

from animals_metadata.models import Animal


class Virus(models.Model):
    virus_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Virus ID",
    )

    viral_construct = models.CharField(
        max_length=255,
        verbose_name="Viral Construct",
    )

    titre = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Titre",
    )

    location_in_fridge = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Location in -80°C Fridge",
    )

    virus_owner = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Virus Owner"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Virus"
        verbose_name_plural = "Viruses"
        ordering = ["virus_id"]

    def __str__(self):
        return f"{self.virus_id} ({self.viral_construct})"


class TrackChanges(models.Model):

    class CategoryChoices(models.TextChoices):
        VIRUS = "virus", "Virus"

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
        verbose_name="Virus ID",
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


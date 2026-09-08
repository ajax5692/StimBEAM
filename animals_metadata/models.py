from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


class Animal(models.Model):
    
    class SexChoices(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE  = 'F', 'Female'
        
    class OwnerChoices(models.TextChoices):
        AC = 'AC', 'Abhrajyoti'
        TB  = 'TB', 'Balázs'
        VK = 'VK', 'Varada'
        
    class GenotypeChoices(models.TextChoices):
        TC = 'Thy1-Cre', 'Thy1-Cre'
        TG = 'Thy1-gcamp6s', 'Thy1/gcamp6s (Tg)'
        
    class StatusChoices(models.TextChoices):
        ALIVE = 'Alive', 'Alive'
        DEAD  = 'Dead', 'Dead'
        
    class PipelineStageChoices(models.TextChoices):
        INTAKE = 'Intake', 'Intake'
        VISION_CHECK = 'Vision Check', 'Vision Check'
        VIRUS_INJECTION = 'Virus Injection', 'Virus Injection'
        SURGERY = 'Surgery', 'Surgery'
        BEHAVIOR_TRAINING = 'Behavior Training', 'Behavior Training'
        FINISHED = 'Finished', 'Finished'
        CULLED = 'Culled', 'Culled'


    animal_id = models.CharField(max_length=10,unique=True,verbose_name="Animal ID")
    owner = models.CharField(max_length=100,choices=OwnerChoices.choices, null=True, blank=True)
    sex = models.CharField(max_length=100,choices=SexChoices.choices)
    genotype = models.CharField(max_length=100,choices=GenotypeChoices.choices)
    cage_id = models.CharField(max_length=100, null=True, blank=True,verbose_name="Cage ID")
    ogr_id = models.CharField(max_length=100, null=True, blank=True,verbose_name="OGR ID")
    project_id = models.CharField(max_length=100, null=True, blank=True,verbose_name="Project ID")
    status = models.CharField(max_length=100,choices=StatusChoices.choices, null=True, blank=True)
    pipeline_stage = models.CharField(max_length=100,choices=PipelineStageChoices.choices, null=True, blank=True)
    
    dob = models.DateField(verbose_name="Date of Birth")
    @property
    def age_in_days(self):
        if not self.dob:
            return "N/A"
        today = timezone.now().date()
        return (today - self.dob).days
    
    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "Animal"
        verbose_name_plural = "Animals"
        
    def __str__(self):
        return self.animal_id
    
class VisionCheck(models.Model):

    class PassFailChoices(models.TextChoices):
        PASS = 'P', 'Pass'
        FAIL  = 'F', 'Fail' 

    class TestChoices(models.TextChoices):
        SWEEP = 'SweepTest', 'Vision Sweep Test'
        QOMR = 'qOMR', 'qOMR'
        
    animal_id = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        verbose_name="Animal ID"
    )
    
    vision_test_type = models.CharField(max_length=10,choices=TestChoices.choices)
    vision_test_result = models.CharField(max_length=10,choices=PassFailChoices.choices)
    data_path = models.CharField(blank=True, null=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Vision Check"
        verbose_name_plural = "Vision Checks"

    def __str__(self):
        return f"{self.animal_id}"
    
class ViralInjection(models.Model):

    animal_id = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
    )

    class InjectionSiteChoices(models.TextChoices):
        V1 = "V1", "V1"

    # ---------------------------------------------------------
    # VIRUS 1
    # ---------------------------------------------------------

    virus_id = models.ForeignKey(
        "virus_metadata.Virus",
        to_field="virus_id",
        on_delete=models.PROTECT,
        verbose_name="Virus ID 1",
        related_name="viral_injections_1",
    )

    volume_ul = models.FloatField(
        verbose_name="Volume 1 (nL)",
    )

    site = models.CharField(
        max_length=100,
        choices=InjectionSiteChoices.choices,
        blank=True,
        null=True,
        verbose_name="Injection Site 1",
    )

    depth = models.FloatField(
        verbose_name="Depth 1 (μm)",
        blank=True,
        null=True,
    )


    # ---------------------------------------------------------
    # VIRUS 2
    # ---------------------------------------------------------

    virus_id_2 = models.ForeignKey(
        "virus_metadata.Virus",
        to_field="virus_id",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name="Virus ID 2",
        related_name="viral_injections_2",
    )

    volume_nl_2 = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Volume 2 (nL)",
    )

    site_2 = models.CharField(
        max_length=100,
        choices=InjectionSiteChoices.choices,
        blank=True,
        null=True,
        verbose_name="Injection Site 2",
    )

    depth_2 = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Depth 2 (μm)",
    )


    # ---------------------------------------------------------
    # VIRUS 3
    # ---------------------------------------------------------

    virus_id_3 = models.ForeignKey(
        "virus_metadata.Virus",
        to_field="virus_id",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name="Virus ID 3",
        related_name="viral_injections_3",
    )

    volume_nl_3 = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Volume 3 (nL)",
    )

    site_3 = models.CharField(
        max_length=100,
        choices=InjectionSiteChoices.choices,
        blank=True,
        null=True,
        verbose_name="Injection Site 3",
    )

    depth_3 = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Depth 3 (μm)",
    )
    # ---------------------------------------------------------
    # INJECTION METADATA
    # ---------------------------------------------------------

    injection_date = models.DateField(
        verbose_name="Inj. Date",
    )

    injecting_person = models.CharField(
        max_length=100,
        choices=Animal.OwnerChoices.choices,
        null=True,
        blank=True,
    )

    surgery_date = models.DateField(
        null=True,
        blank=True,
    )

    surgery_person = models.CharField(
        max_length=100,
        choices=Animal.OwnerChoices.choices,
        null=True,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    expression = models.TextField(
        blank=True,
        null=True,
        verbose_name="Expression (Checkup MESc file)",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Viral Injections"
        verbose_name_plural = "Viral Injections"

    def __str__(self):
        return f"{self.animal_id}"

class TrackChanges(models.Model):

    class CategoryChoices(models.TextChoices):
        ANIMAL = "animal", "Animal"
        VISION_CHECK = "vision_check", "Vision Check"
        VIRAL_INJECTION = "viral_injection", "Viral Injection"

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
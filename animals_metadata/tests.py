from django.test import TestCase
from django.utils import timezone

from virus_metadata.models import Virus
from .models import Animal, TrackChanges, ViralInjection, VisionCheck


class AnimalsMetadataTrackChangesTest(TestCase):
    def setUp(self):
        self.virus1 = Virus.objects.create(
            virus_id="AAV322",
            viral_construct="AAV9-hSyn-DIO-jGCaMP8s",
            titre="1.5x10^13",
            location_in_fridge="Box 1",
            virus_owner="AC",
        )
        self.virus2 = Virus.objects.create(
            virus_id="AAV418",
            viral_construct="AAV9-hSyn-DIO-ChrimsonR",
            titre="2.0x10^13",
            location_in_fridge="Box 2",
            virus_owner="TB",
        )
        self.animal = Animal.objects.create(
            animal_id="ANM01",
            sex="M",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
        )

    def test_viral_injection_with_virus_foreign_key(self):
        # Create ViralInjection
        inj = ViralInjection.objects.create(
            animal_id=self.animal,
            virus_id=self.virus1,
            volume_ul=100.0,
            site="V1",
            depth=300.0,
            virus_id_2=self.virus2,
            volume_nl_2=50.0,
            site_2="V1",
            depth_2=350.0,
            injection_date=timezone.now().date(),
        )
        self.assertEqual(inj.virus_id.virus_id, "AAV322")
        self.assertEqual(inj.virus_id_2.virus_id, "AAV418")
        tc_create = TrackChanges.objects.filter(animal_id="ANM01", category=TrackChanges.CategoryChoices.VIRAL_INJECTION).first()
        self.assertIsNotNone(tc_create)
        self.assertIn("Initial Entry", tc_create.changes)
        self.assertIn("virus_id: 'AAV322 (AAV9-hSyn-DIO-jGCaMP8s)'", tc_create.changes)
        self.assertEqual(TrackChanges.objects.filter(animal_id="ANM01", category=TrackChanges.CategoryChoices.VIRAL_INJECTION).count(), 1)

        # Update
        inj.depth = 320.0
        inj.save()
        self.assertEqual(TrackChanges.objects.filter(animal_id="ANM01", category=TrackChanges.CategoryChoices.VIRAL_INJECTION).count(), 2)

        # Delete
        inj.delete()
        self.assertEqual(TrackChanges.objects.filter(animal_id="ANM01", category=TrackChanges.CategoryChoices.VIRAL_INJECTION).count(), 3)

    def test_dynamic_navigation_context(self):
        from django.contrib.auth import get_user_model
        from django.test import Client, RequestFactory
        from PStim_DAP.context_processors import enabled_apps

        factory = RequestFactory()
        req = factory.get("/admin/")
        context = enabled_apps(req)
        self.assertIn("installed_apps", context)
        self.assertTrue(context["installed_apps"].get("animals_metadata"))
        self.assertTrue(context["installed_apps"].get("virus_metadata"))

        User = get_user_model()
        user = User.objects.create_superuser("adminuser", "admin@example.com", "password")
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)

        res = client.get("/admin/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "ANIMALS METADATA")
        self.assertContains(res, "VIRUS METADATA")

    def test_mouse_tracker_water_restricted_count(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        from training_metadata.models import MouseBodyWeight

        # Clean existing animals
        Animal.objects.all().delete()

        # 1. Create inactive / finished / culled / dead animals with water restriction logged
        dead_animal = Animal.objects.create(
            animal_id="DEAD01",
            sex="M",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
            status=Animal.StatusChoices.DEAD,
            pipeline_stage=Animal.PipelineStageChoices.FINISHED,
        )
        MouseBodyWeight.objects.create(
            animal=dead_animal,
            water_restriction_start_date=timezone.now().date(),
        )

        culled_animal = Animal.objects.create(
            animal_id="CULL01",
            sex="F",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
            status=Animal.StatusChoices.ALIVE,
            pipeline_stage=Animal.PipelineStageChoices.CULLED,
        )
        MouseBodyWeight.objects.create(
            animal=culled_animal,
            water_restriction_start_date=timezone.now().date(),
        )

        User = get_user_model()
        user, _ = User.objects.get_or_create(username="adminuser2", defaults={"is_superuser": True, "is_staff": True})
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)

        res = client.get("/admin/tracker/")
        self.assertEqual(res.status_code, 200)
        # When active_mice is 0, water_restricted must be 0
        self.assertEqual(res.context["active_mice"], 0)
        self.assertEqual(res.context["water_restricted_mice"], 0)

        # 2. Add an active animal in Surgery (not in training)
        surg_animal = Animal.objects.create(
            animal_id="SURG01",
            sex="M",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
            status=Animal.StatusChoices.ALIVE,
            pipeline_stage=Animal.PipelineStageChoices.SURGERY,
        )
        res = client.get("/admin/tracker/")
        self.assertEqual(res.context["active_mice"], 1)
        self.assertEqual(res.context["water_restricted_mice"], 0)

        # 3. Add an active animal in Behavior Training
        train_animal = Animal.objects.create(
            animal_id="TRAIN01",
            sex="M",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
            status=Animal.StatusChoices.ALIVE,
            pipeline_stage=Animal.PipelineStageChoices.BEHAVIOR_TRAINING,
        )
        res = client.get("/admin/tracker/")
        self.assertEqual(res.context["active_mice"], 2)
        self.assertEqual(res.context["water_restricted_mice"], 1)




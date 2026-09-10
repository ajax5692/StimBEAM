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

        res = client.get("/admin/", follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Animals Metadata")
        self.assertContains(res, "Virus Metadata")

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
        self.assertContains(res, 'id="user-tools"')
        self.assertContains(res, "adminuser2")
        self.assertContains(res, "Log out")



class MouseTrackerServiceTest(TestCase):
    def setUp(self):
        self.today = timezone.now().date()
        self.animal = Animal.objects.create(
            animal_id="SERV01",
            sex="M",
            genotype="Thy1-Cre",
            dob=self.today,
            status=Animal.StatusChoices.ALIVE,
            pipeline_stage=Animal.PipelineStageChoices.BEHAVIOR_TRAINING,
        )

    def test_pipeline_distribution_calculation(self):
        from animals_metadata.services import MouseTrackerService

        sample_data = [
            {"animal_id": "M01", "pipeline_stage": "Intake", "status": "Alive"},
            {"animal_id": "M02", "pipeline_stage": "Vision Check", "status": "Alive"},
            {"animal_id": "M03", "pipeline_stage": "Behavior Training", "status": "Alive"},
            {"animal_id": "M04", "pipeline_stage": "Culled", "status": "Culled"},
        ]

        dist = MouseTrackerService.compute_pipeline_distribution(sample_data)
        self.assertEqual(len(dist), len(MouseTrackerService.PIPELINE_STAGES))

        dist_dict = {d["stage"]: d for d in dist}
        self.assertEqual(dist_dict["Intake"]["count"], 1)
        self.assertEqual(dist_dict["Intake"]["animals"], ["M01"])
        self.assertEqual(dist_dict["Vision Check"]["count"], 1)
        self.assertEqual(dist_dict["Vision Check"]["animals"], ["M02"])
        self.assertEqual(dist_dict["Behavior Training"]["count"], 1)
        self.assertEqual(dist_dict["Behavior Training"]["animals"], ["M03"])
        self.assertEqual(dist_dict["Culled"]["count"], 1)
        self.assertEqual(dist_dict["Culled"]["animals"], ["M04"])
        self.assertEqual(dist_dict["Surgery"]["count"], 0)

    def test_water_restriction_string_formatting(self):
        from datetime import timedelta
        from animals_metadata.services import MouseTrackerService

        # Active & started 5 days ago
        start_date = self.today - timedelta(days=4)
        s = MouseTrackerService.calculate_restriction_string(True, start_date, self.today)
        self.assertEqual(s, f"Day 5 (Since {start_date})")

        # Active & no date set
        s_nodate = MouseTrackerService.calculate_restriction_string(True, None, self.today)
        self.assertEqual(s_nodate, "Active Training (Date not set)")

        # Inactive & prior start date
        s_inactive = MouseTrackerService.calculate_restriction_string(False, start_date, self.today)
        self.assertEqual(s_inactive, f"Not on restriction (Prior start: {start_date})")

        # Inactive & no start date
        s_none = MouseTrackerService.calculate_restriction_string(False, None, self.today)
        self.assertEqual(s_none, "Not on restriction")

    def test_tracker_dashboard_context_generation(self):
        from animals_metadata.services import MouseTrackerService

        context = MouseTrackerService.get_tracker_dashboard_context(today=self.today)
        self.assertIn("animals_data", context)
        self.assertIn("animals_json", context)
        self.assertIn("pipeline_distribution", context)
        self.assertIn("recent_activity", context)
        self.assertEqual(context["total_mice"], 1)
        self.assertEqual(context["active_mice"], 1)
        self.assertEqual(context["water_restricted_mice"], 1)





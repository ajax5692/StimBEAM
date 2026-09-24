import os
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from animals_metadata.models import Animal
from .models import BodyWeightEntry, MouseBodyWeight, TrackChanges, TrainingSession
from .services import (
    claim_next_pending_training_session,
    execute_training_analysis,
    process_next_training_analysis,
)


class TrainingSessionTrackChangesTest(TestCase):
    def setUp(self):
        self.animal = Animal.objects.create(
            animal_id="TRN01",
            sex="M",
            genotype="Thy1-gcamp6s",
            dob=timezone.now().date(),
        )

    def test_track_changes_lifecycle(self):
        # Create
        session = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path="/data/bpod.mat",
            training_unit_range="1:10",
        )
        self.assertEqual(TrackChanges.objects.filter(animal_id="TRN01").count(), 1)
        create_record = TrackChanges.objects.filter(animal_id="TRN01").first()
        self.assertEqual(create_record.action, "+")
        self.assertEqual(create_record.category, TrackChanges.CategoryChoices.TRAINING_SESSION)
        self.assertIn("Initial Entry", create_record.changes)
        self.assertIn("bpod_file_path: '/data/bpod.mat'", create_record.changes)

        # Update
        session.notes = "Updated training notes"
        session.save()
        self.assertEqual(TrackChanges.objects.filter(animal_id="TRN01").count(), 2)
        update_record = TrackChanges.objects.filter(animal_id="TRN01").first()
        self.assertEqual(update_record.action, "~")
        self.assertIn("notes", update_record.changes)

        # Delete
        session.delete()
        self.assertEqual(TrackChanges.objects.filter(animal_id="TRN01").count(), 3)
        delete_record = TrackChanges.objects.filter(animal_id="TRN01").first()
        self.assertEqual(delete_record.action, "-")
        self.assertEqual(delete_record.changes, "Deleted Record")

    def test_mouse_body_weight_lifecycle_and_auto_calculation(self):
        base_date = timezone.now().date()

        # Create Tracker
        tracker = MouseBodyWeight.objects.create(animal=self.animal)
        self.assertEqual(
            TrackChanges.objects.filter(
                animal_id="TRN01",
                category=TrackChanges.CategoryChoices.MOUSE_BODY_WEIGHT,
            ).count(),
            1,
        )

        # Day 1: Start weight = 25.0g (100.0%)
        entry1 = BodyWeightEntry.objects.create(
            tracker=tracker,
            date=base_date,
            body_weight_g=25.0,
            notes="Baseline weight",
        )
        self.assertEqual(entry1.percent_body_weight, 100.0)

        # Day 2: Entered weight = 24.0g (96.0%)
        entry2 = BodyWeightEntry.objects.create(
            tracker=tracker,
            date=base_date + timedelta(days=1),
            body_weight_g=24.0,
            notes="Day 2 training",
        )
        self.assertEqual(entry2.percent_body_weight, 96.0)

        # Day 3: Entered weight = 22.5g (90.0%)
        entry3 = BodyWeightEntry.objects.create(
            tracker=tracker,
            date=base_date + timedelta(days=2),
            body_weight_g=22.5,
            notes="Day 3 training",
        )
        self.assertEqual(entry3.percent_body_weight, 90.0)

        # Update entry2 notes and weight
        entry2.notes = "Day 2 notes updated"
        entry2.save()
        self.assertIn(
            "notes",
            TrackChanges.objects.filter(
                animal_id="TRN01",
                category=TrackChanges.CategoryChoices.MOUSE_BODY_WEIGHT,
            ).first().changes,
        )

        # Delete entry3
        entry3.delete()
        delete_track = TrackChanges.objects.filter(
            animal_id="TRN01",
            category=TrackChanges.CategoryChoices.MOUSE_BODY_WEIGHT,
            action="-",
        ).first()
        self.assertIsNotNone(delete_track)


class TrainingAnalysisServiceAndAdminTest(TestCase):
    def setUp(self):
        self.animal = Animal.objects.create(
            animal_id="m67",
            sex="M",
            genotype="Thy1-gcamp6s",
            dob=timezone.now().date(),
        )
        self.user = get_user_model().objects.create_superuser(
            username="admin_test",
            email="admin@example.com",
            password="testpassword123",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_status_lifecycle_and_service_execution(self):
        test_mat_path = r"C:\Users\abhrajyoti.chakrabarti\Desktop\64gb_usb_dump\TrainingData\m67_new_VisGo_GoProb_Train_measure_20250926_132921.mat"

        session = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path=test_mat_path if os.path.exists(test_mat_path) else "dummy.mat",
            training_unit_range="10:21",
        )
        self.assertEqual(session.status, TrainingSession.StatusChoices.PENDING)

        # Test claiming
        claimed = claim_next_pending_training_session()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.pk, session.pk)
        self.assertEqual(claimed.status, TrainingSession.StatusChoices.RUNNING)

        if os.path.exists(test_mat_path):
            with tempfile.TemporaryDirectory() as tmpdir:
                execute_training_analysis(claimed, output_dir=tmpdir)
                claimed.refresh_from_db()
                self.assertEqual(claimed.status, TrainingSession.StatusChoices.COMPLETED)
                self.assertTrue(bool(claimed.output_plot_path))
                self.assertTrue(bool(claimed.output_raster_path))
                self.assertTrue(bool(claimed.output_excel_path))
                self.assertIn("n_trials", claimed.metrics_json)
                self.assertEqual(claimed.metrics_json["n_trials"], 12)
                self.assertIn("d_prime", claimed.metrics_json)
                self.assertIn("hit_rate", claimed.metrics_json)
                self.assertIn("false_alarm_rate", claimed.metrics_json)
                self.assertAlmostEqual(claimed.metrics_json["d_prime"], 1.163, places=2)

    def test_d_prime_calculation_with_unit_range_3_174(self):
        test_mat_path = r"C:\Users\abhrajyoti.chakrabarti\Desktop\64gb_usb_dump\TrainingData\m67_new_VisGo_GoProb_Train_measure_20250926_132921.mat"
        if not os.path.exists(test_mat_path):
            return

        session = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path=test_mat_path,
            training_unit_range="3:174",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            execute_training_analysis(session, output_dir=tmpdir)
            session.refresh_from_db()
            self.assertEqual(session.status, TrainingSession.StatusChoices.COMPLETED)
            m = session.metrics_json
            self.assertEqual(m["n_trials"], 165)
            self.assertEqual(m["n_go_trials"], 92)
            self.assertEqual(m["n_nogo_trials"], 73)
            self.assertEqual(m["n_hits"], 60)
            self.assertEqual(m["n_false_alarms"], 7)
            self.assertAlmostEqual(m["hit_rate"], 60 / 92, places=3)
            self.assertAlmostEqual(m["false_alarm_rate"], 7 / 73, places=3)
            self.assertAlmostEqual(m["d_prime"], 1.661, places=2)

    def test_admin_lick_traces_view(self):
        session = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path="/data/test.mat",
            training_unit_range="1:10",
        )
        url = reverse("admin:training_session_lick_traces", args=[session.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Animal {self.animal.animal_id}")
        self.assertContains(response, "Average Licking Trace")

    def test_training_unit_range_validation(self):
        from django.core.exceptions import ValidationError

        # Valid formats should pass full_clean
        valid_session = TrainingSession(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path="/data/test.mat",
            training_unit_range="10:21, 25:55",
        )
        valid_session.full_clean()

        # Invalid format should raise ValidationError
        invalid_session = TrainingSession(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path="/data/test.mat",
            training_unit_range="10-21-30",
        )
        with self.assertRaises(ValidationError):
            invalid_session.full_clean()


class TrainingSessionUnitValidationTest(TestCase):
    def setUp(self):
        self.animal1 = Animal.objects.create(
            animal_id="TRN_TEST_1",
            sex="M",
            genotype="Thy1-gcamp6s",
            dob=timezone.now().date(),
        )
        self.animal2 = Animal.objects.create(
            animal_id="TRN_TEST_2",
            sex="F",
            genotype="Wildtype",
            dob=timezone.now().date(),
        )
        self.today = timezone.now().date()
        self.tomorrow = self.today + timezone.timedelta(days=1)

    def test_duplicate_session_exact_units_rejected(self):
        from django.core.exceptions import ValidationError

        TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="10:21",
        )

        duplicate = TrainingSession(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file2.mat",
            training_unit_range="10:21",
        )
        with self.assertRaises(ValidationError) as ctx:
            duplicate.full_clean()
        self.assertIn("training_unit_range", ctx.exception.message_dict)

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_overlapping_units_rejected(self):
        from django.core.exceptions import ValidationError

        TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="10:21",
        )

        # Overlaps at units 20, 21
        overlapping = TrainingSession(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file2.mat",
            training_unit_range="20:30",
        )
        with self.assertRaises(ValidationError) as ctx:
            overlapping.full_clean()
        self.assertIn("training_unit_range", ctx.exception.message_dict)
        self.assertIn("20", str(ctx.exception.message_dict["training_unit_range"]))

    def test_disjoint_units_same_date_allowed(self):
        s1 = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="1:10",
        )
        s2 = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file2.mat",
            training_unit_range="11:20",
        )
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_same_units_different_date_allowed(self):
        s1 = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="10:21",
        )
        s2 = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.tomorrow,
            bpod_file_path="/data/file2.mat",
            training_unit_range="10:21",
        )
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_same_units_different_animal_allowed(self):
        s1 = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="10:21",
        )
        s2 = TrainingSession.objects.create(
            animal=self.animal2,
            training_date=self.today,
            bpod_file_path="/data/file2.mat",
            training_unit_range="10:21",
        )
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_update_existing_session_allowed(self):
        session = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="10:21",
        )
        session.notes = "Updated notes"
        session.full_clean()
        session.save()
        session.refresh_from_db()
        self.assertEqual(session.notes, "Updated notes")



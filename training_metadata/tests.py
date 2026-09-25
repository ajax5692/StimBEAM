import os
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from animals_metadata.models import Animal
from .models import (
    BodyWeightEntry,
    MouseBodyWeight,
    MouseTrainingRecord,
    TrackChanges,
    TrainingSession,
)
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
        self.assertEqual(
            TrackChanges.objects.filter(
                animal_id="TRN01",
                category=TrackChanges.CategoryChoices.TRAINING_SESSION,
            ).count(),
            1,
        )
        create_record = TrackChanges.objects.filter(
            animal_id="TRN01",
            category=TrackChanges.CategoryChoices.TRAINING_SESSION,
        ).first()
        self.assertEqual(create_record.action, "+")
        self.assertEqual(create_record.category, TrackChanges.CategoryChoices.TRAINING_SESSION)
        self.assertIn("Initial Entry", create_record.changes)
        self.assertIn("bpod_file_path: '/data/bpod.mat'", create_record.changes)

        # Update
        session.notes = "Updated training notes"
        session.save()
        self.assertEqual(
            TrackChanges.objects.filter(
                animal_id="TRN01",
                category=TrackChanges.CategoryChoices.TRAINING_SESSION,
            ).count(),
            2,
        )
        update_record = TrackChanges.objects.filter(
            animal_id="TRN01",
            category=TrackChanges.CategoryChoices.TRAINING_SESSION,
        ).first()
        self.assertEqual(update_record.action, "~")
        self.assertIn("notes", update_record.changes)

        # Delete
        session.delete()
        self.assertEqual(
            TrackChanges.objects.filter(
                animal_id="TRN01",
                category=TrackChanges.CategoryChoices.TRAINING_SESSION,
            ).count(),
            3,
        )
        delete_record = TrackChanges.objects.filter(
            animal_id="TRN01",
            category=TrackChanges.CategoryChoices.TRAINING_SESSION,
        ).first()
        self.assertEqual(delete_record.action, "-")
        self.assertEqual(delete_record.changes, "Deleted Record")

    def test_mouse_training_record_lifecycle_and_auto_linking(self):
        session1 = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path="/data/bpod1.mat",
            training_unit_range="1:10",
        )
        self.assertIsNotNone(session1.tracker)
        self.assertEqual(session1.tracker.animal, self.animal)

        record = session1.tracker
        session2 = TrainingSession(
            tracker=record,
            training_date=timezone.now().date() + timedelta(days=1),
            bpod_file_path="/data/bpod2.mat",
            training_unit_range="1:10",
        )
        session2.save()
        self.assertEqual(session2.animal, self.animal)

        self.assertGreaterEqual(
            TrackChanges.objects.filter(
                animal_id="TRN01",
                category=TrackChanges.CategoryChoices.MOUSE_TRAINING,
            ).count(),
            1,
        )

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

    def test_duplicate_session_exact_units_same_file_rejected(self):
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
            bpod_file_path="/data/file1.mat",
            training_unit_range="10:21",
        )
        with self.assertRaises(ValidationError) as ctx:
            duplicate.full_clean()
        self.assertIn("training_unit_range", ctx.exception.message_dict)

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_overlapping_units_same_file_allowed(self):
        # Overlapping units (e.g. 3:20 and 11:16) for the same bpod file are allowed for testing
        s1 = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="3:20",
        )
        s2 = TrainingSession(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="11:16",
        )
        s2.full_clean()
        s2.save()
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_disjoint_units_same_file_allowed(self):
        s1 = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
            training_unit_range="1:10",
        )
        s2 = TrainingSession.objects.create(
            animal=self.animal1,
            training_date=self.today,
            bpod_file_path="/data/file1.mat",
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


class MouseTrainingRecordAdminTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.animal = Animal.objects.create(
            animal_id="TRN02",
            sex="F",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
            owner=self.admin_user,
        )
        self.client = Client()
        self.client.login(username="admin", password="password123")

    def test_navigation_dropdown_order_and_mice_options(self):
        bw_record = MouseBodyWeight.objects.create(animal=self.animal)
        trn_record = MouseTrainingRecord.objects.create(animal=self.animal)

        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        bw_pos = content.find("Body Weight Records")
        trn_pos = content.find("Training Records")
        self.assertNotEqual(bw_pos, -1)
        self.assertNotEqual(trn_pos, -1)
        self.assertLess(bw_pos, trn_pos)

        bw_mouse_link = f"/admin/training_metadata/mousebodyweight/{bw_record.pk}/change/"
        trn_mouse_link = f"/admin/training_metadata/mousetrainingrecord/{trn_record.pk}/change/"
        self.assertContains(response, bw_mouse_link)
        self.assertContains(response, trn_mouse_link)

    def test_app_index_model_ordering(self):
        url = reverse("admin:app_list", args=["training_metadata"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        app = response.context["app_list"][0]
        model_names = [m["name"] for m in app["models"]]
        expected_names = [
            "Body Weight Records",
            "Training Records",
            "Track Changes",
        ]
        self.assertEqual(model_names, expected_names)

    def test_owner_first_name_harmonized_across_training_and_body_weight(self):
        self.admin_user.first_name = "Alex"
        self.admin_user.save()

        bw_record = MouseBodyWeight.objects.create(animal=self.animal)
        trn_record = MouseTrainingRecord.objects.create(animal=self.animal)

        # Body weight changelist
        bw_cl_url = reverse("admin:training_metadata_mousebodyweight_changelist")
        bw_resp = self.client.get(bw_cl_url)
        self.assertEqual(bw_resp.status_code, 200)
        self.assertContains(bw_resp, "Alex")

        # Training record changelist
        trn_cl_url = reverse("admin:training_metadata_mousetrainingrecord_changelist")
        trn_resp = self.client.get(trn_cl_url)
        self.assertEqual(trn_resp.status_code, 200)
        self.assertContains(trn_resp, "Alex")

        # Body weight changeform
        bw_cf_url = reverse("admin:training_metadata_mousebodyweight_change", args=[bw_record.pk])
        bw_cf_resp = self.client.get(bw_cf_url)
        self.assertEqual(bw_cf_resp.status_code, 200)
        self.assertContains(bw_cf_resp, "Alex")

        # Training record changeform
        trn_cf_url = reverse("admin:training_metadata_mousetrainingrecord_change", args=[trn_record.pk])
        trn_cf_resp = self.client.get(trn_cf_url)
        self.assertEqual(trn_cf_resp.status_code, 200)
        self.assertContains(trn_cf_resp, "Alex")

    def test_mousetrainingrecord_changelist_and_change_views(self):
        session = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path="/data/bpod_test.mat",
            training_unit_range="1:15",
            status=TrainingSession.StatusChoices.COMPLETED,
            metrics_json={"d_prime": 1.75, "hit_rate": 0.8, "false_alarm_rate": 0.1},
        )
        record = session.tracker

        # Changelist
        changelist_url = reverse("admin:training_metadata_mousetrainingrecord_changelist")
        response = self.client.get(changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TRN02")
        self.assertContains(response, "1.75")
        self.assertContains(response, 'name="action"')
        self.assertContains(response, "action-select")

        # Change form
        change_url = reverse("admin:training_metadata_mousetrainingrecord_change", args=[record.pk])
        response = self.client.get(change_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bpod_test.mat")
        self.assertContains(response, 'class="pstim-copy-button"')
        self.assertContains(response, 'data-copy-text="/data/bpod_test.mat"')
        self.assertContains(response, "form-multiline")
        self.assertIsNone(response.context.get("subtitle"))
        self.assertNotContains(response, f"<h2>{record.animal.animal_id}</h2>")
        self.assertContains(response, "1:15")
        self.assertContains(response, "1.75")

    def test_add_session_via_admin_inline_post(self):
        record = MouseTrainingRecord.objects.create(animal=self.animal)
        change_url = reverse("admin:training_metadata_mousetrainingrecord_change", args=[record.pk])

        post_data = {
            "animal": self.animal.pk,
            "notes": "Tracker notes",
            "sessions-TOTAL_FORMS": "1",
            "sessions-INITIAL_FORMS": "0",
            "sessions-MIN_NUM_FORMS": "0",
            "sessions-MAX_NUM_FORMS": "1000",
            "sessions-0-training_date": str(timezone.now().date()),
            "sessions-0-bpod_file_path": "/data/inline_file.mat",
            "sessions-0-training_unit_range": "20:30",
            "sessions-0-notes": "Inline added note",
            "_save": "Save",
        }
        response = self.client.post(change_url, post_data)
        self.assertRedirects(response, change_url)

        record.refresh_from_db()
        self.assertEqual(record.sessions.count(), 1)
        created_session = record.sessions.first()
        self.assertEqual(created_session.animal, self.animal)
        self.assertEqual(created_session.bpod_file_path, "/data/inline_file.mat")
        self.assertEqual(created_session.training_unit_range, "20:30")

    def test_delete_individual_training_session_via_checkbox(self):
        session1 = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path="/data/file1.mat",
            training_unit_range="1:10",
        )
        session2 = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date() + timezone.timedelta(days=1),
            bpod_file_path="/data/file2.mat",
            training_unit_range="11:20",
        )
        record = session1.tracker
        self.assertEqual(record.sessions.count(), 2)

        # Check that change form renders Delete? checkbox column matching BodyWeightEntryInline
        change_url = reverse("admin:training_metadata_mousetrainingrecord_change", args=[record.pk])
        resp = self.client.get(change_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Delete?")
        self.assertContains(resp, 'name="sessions-0-DELETE"')
        self.assertContains(resp, 'name="sessions-1-DELETE"')
        inline_sessions = list(record.sessions.all())
        target_session = inline_sessions[0]
        surviving_session = inline_sessions[1]

        post_data = {
            "animal": self.animal.pk,
            "notes": "",
            "sessions-TOTAL_FORMS": "2",
            "sessions-INITIAL_FORMS": "2",
            "sessions-MIN_NUM_FORMS": "0",
            "sessions-MAX_NUM_FORMS": "1000",
            "sessions-0-id": str(inline_sessions[0].pk),
            "sessions-0-tracker": str(record.pk),
            "sessions-0-training_date": str(inline_sessions[0].training_date),
            "sessions-0-bpod_file_path": inline_sessions[0].bpod_file_path,
            "sessions-0-training_unit_range": inline_sessions[0].training_unit_range,
            "sessions-0-DELETE": "on",
            "sessions-1-id": str(inline_sessions[1].pk),
            "sessions-1-tracker": str(record.pk),
            "sessions-1-training_date": str(inline_sessions[1].training_date),
            "sessions-1-bpod_file_path": inline_sessions[1].bpod_file_path,
            "sessions-1-training_unit_range": inline_sessions[1].training_unit_range,
            "_save": "Save",
        }
        del_resp = self.client.post(change_url, post_data, follow=True)
        self.assertEqual(del_resp.status_code, 200)

        # Assert target session was deleted and surviving session remains
        self.assertFalse(TrainingSession.objects.filter(pk=target_session.pk).exists())
        self.assertTrue(TrainingSession.objects.filter(pk=surviving_session.pk).exists())
        self.assertEqual(record.sessions.count(), 1)
        self.assertTrue(MouseTrainingRecord.objects.filter(pk=record.pk).exists())

    def test_delete_individual_training_session_direct_view(self):
        session1 = TrainingSession.objects.create(
            animal=self.animal,
            training_date=timezone.now().date(),
            bpod_file_path="/data/file1.mat",
            training_unit_range="1:10",
        )
        record = session1.tracker
        delete_url = reverse("admin:training_delete_session", args=[record.pk, session1.pk])
        del_resp = self.client.get(delete_url, follow=True)
        self.assertEqual(del_resp.status_code, 200)
        self.assertContains(del_resp, "deleted successfully")
        self.assertFalse(TrainingSession.objects.filter(pk=session1.pk).exists())

    def test_same_bpod_file_different_units_triggers_admin_warning(self):
        record = MouseTrainingRecord.objects.create(animal=self.animal)
        change_url = reverse("admin:training_metadata_mousetrainingrecord_change", args=[record.pk])

        # Session 1 exists in DB
        TrainingSession.objects.create(
            animal=self.animal,
            tracker=record,
            training_date=timezone.now().date(),
            bpod_file_path="/data/shared_bpod.mat",
            training_unit_range="3:20",
        )

        # Upload session 2 with the same BPod file on the same date, but different unit numbers
        post_data = {
            "animal": self.animal.pk,
            "notes": "",
            "sessions-TOTAL_FORMS": "2",
            "sessions-INITIAL_FORMS": "1",
            "sessions-MIN_NUM_FORMS": "0",
            "sessions-MAX_NUM_FORMS": "1000",
            "sessions-0-id": str(record.sessions.first().pk),
            "sessions-0-tracker": str(record.pk),
            "sessions-0-training_date": str(timezone.now().date()),
            "sessions-0-bpod_file_path": "/data/shared_bpod.mat",
            "sessions-0-training_unit_range": "3:20",
            "sessions-1-training_date": str(timezone.now().date()),
            "sessions-1-bpod_file_path": "/data/shared_bpod.mat",
            "sessions-1-training_unit_range": "11:16",
            "_save": "Save",
        }
        resp = self.client.post(change_url, post_data, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(record.sessions.count(), 2)
        # Warning message should be present
        self.assertContains(resp, "shared_bpod.mat")
        self.assertContains(resp, "uploaded multiple times")

    def test_formset_duplicate_same_file_same_units_blocks_save(self):
        record = MouseTrainingRecord.objects.create(animal=self.animal)
        change_url = reverse("admin:training_metadata_mousetrainingrecord_change", args=[record.pk])

        # Submit two rows simultaneously with same file and identical units
        post_data = {
            "animal": self.animal.pk,
            "notes": "",
            "sessions-TOTAL_FORMS": "2",
            "sessions-INITIAL_FORMS": "0",
            "sessions-MIN_NUM_FORMS": "0",
            "sessions-MAX_NUM_FORMS": "1000",
            "sessions-0-training_date": str(timezone.now().date()),
            "sessions-0-bpod_file_path": "/data/test_dup.mat",
            "sessions-0-training_unit_range": "5:15",
            "sessions-1-training_date": str(timezone.now().date()),
            "sessions-1-bpod_file_path": "/data/test_dup.mat",
            "sessions-1-training_unit_range": "5:15",
            "_save": "Save",
        }
        resp = self.client.post(change_url, post_data)
        self.assertEqual(resp.status_code, 200)
        # Verify save was blocked and form error rendered
        self.assertEqual(record.sessions.count(), 0)
        self.assertContains(resp, "Duplicate session")
        self.assertContains(resp, "test_dup.mat")

    def test_include_in_mouse_tracker_filters_d_prime_history_and_profile(self):
        from animals_metadata.services import MouseTrackerService

        record = MouseTrainingRecord.objects.create(animal=self.animal)

        # Full session included in mouse tracker (default True)
        s_full = TrainingSession.objects.create(
            animal=self.animal,
            tracker=record,
            training_date=timezone.now().date() - timezone.timedelta(days=1),
            bpod_file_path="/data/file.mat",
            training_unit_range="3:174",
            status=TrainingSession.StatusChoices.COMPLETED,
            metrics_json={"d_prime": 1.85, "hit_rate": 0.85, "false_alarm_rate": 0.1},
            include_in_mouse_tracker=True,
        )

        # Subset troubleshooting session excluded from mouse tracker
        s_troubleshoot = TrainingSession.objects.create(
            animal=self.animal,
            tracker=record,
            training_date=timezone.now().date(),
            bpod_file_path="/data/file.mat",
            training_unit_range="5:50",
            status=TrainingSession.StatusChoices.COMPLETED,
            metrics_json={"d_prime": 0.50, "hit_rate": 0.50, "false_alarm_rate": 0.4},
            include_in_mouse_tracker=False,
        )

        preloaded = MouseTrackerService.preload_colony_data()
        profile = MouseTrackerService.build_animal_profile(self.animal, preloaded, timezone.now().date())

        # Assert only s_full is plotted in d_prime_history
        d_history_ids = [pt["session_id"] for pt in profile["d_prime_history"]]
        self.assertIn(s_full.pk, d_history_ids)
        self.assertNotIn(s_troubleshoot.pk, d_history_ids)

        # Assert change form renders column header 'include in mouse tracker?'
        change_url = reverse("admin:training_metadata_mousetrainingrecord_change", args=[record.pk])
        resp = self.client.get(change_url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("include in mouse tracker?", resp.content.decode("utf-8").lower())
        self.assertContains(resp, "include_in_mouse_tracker")



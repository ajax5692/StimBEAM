from django.test import TestCase
from django.utils import timezone

from animals_metadata.models import Animal
from .models import ImagingSession, TrackChanges


class ImagingSessionTrackChangesTest(TestCase):
    def setUp(self):
        self.animal = Animal.objects.create(
            animal_id="IMG01",
            sex="M",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
        )

    def test_track_changes_lifecycle(self):
        # Create
        session = ImagingSession.objects.create(
            animal=self.animal,
            acquisition_date=timezone.now().date(),
            imaging_region="V1",
            mesc_file_path="/data/file.mesc",
            measurement_unit_ranges="1:10",
        )
        self.assertEqual(TrackChanges.objects.filter(animal_id="IMG01", category=TrackChanges.CategoryChoices.IMAGING_SESSION).count(), 1)
        create_record = TrackChanges.objects.filter(animal_id="IMG01", category=TrackChanges.CategoryChoices.IMAGING_SESSION).first()
        self.assertEqual(create_record.action, "+")
        self.assertEqual(create_record.category, TrackChanges.CategoryChoices.IMAGING_SESSION)
        self.assertIn("Initial Entry", create_record.changes)
        self.assertIn("imaging_region: 'V1'", create_record.changes)

        # Update
        session.imaging_region = "V2"
        session.save()
        self.assertEqual(TrackChanges.objects.filter(animal_id="IMG01", category=TrackChanges.CategoryChoices.IMAGING_SESSION).count(), 2)
        update_record = TrackChanges.objects.filter(animal_id="IMG01", category=TrackChanges.CategoryChoices.IMAGING_SESSION).first()
        self.assertEqual(update_record.action, "~")
        self.assertIn("imaging_region", update_record.changes)

        # Delete
        session.delete()
        self.assertEqual(TrackChanges.objects.filter(animal_id="IMG01", category=TrackChanges.CategoryChoices.IMAGING_SESSION).count(), 3)
        delete_record = TrackChanges.objects.filter(animal_id="IMG01").first()
        self.assertEqual(delete_record.action, "-")
        self.assertEqual(delete_record.changes, "Deleted Record")


class ImagingSessionUnitValidationTest(TestCase):
    def setUp(self):
        self.animal1 = Animal.objects.create(
            animal_id="IMG_TEST_1",
            sex="M",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
        )
        self.animal2 = Animal.objects.create(
            animal_id="IMG_TEST_2",
            sex="F",
            genotype="Wildtype",
            dob=timezone.now().date(),
        )
        self.today = timezone.now().date()
        self.tomorrow = self.today + timezone.timedelta(days=1)

    def test_duplicate_session_exact_units_rejected(self):
        from django.core.exceptions import ValidationError

        ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )

        duplicate = ImagingSession(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )
        with self.assertRaises(ValidationError) as ctx:
            duplicate.full_clean()
        self.assertIn("measurement_unit_ranges", ctx.exception.message_dict)

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_overlapping_units_same_file_allowed(self):
        s1 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )

        # Overlapping units (20, 21) on same file are now allowed to save
        s2 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="20:30",
        )
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_different_file_same_units_allowed(self):
        s1 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )
        s2 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file2.mesc",
            measurement_unit_ranges="10:21",
        )
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_disjoint_units_same_date_allowed(self):
        s1 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="1:10",
        )
        s2 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="11:20",
        )
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_same_units_different_date_allowed(self):
        s1 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )
        s2 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.tomorrow,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_same_units_different_animal_allowed(self):
        s1 = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )
        s2 = ImagingSession.objects.create(
            animal=self.animal2,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )
        self.assertIsNotNone(s1.pk)
        self.assertIsNotNone(s2.pk)

    def test_update_existing_session_allowed(self):
        session = ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )
        session.imaging_region = "V1"
        session.notes = "Updated notes"
        session.full_clean()
        session.save()
        session.refresh_from_db()
        self.assertEqual(session.notes, "Updated notes")


class MouseImagingRecordAdminTest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_superuser(
            username="admin_img",
            email="admin_img@example.com",
            password="password123",
            first_name="Admin",
            last_name="User",
        )
        self.client.force_login(self.user)
        self.animal = Animal.objects.create(
            animal_id="M_IMG_TEST",
            sex="M",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
            owner=self.user,
        )

    def test_mouseimagingrecord_changelist_and_change_views(self):
        from django.urls import reverse
        from .models import MouseImagingRecord

        record, _ = MouseImagingRecord.objects.get_or_create(animal=self.animal)
        session = ImagingSession.objects.create(
            animal=self.animal,
            tracker=record,
            acquisition_date=timezone.now().date(),
            mesc_file_path="/data/sample.mesc",
            measurement_unit_ranges="10:21",
        )
        changelist_url = reverse("admin:imaging_metadata_mouseimagingrecord_changelist")
        resp = self.client.get(changelist_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.animal.animal_id)

        change_url = reverse("admin:imaging_metadata_mouseimagingrecord_change", args=[record.pk])
        resp_change = self.client.get(change_url)
        self.assertEqual(resp_change.status_code, 200)
        self.assertContains(resp_change, "sessions-0-measurement_unit_ranges")

    def test_same_mesc_file_different_units_triggers_admin_warning(self):
        from django.urls import reverse
        from .models import MouseImagingRecord

        record, _ = MouseImagingRecord.objects.get_or_create(animal=self.animal)
        change_url = reverse("admin:imaging_metadata_mouseimagingrecord_change", args=[record.pk])

        # Session 1 exists in DB
        ImagingSession.objects.create(
            animal=self.animal,
            tracker=record,
            acquisition_date=timezone.now().date(),
            mesc_file_path="/data/shared_img.mesc",
            measurement_unit_ranges="3:20",
        )

        # Upload session 2 with the same MESC file on the same date, but overlapping unit numbers
        post_data = {
            "animal": self.animal.pk,
            "notes": "",
            "sessions-TOTAL_FORMS": "2",
            "sessions-INITIAL_FORMS": "1",
            "sessions-MIN_NUM_FORMS": "0",
            "sessions-MAX_NUM_FORMS": "1000",
            "sessions-0-id": str(record.sessions.first().pk),
            "sessions-0-tracker": str(record.pk),
            "sessions-0-acquisition_date": str(timezone.now().date()),
            "sessions-0-mesc_file_path": "/data/shared_img.mesc",
            "sessions-0-measurement_unit_ranges": "3:20",
            "sessions-1-acquisition_date": str(timezone.now().date()),
            "sessions-1-mesc_file_path": "/data/shared_img.mesc",
            "sessions-1-measurement_unit_ranges": "11:16",
            "_save": "Save",
        }
        resp = self.client.post(change_url, post_data, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(record.sessions.count(), 2)
        # Warning message should be present
        self.assertContains(resp, "shared_img.mesc")
        self.assertContains(resp, "uploaded multiple times")

    def test_formset_duplicate_same_file_same_units_blocks_save(self):
        from django.urls import reverse
        from .models import MouseImagingRecord

        record, _ = MouseImagingRecord.objects.get_or_create(animal=self.animal)
        change_url = reverse("admin:imaging_metadata_mouseimagingrecord_change", args=[record.pk])

        # Submit two rows simultaneously with same file and identical units
        post_data = {
            "animal": self.animal.pk,
            "notes": "",
            "sessions-TOTAL_FORMS": "2",
            "sessions-INITIAL_FORMS": "0",
            "sessions-MIN_NUM_FORMS": "0",
            "sessions-MAX_NUM_FORMS": "1000",
            "sessions-0-acquisition_date": str(timezone.now().date()),
            "sessions-0-mesc_file_path": "/data/test_dup.mesc",
            "sessions-0-measurement_unit_ranges": "5:15",
            "sessions-1-acquisition_date": str(timezone.now().date()),
            "sessions-1-mesc_file_path": "/data/test_dup.mesc",
            "sessions-1-measurement_unit_ranges": "5:15",
            "_save": "Save",
        }
        resp = self.client.post(change_url, post_data)
        self.assertEqual(resp.status_code, 200)
        # Verify save was blocked and form error rendered
        self.assertEqual(record.sessions.count(), 0)
        self.assertContains(resp, "Duplicate session")
        self.assertContains(resp, "test_dup.mesc")

    def test_delete_session_view(self):
        from django.urls import reverse
        from .models import MouseImagingRecord

        record, _ = MouseImagingRecord.objects.get_or_create(animal=self.animal)
        session = ImagingSession.objects.create(
            animal=self.animal,
            tracker=record,
            acquisition_date=timezone.now().date(),
            mesc_file_path="/data/to_del.mesc",
            measurement_unit_ranges="1:10",
        )
        del_url = reverse("admin:imaging_delete_session", args=[record.pk, session.pk])
        resp = self.client.get(del_url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "deleted successfully")
        self.assertFalse(ImagingSession.objects.filter(pk=session.pk).exists())



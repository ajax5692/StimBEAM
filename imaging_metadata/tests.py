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
        self.assertEqual(TrackChanges.objects.filter(animal_id="IMG01").count(), 1)
        create_record = TrackChanges.objects.filter(animal_id="IMG01").first()
        self.assertEqual(create_record.action, "+")
        self.assertEqual(create_record.category, TrackChanges.CategoryChoices.IMAGING_SESSION)
        self.assertIn("Initial Entry", create_record.changes)
        self.assertIn("imaging_region: 'V1'", create_record.changes)

        # Update
        session.imaging_region = "V2"
        session.save()
        self.assertEqual(TrackChanges.objects.filter(animal_id="IMG01").count(), 2)
        update_record = TrackChanges.objects.filter(animal_id="IMG01").first()
        self.assertEqual(update_record.action, "~")
        self.assertIn("imaging_region", update_record.changes)

        # Delete
        session.delete()
        self.assertEqual(TrackChanges.objects.filter(animal_id="IMG01").count(), 3)
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
            mesc_file_path="/data/file2.mesc",
            measurement_unit_ranges="10:21",
        )
        with self.assertRaises(ValidationError) as ctx:
            duplicate.full_clean()
        self.assertIn("measurement_unit_ranges", ctx.exception.message_dict)

        with self.assertRaises(ValidationError):
            duplicate.save()

    def test_overlapping_units_rejected(self):
        from django.core.exceptions import ValidationError

        ImagingSession.objects.create(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file1.mesc",
            measurement_unit_ranges="10:21",
        )

        # Overlaps at units 20, 21
        overlapping = ImagingSession(
            animal=self.animal1,
            acquisition_date=self.today,
            mesc_file_path="/data/file2.mesc",
            measurement_unit_ranges="20:30",
        )
        with self.assertRaises(ValidationError) as ctx:
            overlapping.full_clean()
        self.assertIn("measurement_unit_ranges", ctx.exception.message_dict)
        self.assertIn("20", str(ctx.exception.message_dict["measurement_unit_ranges"]))

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
            mesc_file_path="/data/file2.mesc",
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
            mesc_file_path="/data/file2.mesc",
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
            mesc_file_path="/data/file2.mesc",
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



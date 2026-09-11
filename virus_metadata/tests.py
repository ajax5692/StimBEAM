from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import TrackChanges, Virus

User = get_user_model()


class VirusTrackChangesTest(TestCase):
    def setUp(self):
        # Create a test user instance
        self.user = User.objects.create(
            username="AC",
            first_name="Abhrajyoti",
        )

    def test_track_changes_lifecycle(self):
        # Create
        virus = Virus.objects.create(
            virus_id="AAV9-TEST",
            viral_construct="AAV9-hSyn-DIO-jGCaMP8s",
            titre="1.5x10^13 vg/mL",
            location_in_fridge="Rack 2, Box A, Pos 5",
            virus_owner=self.user,  # <--- Pass self.user instead of "AC"
        )
        self.assertEqual(TrackChanges.objects.filter(animal_id="AAV9-TEST").count(), 1)
        create_record = TrackChanges.objects.filter(animal_id="AAV9-TEST").first()
        self.assertEqual(create_record.action, "+")
        self.assertEqual(create_record.category, TrackChanges.CategoryChoices.VIRUS)
        self.assertIn("Initial Entry", create_record.changes)
        self.assertIn("viral_construct: 'AAV9-hSyn-DIO-jGCaMP8s'", create_record.changes)

        # Update
        virus.location_in_fridge = "Rack 2, Box B, Pos 1"
        virus.save()
        self.assertEqual(TrackChanges.objects.filter(animal_id="AAV9-TEST").count(), 2)
        update_record = TrackChanges.objects.filter(animal_id="AAV9-TEST").first()
        self.assertEqual(update_record.action, "~")
        self.assertIn("location_in_fridge", update_record.changes)

        # Delete
        virus.delete()
        self.assertEqual(TrackChanges.objects.filter(animal_id="AAV9-TEST").count(), 3)
        delete_record = TrackChanges.objects.filter(animal_id="AAV9-TEST").first()
        self.assertEqual(delete_record.action, "-")
        self.assertEqual(delete_record.changes, "Deleted Record")
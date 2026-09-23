from django.test import TestCase
from django.utils import timezone

from animals_metadata.models import Animal
from imaging_metadata.models import ImagingSession
from .models import AnalysisRun, TrackChanges


class AnalysisRunTrackChangesTest(TestCase):
    def setUp(self):
        self.animal = Animal.objects.create(
            animal_id="ANL01",
            sex="F",
            genotype="Thy1-Cre",
            dob=timezone.now().date(),
        )
        self.session = ImagingSession.objects.create(
            animal=self.animal,
            acquisition_date=timezone.now().date(),
            imaging_region="V1",
            mesc_file_path="/data/file.mesc",
            measurement_unit_ranges="1:10",
        )

    def test_track_changes_lifecycle(self):
        # Create
        run = AnalysisRun.objects.create(
            imaging_session=self.session,
            frame_rate=30.0,
        )
        self.assertEqual(TrackChanges.objects.filter(animal_id="ANL01").count(), 1)
        create_record = TrackChanges.objects.filter(animal_id="ANL01").first()
        self.assertEqual(create_record.action, "+")
        self.assertEqual(create_record.category, TrackChanges.CategoryChoices.ANALYSIS_RUN)
        self.assertIn("Initial Entry", create_record.changes)
        self.assertIn("frame_rate: '30.0'", create_record.changes)

        # Update
        run.notes = "Updated pipeline notes"
        run.save()
        self.assertEqual(TrackChanges.objects.filter(animal_id="ANL01").count(), 2)
        update_record = TrackChanges.objects.filter(animal_id="ANL01").first()
        self.assertEqual(update_record.action, "~")
        self.assertIn("notes", update_record.changes)

        # Delete
        run.delete()
        self.assertEqual(TrackChanges.objects.filter(animal_id="ANL01").count(), 3)
        delete_record = TrackChanges.objects.filter(animal_id="ANL01").first()
        self.assertEqual(delete_record.action, "-")
        self.assertEqual(delete_record.changes, "Deleted Record")

    def test_run_deletion_updates_session_status(self):
        # Initial run completed -> session marked as 'Y'
        self.session.analysis_performed = ImagingSession.AnalysisPerformedChoices.YES
        self.session.save(update_fields=["analysis_performed"])
        run1 = AnalysisRun.objects.create(
            imaging_session=self.session,
            status=AnalysisRun.StatusChoices.COMPLETED,
            frame_rate=30.0,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.analysis_performed, ImagingSession.AnalysisPerformedChoices.YES)

        # Deleting the only completed run marks session as 'Record Deleted' ('D')
        run1.delete()
        self.session.refresh_from_db()
        self.assertEqual(self.session.analysis_performed, ImagingSession.AnalysisPerformedChoices.RECORD_DELETED)
        self.assertEqual(self.session.get_analysis_performed_display(), "Record Deleted")

        # If multiple runs exist and one completed remains, session stays 'Y'
        run2 = AnalysisRun.objects.create(
            imaging_session=self.session,
            frame_rate=30.0,
        )
        run2.mark_completed()
        run3 = AnalysisRun.objects.create(
            imaging_session=self.session,
            status=AnalysisRun.StatusChoices.FAILED,
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.analysis_performed, ImagingSession.AnalysisPerformedChoices.YES)

        # Delete failed run -> still has completed run2 -> stays 'Y'
        run3.delete()
        self.session.refresh_from_db()
        self.assertEqual(self.session.analysis_performed, ImagingSession.AnalysisPerformedChoices.YES)

        # Delete run2 -> no completed runs left -> becomes 'Record Deleted'
        run2.delete()
        self.session.refresh_from_db()
        self.assertEqual(self.session.analysis_performed, ImagingSession.AnalysisPerformedChoices.RECORD_DELETED)

    def test_admin_form_excludes_record_deleted(self):
        from imaging_metadata.admin import ImagingSessionAdminForm
        form = ImagingSessionAdminForm()
        choices = [c[0] for c in form.fields["analysis_performed"].choices]
        self.assertNotIn(ImagingSession.AnalysisPerformedChoices.RECORD_DELETED.value, choices)
        self.assertIn(ImagingSession.AnalysisPerformedChoices.YES.value, choices)
        self.assertIn(ImagingSession.AnalysisPerformedChoices.NO.value, choices)



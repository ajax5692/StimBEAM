import json

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.utils import timezone

from animals_metadata.models import Animal
from imaging_metadata.models import ImagingSession
from .admin import AnalysisRunAdmin, AnalysisRunAdminForm
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


class MockAdminSite(AdminSite):
    pass


class AnalysisRunAdminOutputResourceTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="admin_tester",
            email="admin@example.com",
            password="password123",
        )
        self.animal = Animal.objects.create(
            animal_id="ANL02",
            sex="M",
            genotype="WT",
            dob=timezone.now().date(),
        )
        self.session = ImagingSession.objects.create(
            animal=self.animal,
            acquisition_date=timezone.now().date(),
            imaging_region="V1",
            mesc_file_path="/data/test.mesc",
            measurement_unit_ranges="1:5",
        )
        self.run = AnalysisRun.objects.create(
            imaging_session=self.session,
            frame_rate=30.0,
            output_log_path="/data/logs/m67_runlog.txt",
            output_path="/data/suite2p/output",
        )
        self.site = MockAdminSite()
        self.admin = AnalysisRunAdmin(AnalysisRun, self.site)
        self.factory = RequestFactory()

    def test_display_output_resources_rendering(self):
        html = self.admin.display_output_resources(self.run)
        # Copy button present
        self.assertIn('class="pstim-copy-button"', html)
        self.assertIn('data-copy-text="/data/logs/m67_runlog.txt"', html)
        self.assertIn('data-copy-text="/data/suite2p/output"', html)

        # Labels present
        self.assertIn("• Log:", html)
        self.assertIn("• Suite2P:", html)

        # Text present
        self.assertIn("/data/logs/m67_runlog.txt", html)
        self.assertIn("/data/suite2p/output", html)

        # Edit buttons with blue color and pencil SVG present
        self.assertIn('class="pstim-edit-button"', html)
        self.assertIn('data-field="output_log_path"', html)
        self.assertIn('data-field="output_path"', html)

        # Inline editor container present
        self.assertIn('class="pstim-resource-editor"', html)
        self.assertIn('class="pstim-resource-input"', html)
        self.assertIn('class="pstim-resource-save-btn"', html)
        self.assertIn('class="pstim-resource-cancel-btn"', html)

    def test_update_output_path_view_success_json(self):
        new_log_path = "/new/dir/m67_updated_runlog.txt"
        request = self.factory.post(
            f"/admin/imaging_analysis_metadata/analysisrun/{self.run.pk}/update-output-path/",
            data=json.dumps({"field": "output_log_path", "value": new_log_path}),
            content_type="application/json",
        )
        request.user = self.user
        response = self.admin.update_output_path_view(request, self.run.pk)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["value"], new_log_path)

        self.run.refresh_from_db()
        self.assertEqual(self.run.output_log_path, new_log_path)

        # Verify TrackChanges logged
        track_entry = TrackChanges.objects.filter(
            animal_id=self.animal.animal_id,
            action="~",
        ).order_by("-changed_at").first()
        self.assertIsNotNone(track_entry)
        self.assertIn("output_log_path", track_entry.changes)

    def test_update_output_path_view_success_form_data(self):
        new_output_path = "/new/dir/suite2p_results"
        request = self.factory.post(
            f"/admin/imaging_analysis_metadata/analysisrun/{self.run.pk}/update-output-path/",
            data={"field": "output_path", "value": new_output_path},
        )
        request.user = self.user
        response = self.admin.update_output_path_view(request, self.run.pk)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode("utf-8"))
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["value"], new_output_path)

        self.run.refresh_from_db()
        self.assertEqual(self.run.output_path, new_output_path)

    def test_update_output_path_view_invalid_field(self):
        request = self.factory.post(
            f"/admin/imaging_analysis_metadata/analysisrun/{self.run.pk}/update-output-path/",
            data=json.dumps({"field": "notes", "value": "invalid"}),
            content_type="application/json",
        )
        request.user = self.user
        response = self.admin.update_output_path_view(request, self.run.pk)
        self.assertEqual(response.status_code, 400)

    def test_update_output_path_view_not_found(self):
        request = self.factory.post(
            "/admin/imaging_analysis_metadata/analysisrun/99999/update-output-path/",
            data=json.dumps({"field": "output_path", "value": "/test"}),
            content_type="application/json",
        )
        request.user = self.user
        response = self.admin.update_output_path_view(request, 99999)
        self.assertEqual(response.status_code, 404)

    def test_update_output_path_view_method_not_allowed(self):
        request = self.factory.get(
            f"/admin/imaging_analysis_metadata/analysisrun/{self.run.pk}/update-output-path/",
        )
        request.user = self.user
        response = self.admin.update_output_path_view(request, self.run.pk)
        self.assertEqual(response.status_code, 405)

    def test_admin_form_has_copyable_path_widgets(self):
        from animals_metadata.utils import CopyablePathInput
        form = AnalysisRunAdminForm()
        self.assertIsInstance(form.fields["output_log_path"].widget, CopyablePathInput)
        self.assertIsInstance(form.fields["output_path"].widget, CopyablePathInput)




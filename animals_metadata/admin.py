from django import forms
from django.contrib import admin
from django.utils.html import format_html, format_html_join
from simple_history.admin import SimpleHistoryAdmin

from animals_metadata.models import (
    Animal,
    TrackChanges,
    ViralInjection,
    VisionCheck,
)
from animals_metadata.utils import (
    BaseTrackChangesAdmin,
    render_copyable_path_widget,
)


@admin.register(Animal)
class AnimalAdmin(SimpleHistoryAdmin):
    list_display = (
        "animal_id",
        "display_owner",
        "sex",
        "genotype",
        "dob",
        "age_in_days",
        "status",
        "pipeline_stage",
        "cage_id",
        "ogr_id",
        "project_id",
    )

    list_filter = (
        "status",
        "sex",
        "owner",
        "genotype",
        "project_id",
    )

    readonly_fields = (
        "age_in_days",
    )

    search_fields = (
        "animal_id",
        "genotype",
        "cage_id",
        "sex",
        "owner",
    )
    
    # Customizes what text is shown in the dropdown options
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "owner" and formfield:
            # Displays first_name (or falls back to username if first_name is empty)
            formfield.label_from_instance = lambda user: user.first_name if user.first_name else user.username
        return formfield
    
    @admin.display(description="Owner")
    def display_owner(self, obj):
        if obj.owner:
            return obj.owner.first_name if obj.owner.first_name else obj.owner.username
        return "-"


@admin.register(VisionCheck)
class VisionCheckAdmin(SimpleHistoryAdmin):
    list_select_related = ("animal_id",)

    list_display = (
        "get_animal_id",
        "vision_test_type",
        "vision_test_result",
        "display_data_path",
    )

    list_filter = (
        "vision_test_type",
        "vision_test_result",
        "animal_id",
    )

    search_fields = (
        "animal_id__animal_id",
        "vision_test_result",
        "vision_test_type",
    )

    @admin.display(description="Animal ID")
    def get_animal_id(self, obj):
        return obj.animal_id
    
    
    @admin.display(description="Data Path", ordering="data_path")
    def display_data_path(self, obj):
        return render_copyable_path_widget(obj.data_path, tooltip="Copy data path")


class ViralInjectionAdminForm(forms.ModelForm):
    class Meta:
        model = ViralInjection
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        # -------------------------------------------------
        # VIRUS 2
        # -------------------------------------------------
        virus_2 = cleaned_data.get("virus_id_2")
        volume_2 = cleaned_data.get("volume_nl_2")
        site_2 = cleaned_data.get("site_2")
        depth_2 = cleaned_data.get("depth_2")

        virus_2_values = (
            virus_2,
            volume_2,
            site_2,
            depth_2,
        )

        if any(value not in (None, "") for value in virus_2_values):
            if not virus_2:
                self.add_error(
                    "virus_id_2",
                    "Please select Virus ID 2.",
                )

            if volume_2 is None:
                self.add_error(
                    "volume_nl_2",
                    "Please enter Volume 2.",
                )

            if not site_2:
                self.add_error(
                    "site_2",
                    "Please select Injection Site 2.",
                )

            if depth_2 is None:
                self.add_error(
                    "depth_2",
                    "Please enter Depth 2.",
                )

        # -------------------------------------------------
        # VIRUS 3
        # -------------------------------------------------
        virus_3 = cleaned_data.get("virus_id_3")
        volume_3 = cleaned_data.get("volume_nl_3")
        site_3 = cleaned_data.get("site_3")
        depth_3 = cleaned_data.get("depth_3")

        virus_3_values = (
            virus_3,
            volume_3,
            site_3,
            depth_3,
        )

        if any(value not in (None, "") for value in virus_3_values):
            if not virus_3:
                self.add_error(
                    "virus_id_3",
                    "Please select Virus ID 3.",
                )

            if volume_3 is None:
                self.add_error(
                    "volume_nl_3",
                    "Please enter Volume 3.",
                )

            if not site_3:
                self.add_error(
                    "site_3",
                    "Please select Injection Site 3.",
                )

            if depth_3 is None:
                self.add_error(
                    "depth_3",
                    "Please enter Depth 3.",
                )

        return cleaned_data


@admin.register(ViralInjection)
class ViralInjectionAdmin(SimpleHistoryAdmin):
    form = ViralInjectionAdminForm
    list_select_related = ("animal_id", "virus_id", "virus_id_2", "virus_id_3")

    list_display = (
        "get_animal_id",
        "get_owner",
        "display_virus_injections",
        "get_inj_person",
        "injection_date",
        "surgery_date",
        "get_surgery_person",
        "display_expression_mescfile_path",
        "notes",
    )

    list_filter = (
        "animal_id",
        "virus_id",
        "virus_id_2",
        "virus_id_3",
        "injecting_person",
        "site",
        "site_2",
        "site_3",
    )

    search_fields = (
        "animal_id__animal_id",
        "virus_id__virus_id",
        "virus_id_2__virus_id",
        "virus_id_3__virus_id",
        "injecting_person",
        "site",
        "site_2",
        "site_3",
    )
    
    # Customizes what text is shown in the dropdown options
       # Customizes what text is shown in the dropdown options
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        
        # Check both fields together
        if db_field.name in ("injecting_person", "surgery_person") and formfield:
            # Displays first_name (or falls back to username if first_name is empty)
            formfield.label_from_instance = lambda user: user.first_name if user.first_name else user.username
            
        return formfield

    fieldsets = (
        (
            "Animal",
            {
                "fields": (
                    "animal_id",
                ),
            },
        ),
        (
            "Virus Injection 1",
            {
                "fields": (
                    (
                        "virus_id",
                        "volume_ul",
                        "site",
                        "depth",
                    ),
                ),
            },
        ),
        (
            "Virus Injection 2",
            {
                "fields": (
                    (
                        "virus_id_2",
                        "volume_nl_2",
                        "site_2",
                        "depth_2",
                    ),
                ),
            },
        ),
        (
            "Virus Injection 3",
            {
                "fields": (
                    (
                        "virus_id_3",
                        "volume_nl_3",
                        "site_3",
                        "depth_3",
                    ),
                ),
            },
        ),
        (
            "Injection Details",
            {
                "fields": (
                    "injection_date",
                    "injecting_person",
                ),
            },
        ),
        (
            "Surgery",
            {
                "fields": (
                    "surgery_date",
                    "surgery_person",
                ),
            },
        ),
        (
            "Other",
            {
                "fields": (
                    "expression",
                    "notes",
                ),
            },
        ),
    )

    @admin.display(description="Animal ID")
    def get_animal_id(self, obj):
        return obj.animal_id

    @admin.display(description="Owner")
    def get_owner(self, obj):
        if obj.animal_id.owner.first_name and obj.animal_id.owner.last_name:
            return f"{obj.animal_id.owner.first_name[0].upper()}{obj.animal_id.owner.last_name[0].upper()}"

    @admin.display(description="Virus / Volume / Site / Depth")
    def display_virus_injections(self, obj):
        injections = []

        # Virus 1
        if obj.virus_id:
            injections.append(
                (
                    obj.virus_id.virus_id if hasattr(obj.virus_id, "virus_id") else obj.virus_id,
                    obj.volume_ul,
                    obj.site,
                    obj.depth,
                )
            )

        # Virus 2
        if obj.virus_id_2:
            injections.append(
                (
                    obj.virus_id_2.virus_id if hasattr(obj.virus_id_2, "virus_id") else obj.virus_id_2,
                    obj.volume_nl_2,
                    obj.site_2,
                    obj.depth_2,
                )
            )

        # Virus 3
        if obj.virus_id_3:
            injections.append(
                (
                    obj.virus_id_3.virus_id if hasattr(obj.virus_id_3, "virus_id") else obj.virus_id_3,
                    obj.volume_nl_3,
                    obj.site_3,
                    obj.depth_3,
                )
            )

        if not injections:
            return "-"

        return format_html_join(
            "",
            (
                '<div style="margin-bottom: 6px;">'
                '• <strong>{}</strong>'
                ' — {} nL'
                ' — {}'
                ' — {} μm'
                '</div>'
            ),
            injections,
        )

    @admin.display(description="Inj. Person")
    def get_inj_person(self, obj):
        if obj.injecting_person.first_name and obj.injecting_person.last_name:
            return f"{obj.injecting_person.first_name[0].upper()}{obj.injecting_person.last_name[0].upper()}"

    @admin.display(description="Sur. Person")
    def get_surgery_person(self, obj):
        if obj.surgery_person.first_name and obj.surgery_person.last_name:
            return f"{obj.surgery_person.first_name[0].upper()}{obj.surgery_person.last_name[0].upper()}"
    
    @admin.display(description="Expression (Checkup MESC File)", ordering="expression")
    def display_expression_mescfile_path(self, obj):
        return render_copyable_path_widget(obj.expression, tooltip="Copy MESC file path")


@admin.register(TrackChanges)
class TrackChangesAdmin(BaseTrackChangesAdmin):
    pass
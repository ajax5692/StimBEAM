from django.apps import AppConfig


class AnimalsMetadataConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "animals_metadata"
    verbose_name = "ANIMALS METADATA"

    def ready(self):
        from django.contrib import admin

        original_get_app_list = admin.AdminSite.get_app_list

        def custom_get_app_list(self, request, app_label=None):
            app_list = original_get_app_list(
                self,
                request,
                app_label,
            )

            # Order models inside apps
            app_model_orders = {
                "animals_metadata": [
                    "Animals",
                    "Viral Injections",
                    "Vision Checks",
                    "Track Changes",
                ],
                "virus_metadata": [
                    "Virus Inventory",
                    "Track Changes",
                ],
                "imaging_metadata": [
                    "Imaging Records",
                    "Track Changes",
                ],
                "imaging_analysis_metadata": [
                    "Analysis Runs",
                    "Track Changes",
                ],
                "training_metadata": [
                    "Body Weight Records",
                    "Training Records",
                    "Track Changes",
                ],
            }

            for app in app_list:
                app_label = app["app_label"]
                if app_label in app_model_orders:
                    order = app_model_orders[app_label]
                    app["models"].sort(
                        key=lambda x: (
                            order.index(x["name"])
                            if x["name"] in order
                            else 999
                        )
                    )

            # Order the apps in the Django admin sidebar
            app_order = {
                "animals_metadata": 0,
                "imaging_metadata": 1,
                "imaging_analysis_metadata": 2,
                "training_metadata": 3,
                "virus_metadata": 4,
                "auth": 5,
            }

            app_list.sort(
                key=lambda app: app_order.get(
                    app["app_label"],
                    999,
                )
            )

            return app_list

        admin.AdminSite.get_app_list = custom_get_app_list

        # Load signals when Django has finished loading the app registry
        from . import signals  # noqa: F401
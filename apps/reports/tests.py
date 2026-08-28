from django.apps import apps
from django.test import SimpleTestCase


class ReportsSchemaTests(SimpleTestCase):
    def test_reports_app_has_no_models(self):
        self.assertEqual(list(apps.get_app_config("reports").get_models()), [])

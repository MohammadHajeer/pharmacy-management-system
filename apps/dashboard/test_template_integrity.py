"""Guard against HTML formatters treating Django expressions as ordinary text."""

import re

from django.conf import settings
from django.template import engines
from django.test import SimpleTestCase


class ProjectTemplateIntegrityTests(SimpleTestCase):
    def templates(self):
        roots = [settings.BASE_DIR / "templates"]
        roots.extend(sorted((settings.BASE_DIR / "apps").glob("*/templates")))
        for root in roots:
            for path in sorted(root.rglob("*.html")):
                yield path, path.read_text(encoding="utf-8")

    def test_all_project_templates_compile(self):
        for path, source in self.templates():
            with self.subTest(template=str(path.relative_to(settings.BASE_DIR))):
                # Compilation checks complete nesting, including earlier opening
                # tags when Django reports a later endif/endfor as the error.
                engines["django"].from_string(source)

    def test_django_expressions_are_not_wrapped_across_lines(self):
        for path, source in self.templates():
            with self.subTest(template=str(path.relative_to(settings.BASE_DIR))):
                for match in re.finditer(r"{%.*?%}|{{.*?}}", source, re.DOTALL):
                    line = source.count("\n", 0, match.start()) + 1
                    # Compilation alone misses expressions that become literal
                    # text when the Django lexer encounters a newline.
                    self.assertNotIn("\n", match.group(), f"{path}:{line}: wrapped Django expression")

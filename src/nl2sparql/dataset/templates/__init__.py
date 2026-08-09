"""GoogleSQL template library and validation contract."""

from nl2sparql.dataset.templates.validate import (
    TEMPLATES_PATH,
    TemplateSummary,
    TemplateValidationError,
    load_templates,
    render_template,
    validate_template_library,
)

__all__ = [
    "TEMPLATES_PATH",
    "TemplateSummary",
    "TemplateValidationError",
    "load_templates",
    "render_template",
    "validate_template_library",
]

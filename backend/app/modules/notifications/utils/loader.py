"""Renders a NotificationEvent into the subject, HTML and text a channel sends.

The wording lives in templates/i18n.yml rather than in these classes: a
notification email is the one thing this backend renders for a human to read,
so it carries its own copy instead of the module growing a translation layer.
"""

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.core.base.markers import helper
from app.modules.notifications.constants import NotificationTemplateDefaults
from app.modules.notifications.schemas import NotificationEvent


class NotificationTemplates:
    """Loads the Jinja2 templates and i18n.yml once, then renders one event.

    The directory is resolved from __file__, not the process's working
    directory, so a worker or a scheduler started from anywhere still finds it.
    StrictUndefined is deliberate: a template naming a key i18n.yml doesn't
    have must fail the test suite, never ship an email with a blank cell.
    """

    _DIRECTORY = Path(__file__).resolve().parent.parent / NotificationTemplateDefaults.DIRECTORY
    _environment = Environment(
        loader=FileSystemLoader(_DIRECTORY),
        autoescape=select_autoescape(default_for_string=False, enabled_extensions=("html",)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    _text: dict[str, Any] = yaml.safe_load(
        (_DIRECTORY / NotificationTemplateDefaults.I18N_FILE).read_text(encoding="utf-8")
    )

    @classmethod
    @helper
    def subject(cls, event: NotificationEvent) -> str:
        """The email subject for this kind, with the severity label filled in."""
        template = cls._text["subjects"][event.kind.value]
        return template.format(severity=cls.severity_label(event.severity), title=event.title)

    @classmethod
    @helper
    def render_html(cls, event: NotificationEvent) -> str:
        """The HTML body for this kind."""
        return cls._render(f"{event.kind.value}.html", event)

    @classmethod
    @helper
    def render_text(cls, event: NotificationEvent) -> str:
        """The plain text body for this kind — Telegram, Base.vn, and the email's text part."""
        return cls._render(f"{event.kind.value}.txt", event)

    @classmethod
    @helper
    def severity_label(cls, severity: str | None) -> str:
        """The Vietnamese label for a severity, or an empty string when there is none."""
        return cls._text["severity"].get(severity, severity or "")

    @classmethod
    @helper
    def _render(cls, name: str, event: NotificationEvent) -> str:
        """Render one template with the event and the shared wording."""
        return cls._environment.get_template(name).render(
            event=event,
            labels=cls._text["labels"],
            heading=cls._text["headings"][event.kind.value],
            severity_label=cls.severity_label(event.severity),
            category_label=cls._text["category"].get(event.category, event.category),
            source_label=cls._text["source"].get(event.source, event.source),
            detected_at=(
                event.detected_at.strftime(NotificationTemplateDefaults.DATETIME_FORMAT)
                if event.detected_at is not None
                else None
            ),
        )

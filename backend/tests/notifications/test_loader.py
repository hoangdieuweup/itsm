"""Unit tests for the notification template loader — no I/O beyond reading
the module's own template files."""

from datetime import UTC, datetime

import pytest

from app.modules.notifications.constants import NotificationKind
from app.modules.notifications.schemas import NotificationEvent
from app.modules.notifications.utils import NotificationTemplates
from app.modules.observability.constants import AlertSeverity, IncidentCategory, IncidentSource


def _incident_event(**overrides) -> NotificationEvent:
    defaults = {
        "kind": NotificationKind.INCIDENT_DETECTED,
        "title": "DDoS trên example.com",
        "severity": "CRITICAL",
        "category": "DDOS",
        "source": "CLOUDFLARE",
        "detected_at": datetime(2026, 9, 14, 10, 30, tzinfo=UTC),
        "project_name": "Cổng thanh toán",
        "environment_name": "Production",
        "rule_name": "Cảnh báo DDoS",
        "incident_url": "https://itsm.test/admin/incidents",
    }
    defaults.update(overrides)
    return NotificationEvent(**defaults)


class TestSubject:
    def test_incident_subject_carries_the_severity_and_title(self) -> None:
        subject = NotificationTemplates.subject(_incident_event())

        assert "Nghiêm trọng" in subject
        assert "DDoS trên example.com" in subject

    def test_test_event_has_its_own_subject(self) -> None:
        subject = NotificationTemplates.subject(
            NotificationEvent(kind=NotificationKind.TEST, title="Xin chào")
        )

        assert subject != ""
        assert "{" not in subject


class TestRenderHtml:
    def test_incident_html_shows_every_field_in_vietnamese(self) -> None:
        html = NotificationTemplates.render_html(_incident_event())

        for expected in (
            "DDoS trên example.com",
            "Nghiêm trọng",
            "Tấn công DDoS",
            "Cổng thanh toán",
            "Production",
            "Cảnh báo DDoS",
            "14/09/2026",
            "https://itsm.test/admin/incidents",
        ):
            assert expected in html
        assert "{{" not in html

    def test_missing_optional_fields_leave_no_empty_rows(self) -> None:
        html = NotificationTemplates.render_html(
            NotificationEvent(kind=NotificationKind.INCIDENT_DETECTED, title="Chỉ có tiêu đề")
        )

        assert "Chỉ có tiêu đề" in html
        assert "Mức độ" not in html
        assert "None" not in html

    def test_html_escapes_the_title(self) -> None:
        html = NotificationTemplates.render_html(_incident_event(title="<script>x</script>"))

        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestRenderText:
    def test_incident_text_is_plain_and_complete(self) -> None:
        text = NotificationTemplates.render_text(_incident_event())

        assert "DDoS trên example.com" in text
        assert "Nghiêm trọng" in text
        assert "<" not in text
        assert "{{" not in text

    def test_text_does_not_escape_html_entities(self) -> None:
        text = NotificationTemplates.render_text(_incident_event(title="A & B"))

        assert "A & B" in text


class TestI18nCoverage:
    @pytest.mark.parametrize("kind", list(NotificationKind))
    def test_every_kind_renders_all_three_outputs(self, kind: NotificationKind) -> None:
        event = NotificationEvent(kind=kind, title="Tiêu đề")

        assert NotificationTemplates.subject(event)
        assert NotificationTemplates.render_html(event)
        assert NotificationTemplates.render_text(event)

    @pytest.mark.parametrize("severity", list(AlertSeverity))
    def test_every_severity_has_a_label(self, severity: AlertSeverity) -> None:
        assert NotificationTemplates.severity_label(severity.value) != severity.value

    @pytest.mark.parametrize("category", list(IncidentCategory))
    def test_every_category_renders_a_label(self, category: IncidentCategory) -> None:
        html = NotificationTemplates.render_html(_incident_event(category=category.value))

        assert category.value not in html

    @pytest.mark.parametrize("source", list(IncidentSource))
    def test_every_source_renders_a_label(self, source: IncidentSource) -> None:
        html = NotificationTemplates.render_html(_incident_event(source=source.value))

        assert html.count(source.value) == 0

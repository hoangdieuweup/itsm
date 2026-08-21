"""Unit tests for app.modules.projects.rules — pure decisions, no I/O, no fixtures."""

from app.modules.projects.config import projects_settings
from app.modules.projects.constants import ProjectLinkType
from app.modules.projects.rules import ProjectsRules


class TestDefaultLinks:
    def test_returns_jira_and_git_when_both_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "https://jira.weup.vn")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "https://git.weup.vn")

        links = ProjectsRules.default_links()

        assert links == [
            (ProjectLinkType.JIRA, "Jira", "https://jira.weup.vn"),
            (ProjectLinkType.GIT, "Git", "https://git.weup.vn"),
        ]

    def test_skips_jira_when_unconfigured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "https://git.weup.vn")

        links = ProjectsRules.default_links()

        assert links == [(ProjectLinkType.GIT, "Git", "https://git.weup.vn")]

    def test_returns_empty_when_neither_configured(self, monkeypatch) -> None:
        monkeypatch.setattr(projects_settings, "DEFAULT_JIRA_URL", "")
        monkeypatch.setattr(projects_settings, "DEFAULT_GIT_URL", "")

        assert ProjectsRules.default_links() == []

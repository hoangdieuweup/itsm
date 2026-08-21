"""Settings owned by the projects module."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ProjectsConfig(BaseSettings):
    """Environment driven settings for the projects module.

    Both default to empty: an unconfigured URL means CreateProject attaches
    no default link of that kind, per ProjectsRules.default_links().
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROJECTS__", extra="ignore")

    DEFAULT_JIRA_URL: str = ""
    DEFAULT_GIT_URL: str = ""


projects_settings = ProjectsConfig()

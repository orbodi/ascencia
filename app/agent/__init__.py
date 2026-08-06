"""Package agent — importer AgentService depuis app.agent.service."""

__all__ = ["AgentService"]


def __getattr__(name: str):
    if name == "AgentService":
        from app.agent.service import AgentService

        return AgentService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

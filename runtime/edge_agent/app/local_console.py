"""Compatibility entry; new deployments start the console inside AI Runtime."""

from ai_runtime.app.gateway.console import create_app, initialize_password

__all__ = ["create_app", "initialize_password"]

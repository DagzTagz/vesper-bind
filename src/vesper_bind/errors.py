"""Failures the CLI prints without file contents."""


class BindError(Exception):
    """A local check failed. The message is safe to print."""

"""Daydor API layer. Thin by design: it opens a database session as the caller and calls the
backend's own functions. It never edits backend code, migrations or the model."""
__version__ = "0.1.0"

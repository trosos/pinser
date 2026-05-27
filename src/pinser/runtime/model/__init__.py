"""Model interfaces for the runtime."""

from pinser.runtime.model.fake import FakeModel
from pinser.runtime.model.protocol import ModelBackend

__all__ = ["FakeModel", "ModelBackend"]

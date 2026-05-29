from dataclasses import dataclass

import pytest


@dataclass(frozen=True, slots=True)
class RemoteModeConfig:
    enable_remote_features: bool = False
    allow_undocumented_remote_api: bool = False


def validate_remote_trigger_mode(config: RemoteModeConfig) -> None:
    if not config.enable_remote_features:
        msg = "remote trigger requires enable_remote_features=True"
        raise PermissionError(msg)
    if not config.allow_undocumented_remote_api:
        msg = "remote trigger requires explicit undocumented remote opt-in"
        raise PermissionError(msg)


def test_remote_trigger_is_blocked_by_default_local_mode() -> None:
    with pytest.raises(PermissionError, match="enable_remote_features=True"):
        validate_remote_trigger_mode(RemoteModeConfig())


def test_remote_trigger_requires_explicit_undocumented_opt_in() -> None:
    with pytest.raises(PermissionError, match="explicit undocumented remote opt-in"):
        validate_remote_trigger_mode(RemoteModeConfig(enable_remote_features=True))


def test_remote_trigger_allowed_only_after_explicit_dual_opt_in() -> None:
    validate_remote_trigger_mode(
        RemoteModeConfig(
            enable_remote_features=True,
            allow_undocumented_remote_api=True,
        )
    )

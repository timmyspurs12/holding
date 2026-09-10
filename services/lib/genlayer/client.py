"""genlayerClient — builds the chain for the configured network and caches it."""

from __future__ import annotations

import threading
from typing import Optional

from .base import Chain, LiveUnavailable
from .config import GenLayerConfig
from .demo import DemoChain
from .registry import HoldingRegistryContract
from .types import NetworkMode

# Re-entrant: get_registry() builds a chain while already holding the lock.
_lock = threading.RLock()
_chain: Optional[Chain] = None
_registry: Optional[HoldingRegistryContract] = None
_config: Optional[GenLayerConfig] = None


def build_chain(config: Optional[GenLayerConfig] = None) -> Chain:
    config = config or GenLayerConfig.from_env()
    if config.mode is NetworkMode.DEMO:
        return DemoChain(config)

    # Live modes must not silently degrade. If the SDK or a required setting is
    # missing the caller sees an explicit, labelled failure.
    try:
        from .live import LiveChain
    except ImportError as error:  # pragma: no cover
        raise LiveUnavailable(f"live adapter unavailable: {error}") from error
    return LiveChain(config)


def get_chain(config: Optional[GenLayerConfig] = None, *, reload: bool = False) -> Chain:
    """Process-wide chain singleton."""
    global _chain, _config
    with _lock:
        if _chain is None or reload:
            _config = config or GenLayerConfig.from_env()
            _chain = build_chain(_config)
        return _chain


def get_registry(config: Optional[GenLayerConfig] = None, *, reload: bool = False) -> HoldingRegistryContract:
    """Process-wide typed registry facade."""
    global _registry, _config
    with _lock:
        if _registry is None or reload:
            _config = config or GenLayerConfig.from_env()
            _registry = HoldingRegistryContract(get_chain(_config, reload=reload), _config)
        return _registry


def reset() -> None:
    """Drop cached instances (tests, and after an env change)."""
    global _chain, _registry, _config
    with _lock:
        _chain = None
        _registry = None
        _config = None


__all__ = [
    "build_chain",
    "get_chain",
    "get_registry",
    "reset",
    "GenLayerConfig",
    "DemoChain",
    "HoldingRegistryContract",
    "NetworkMode",
]

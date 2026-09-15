"""Imprint's independently owned agent packages.

The umbrella application imports agents only through their package-level
public interfaces.  Cross-agent metadata lives in :mod:`agents.catalog`;
implementation, roadmap and suggestions belong to each package directory.
"""

from .catalog import AGENT_SPECS, AgentSpec

__all__ = ["AGENT_SPECS", "AgentSpec"]

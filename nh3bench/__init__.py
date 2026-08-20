"""NH3Bench: real-time LLM control benchmark for an ammonia refrigeration plant."""

from .plant import (
    ControlAction,
    Plant,
    PlantConfig,
    default_plant_config,
)
from .baseline import ThermostatBaseline
from .runner import run_episode
from .scenarios import SCENARIOS, Scenario
from .scoring import ScoreReport

__version__ = "0.1.0"

__all__ = [
    "ControlAction",
    "Plant",
    "PlantConfig",
    "default_plant_config",
    "ThermostatBaseline",
    "run_episode",
    "SCENARIOS",
    "Scenario",
    "ScoreReport",
]

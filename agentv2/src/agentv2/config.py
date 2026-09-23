"""Settings: config.yaml, then config.local.yaml, then AGENTV2_* environment variables."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

ROOT = Path(os.environ.get("AGENTV2_ROOT", Path(__file__).resolve().parents[2]))


class LLMSettings(BaseModel):
    base_url: str = "http://chonkster.lan.lat:11437/v1/"
    model: str = "qwen3.6-27b"
    api_key: str = "unused"
    context_window: int = 262_144
    timeout_s: float = 300.0
    thinking: bool | None = None


class BridgeSettings(BaseModel):
    url: str = "http://127.0.0.1:8765"
    timeout_s: float = 60.0


class PlaySettings(BaseModel):
    speed: int = 3
    think_speed: int = 3
    danger_think_speed: int = 1
    wake_hours: float = 12.0
    min_wake_hours: float = 4.0
    max_wake_hours: float = 48.0
    event_cooldown_hours: float = 3.0
    alert_wake_priorities: list[str] = Field(default_factory=lambda: ["Critical", "High"])
    alert_rewake_hours: float = 24.0
    critical_kinds: list[str] = Field(default_factory=lambda: [
        "dialog", "danger", "manhunter", "hostile_group", "colonist_downed", "colonist_died", "mental_break", "building_lost"])
    wake_on_kinds: list[str] = Field(default_factory=lambda: [
        "letter", "incident", "quest", "research_finished", "steward", "orders"])
    max_requests: int = 30
    failed_step_retry_hours: float = 1.0
    max_days: int = 60
    autosave: bool = True
    save_name: str = "agentv2-autosave"
    restart_command: list[str] = Field(default_factory=list)
    restart_after_s: float = 180.0
    first_improve_day: int = 1
    improve_every_days: int = 3
    seeds: list[str] = Field(default_factory=lambda: ["rimagent-1", "rimagent-2", "rimagent-3", "rimagent-4", "rimagent-5"])
    scenario: str = "Crashlanded"
    storyteller: str = "Cassandra"
    difficulty: str = "Rough"


class ContextSettings(BaseModel):
    compact_at_tokens: int = 200_000
    compact_to_tokens: int = 80_000
    keep_tool_pairs: int = 12
    keep_messages: int = 30


class WatcherSettings(BaseModel):
    poll_s: float = 5.0
    timeout_s: float = 1.0


class StewardSettings(BaseModel):
    enabled: bool = True
    scorer: bool = True
    stock: bool = True
    orders: bool = True
    orders_off: list[str] = Field(default_factory=list)
    research_queue: list[str] = Field(default_factory=list)


class JevSettings(BaseModel):
    """TypeSafe's Jev. The direct API is faster than OpenRouter (base_url https://openrouter.ai/api, model typesafe/jev-1.13)."""

    base_url: str = "https://api.typesafe.ai"
    model: str = "jev-1.13.0"
    api_key: str = ""
    timeout_s: float = 2.0
    hedge_after_s: float = 0.8
    max_concurrency: int = 8
    requests_per_minute: int = 600
    usd_per_hour: float = 2.0
    usd_per_million_input_tokens: float = 0.042
    circuit_failures: int = 5
    circuit_cooldown_s: float = 30.0


class GateSettings(BaseModel):
    heldout_share: float = 0.3
    min_heldout: int = 4
    min_agreement: float = 0.8
    canary_actions: int = 5
    demote_after_wrong: int = 2


class LoopSettings(BaseModel):
    enabled: bool = True
    tick_s: float = 0.5
    summary_max_age_s: float = 20.0
    screen_max_age_s: float = 1.0
    claim_timeout_s: float = 20.0
    directive_hours: float = 24.0
    escalations_per_hour: int = 6
    report_up_threshold: float = 0.7
    director_lease_hours: float = 6.0
    action_timeout_ms: int = 3000
    gate: GateSettings = Field(default_factory=GateSettings)


class DashboardSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8771
    open_browser: bool = True


class Settings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    bridge: BridgeSettings = Field(default_factory=BridgeSettings)
    play: PlaySettings = Field(default_factory=PlaySettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    watchers: WatcherSettings = Field(default_factory=WatcherSettings)
    steward: StewardSettings = Field(default_factory=StewardSettings)
    jev: JevSettings = Field(default_factory=JevSettings)
    loop: LoopSettings = Field(default_factory=LoopSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)
    root: Path = ROOT
    knowledge_dir: Path = ROOT.parent / "knowledge"

    @property
    def brain(self) -> Path:
        return self.root / "brain"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def scratch(self) -> Path:
        return self.runs / "scratch"


_ENV = {
    "AGENTV2_LLM_BASE_URL": ("llm", "base_url"),
    "AGENTV2_LLM_MODEL": ("llm", "model"),
    "AGENTV2_LLM_API_KEY": ("llm", "api_key"),
    "AGENTV2_LLM_THINKING": ("llm", "thinking"),
    "AGENTV2_BRIDGE_URL": ("bridge", "url"),
    "TYPESAFE_API_KEY": ("jev", "api_key"),
    "AGENTV2_JEV_API_KEY": ("jev", "api_key"),
    "AGENTV2_JEV_BASE_URL": ("jev", "base_url"),
    "AGENTV2_JEV_MODEL": ("jev", "model"),
}


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(root: Path = ROOT) -> Settings:
    data: dict[str, Any] = {}
    for name in ("config.yaml", "config.local.yaml"):
        path = root / name
        if path.exists():
            data = _merge(data, yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    for var, (section, key) in _ENV.items():
        if os.environ.get(var):
            data.setdefault(section, {})[key] = os.environ[var]
    settings = Settings.model_validate({**data, "root": root})
    if "knowledge_dir" not in data:
        settings.knowledge_dir = root.parent / "knowledge"
    elif not settings.knowledge_dir.is_absolute():
        settings.knowledge_dir = (root / settings.knowledge_dir).resolve()
    return settings

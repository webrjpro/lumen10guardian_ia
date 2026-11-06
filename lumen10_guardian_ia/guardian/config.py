import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    data: Path
    port: int = 8765
    interval: int = 30
    ai_timeout: int = 360
    ai_daily_limit: int = 32
    workers: bool = True
    model: str = "gpt-6.1-sol"
    security_model: str = "gpt-6-astra"
    reasoning: str = "high"

    def __post_init__(self):
        if self.model not in {"gpt-6.1-sol", "gpt-6-astra"} or self.security_model not in {
            "gpt-6.1-sol",
            "gpt-6-astra",
        }:
            raise ValueError("Somente GPT-6.1 Sol e GPT-6 Astra são autorizados")
        if self.reasoning not in {"high", "xhigh", "max"}:
            raise ValueError("Raciocínio mínimo exigido: high")

    @classmethod
    def load(cls):
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "Lumen10Guardian"
        return cls(
            data=Path(os.environ.get("GUARDIAN_DATA", str(base))).resolve(),
            port=int(os.environ.get("GUARDIAN_PORT", "8765")),
            interval=max(10, int(os.environ.get("GUARDIAN_INTERVAL", "30"))),
            model=os.environ.get("GUARDIAN_MODEL", "gpt-6.1-sol"),
            security_model=os.environ.get("GUARDIAN_SECURITY_MODEL", "gpt-6-astra"),
            reasoning=os.environ.get("GUARDIAN_REASONING", "high"),
        )

    @property
    def database(self):
        return self.data / "guardian.db"

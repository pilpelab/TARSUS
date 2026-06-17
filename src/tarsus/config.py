from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass
class PipelineConfig:
    fasta: Path | None = None
    inputs: list[Path] = field(default_factory=list)
    output_dir: Path | None = None
    queue: str = "gsla-cpu"
    memory_mb: int = 7000
    cpus: int = 1

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        return cls(
            fasta=_env_path("TARSUS_FASTA"),
            inputs=_env_paths("TARSUS_INPUTS"),
            output_dir=_env_path("TARSUS_OUTPUT_DIR"),
            queue=os.environ.get("TARSUS_QUEUE", "gsla-cpu"),
            memory_mb=int(os.environ.get("TARSUS_MEMORY", "7000")),
            cpus=int(os.environ.get("TARSUS_CPUS", "1")),
        )


def _env_path(name: str) -> Path | None:
    v = os.environ.get(name)
    return Path(v) if v else None


def _env_paths(name: str) -> list[Path]:
    v = os.environ.get(name)
    return [Path(p) for p in v.split(os.pathsep)] if v else []

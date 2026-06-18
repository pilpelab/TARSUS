"""Tool environment resolver.

Locates all external tools and provides the correct environment
variables for subprocess invocation. All paths are relative to
the tools directory, configurable via TARSUS_TOOLS_DIR env var.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolEnvironment:
    """Resolve paths to all external tools in the project.

    Tools are expected in <tools_dir>/ (default: repo-root/tools/).
    Override via TARSUS_TOOLS_DIR environment variable.
    """

    tools_dir: Path

    @classmethod
    def from_env(cls) -> "ToolEnvironment":
        """Create from TARSUS_TOOLS_DIR env var, defaulting to tools/."""
        default = Path(__file__).resolve().parent.parent.parent / "tools"
        tools_dir = Path(os.environ.get("TARSUS_TOOLS_DIR", default))
        return cls(tools_dir=tools_dir)

    # ── Runtimes ──────────────────────────────────────────────────────

    @property
    def java_home(self) -> Path:
        return self.tools_dir / "jdk-21.0.11"

    @property
    def java_bin(self) -> Path:
        return self.java_home / "bin" / "java"

    @property
    def dotnet_root(self) -> Path:
        return self.tools_dir / "dotnet-8.0.28"

    @property
    def dotnet_bin(self) -> Path:
        return self.dotnet_root / "dotnet"

    # ── Proteomics Tools ───────────────────────────────────────────────

    @property
    def fragpipe_dir(self) -> Path:
        return self.tools_dir / "fragpipe-24.0"

    @property
    def fragpipe_bin(self) -> Path:
        return self.fragpipe_dir / "bin" / "fragpipe"

    @property
    def pepquery_jar(self) -> Path:
        return self.tools_dir / "pepquery-2.0.2" / "pepquery-2.0.2.jar"

    @property
    def pepquery_lib(self) -> Path:
        return self.tools_dir / "pepquery-2.0.2" / "lib"

    @property
    def pepquery_classpath(self) -> str:
        return f"{self.pepquery_jar}:{self.pepquery_lib}/*"

    @property
    def pdv_jar(self) -> Path:
        return self.tools_dir / "PDV-2.2.3" / "PDV-2.2.3.jar"

    @property
    def thermorawfileparser_bin(self) -> Path:
        return self.tools_dir / "thermorawfileparser-2.0.0-dev" / "ThermoRawFileParser"

    # ── Environment ────────────────────────────────────────────────────

    def env(self) -> dict[str, str]:
        """Return an env dict suitable for subprocess.run()."""
        env = os.environ.copy()
        env["JAVA_HOME"] = str(self.java_home)
        env["DOTNET_ROOT"] = str(self.dotnet_root)
        # Prepend to PATH so tools/jdk-21.0.11/bin/java is found first
        env["PATH"] = (
            f"{self.java_home}/bin:{self.dotnet_root}"
            f"{os.pathsep}{env.get('PATH', '')}"
        )
        # Limit GC heap to prevent startup OOM on some Linux kernels.
        # 4 GB (0x100000000) matches LSF --mem=7000 request.
        # Astral DDA raw files with ~350k scans need ~3-4 GB.
        env["DOTNET_GCHeapHardLimit"] = "0x100000000"
        return env

    def verify(self) -> dict[str, tuple[bool, str]]:
        """Check that all tools exist. Returns {tool: (ok, message)}."""
        checks: dict[str, tuple[bool, str]] = {}
        for name, path in [
            ("java", self.java_bin),
            ("dotnet", self.dotnet_bin),
            ("fragpipe", self.fragpipe_bin),
            ("pepquery", self.pepquery_jar),
            ("pdv", self.pdv_jar),
            ("thermorawfileparser", self.thermorawfileparser_bin),
        ]:
            if path.exists():
                checks[name] = (True, str(path))
            else:
                checks[name] = (False, f"missing: {path}")
        return checks

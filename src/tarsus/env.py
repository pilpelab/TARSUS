"""Tool environment resolver.

Locates all external tools and provides the correct environment
variables for subprocess invocation. All paths are relative to
the tools directory, configurable via TARSUS_TOOLS_DIR env var.

Also provides XvfbDisplay — a context manager that ensures an X11
display is available for GUI tools (PDV) that require one. Uses the
existing $DISPLAY if set; otherwise starts a virtual Xvfb framebuffer
from the cluster's EasyBuild module tree (no sudo required).
"""

import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


# ── Xvfb virtual display ─────────────────────────────────────────────


class XvfbDisplay:
    """Context manager that ensures an X11 display is available.

    If ``$DISPLAY`` is already set, uses it as-is (no Xvfb needed).
    Otherwise locates and starts an Xvfb virtual framebuffer on the
    cluster's EasyBuild software tree and sets ``$DISPLAY`` accordingly.

    Usage::

        with XvfbDisplay() as display_env:
            subprocess.run(["java", "-jar", "PDV.jar", ...], env=display_env)

    Raises ``RuntimeError`` if no display is available and Xvfb cannot
    be found or started.
    """

    _XVFB_SEARCH_PATHS = [
        "/apps/easybd/easybuild/amd/software/Xvfb",
    ]

    def __init__(self) -> None:
        self._xvfb_proc: "subprocess.Popen[bytes] | None" = None
        self._display: str | None = None

    @staticmethod
    def _find_xvfb() -> str | None:
        """Locate the Xvfb binary.

        Searches EasyBuild software tree (latest version first), then PATH.
        """
        for base in XvfbDisplay._XVFB_SEARCH_PATHS:
            basepath = Path(base)
            if not basepath.is_dir():
                continue
            # Sort descending so newest version is tried first
            versions = sorted(basepath.iterdir(), reverse=True)
            for ver_dir in versions:
                xvfb = ver_dir / "bin" / "Xvfb"
                if xvfb.is_file():
                    return str(xvfb)
        return shutil.which("Xvfb")

    def __enter__(self) -> dict[str, str]:
        # If user already has a display, use it
        existing = os.environ.get("DISPLAY")
        if existing:
            self._display = existing
            return os.environ.copy()

        xvfb_bin = self._find_xvfb()
        if not xvfb_bin:
            raise RuntimeError(
                "No X11 display available and Xvfb not found. "
                "Run: module load Xvfb && Xvfb :99 -screen 0 1024x768x24 &"
            )

        # Try display numbers starting from 99 downward
        for disp in (":99", ":98", ":97", ":96"):
            try:
                self._xvfb_proc = subprocess.Popen(
                    [xvfb_bin, disp, "-screen", "0", "1024x768x24"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(0.3)  # Let Xvfb initialize
                self._display = disp
                break
            except FileNotFoundError:
                continue

        if self._xvfb_proc is None:
            raise RuntimeError("Failed to start Xvfb on any display port.")

        env = os.environ.copy()
        assert self._display is not None  # guaranteed by __enter__ branches
        env["DISPLAY"] = self._display
        return env

    def __exit__(self, *args: object) -> None:
        if self._xvfb_proc is not None:
            self._xvfb_proc.terminate()
            try:
                self._xvfb_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._xvfb_proc.kill()
                self._xvfb_proc.wait()


# ── Tool environment ─────────────────────────────────────────────────


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
        return self.tools_dir / "PDV-2.1.2" / "PDV-2.1.2.jar"

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

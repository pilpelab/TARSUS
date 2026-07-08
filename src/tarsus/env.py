"""Tool environment resolver.

Locates all external tools and provides the correct environment
variables for subprocess invocation. All paths are relative to
the tools directory, configurable via TARSUS_TOOLS_DIR env var.

Also provides XvfbDisplay — a context manager that ensures an X11
display is available for GUI tools (PDV) that require one. Uses the
existing $DISPLAY if set; otherwise starts a self-contained virtual
Xvfb framebuffer bundled in tools/xvfb/ (binary + its shared libs,
no cluster module system / `module load` required, no sudo required).
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

    If ``$DISPLAY`` is already set, uses it as-is (no Xvfb needed) —
    this lets a user with their own X server / VNC session skip Xvfb
    entirely. Otherwise starts the self-contained Xvfb bundled at
    ``tools/xvfb/`` (binary + all its non-universal shared libs,
    fetched once via ``make xvfb`` — see tools/README.md). No
    ``module load`` and no cluster-specific paths are used at runtime.

    Usage::

        with XvfbDisplay() as display_env:
            subprocess.run(["java", "-jar", "PDV.jar", ...], env=display_env)

    Raises ``RuntimeError`` if no display is available and the bundled
    Xvfb cannot be found or started.
    """

    def __init__(self, tools_dir: Path | None = None) -> None:
        self._xvfb_proc: "subprocess.Popen[bytes] | None" = None
        self._display: str | None = None
        if tools_dir is None:
            tools_dir = Path(__file__).resolve().parent.parent.parent / "tools"
        self._xvfb_bin = tools_dir / "xvfb" / "bin" / "Xvfb"
        self._xvfb_lib = tools_dir / "xvfb" / "lib"

    def __enter__(self) -> dict[str, str]:
        # If user already has a display, use it
        existing = os.environ.get("DISPLAY")
        if existing:
            self._display = existing
            return os.environ.copy()

        xvfb_bin = self._xvfb_bin
        if not xvfb_bin.is_file():
            # Fall back to a system Xvfb on PATH, if any (e.g. dev laptop).
            found = shutil.which("Xvfb")
            if not found:
                raise RuntimeError(
                    f"No X11 display available and no bundled Xvfb found at "
                    f"{xvfb_bin}. Run `make xvfb` in tools/ to fetch it, or "
                    f"set $DISPLAY to an existing X11/VNC session."
                )
            xvfb_bin = Path(found)
            ld_lib_path = os.environ.get("LD_LIBRARY_PATH", "")
        else:
            # Self-contained: only our own bundled lib dir, no system paths
            # relied upon beyond the universal libc/libm/libpthread/ld-linux
            # baseline that every glibc Linux system already provides.
            existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
            ld_lib_path = f"{self._xvfb_lib}:{existing_ld}" if existing_ld else str(self._xvfb_lib)

        errors: list[str] = []
        # Many PDV shard jobs may land on the same compute node. Each needs
        # its own Xvfb display, so try a broad range rather than only the
        # traditional :99..:96 set. Xvfb itself arbitrates races via /tmp
        # .X*-lock files; if one candidate is busy, we move to the next.
        display_numbers = list(range(99, 49, -1)) + list(range(100, 200))
        for display_number in display_numbers:
            disp = f":{display_number}"
            proc_env = os.environ.copy()
            proc_env["LD_LIBRARY_PATH"] = ld_lib_path
            proc = subprocess.Popen(
                [str(xvfb_bin), disp, "-screen", "0", "1024x768x24"],
                env=proc_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            # Xvfb + its xkbcomp keymap-compile helper can take a couple of
            # seconds to become ready; poll rather than a single fixed sleep.
            ready = False
            for _ in range(20):
                time.sleep(0.3)
                if proc.poll() is not None:
                    break  # died
                if Path(f"/tmp/.X11-unix/X{disp.lstrip(':')}").exists():
                    ready = True
                    break
            if ready:
                self._xvfb_proc = proc
                self._display = disp
                break
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            errors.append(f"{disp}: {stderr.strip()}")

        if self._xvfb_proc is None:
            details = "\n".join(errors) or "no candidates attempted"
            raise RuntimeError(
                f"Failed to start bundled Xvfb ({xvfb_bin}) on any display port:\n{details}"
            )

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

"""Unit tests for ToolEnvironment — no external tools required."""

import os
from pathlib import Path

import pytest

from src.tarsus.env import ToolEnvironment


class TestToolEnvironment:
    def test_from_env_default(self, tmp_path: Path) -> None:
        env = ToolEnvironment.from_env()
        assert isinstance(env.tools_dir, Path)
        assert env.tools_dir.name == "tools"

    def test_from_env_custom(self) -> None:
        custom = "/custom/tools"
        os.environ["TARSUS_TOOLS_DIR"] = custom
        try:
            env = ToolEnvironment.from_env()
            assert str(env.tools_dir) == custom
        finally:
            del os.environ["TARSUS_TOOLS_DIR"]

    def test_from_env_custom_not_a_dir(self) -> None:
        os.environ["TARSUS_TOOLS_DIR"] = "/nonexistent"
        try:
            env = ToolEnvironment.from_env()
            assert str(env.tools_dir) == "/nonexistent"
        finally:
            del os.environ["TARSUS_TOOLS_DIR"]

    def test_java_home(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.java_home == Path("/t/jdk-21.0.11")

    def test_java_bin(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.java_bin == Path("/t/jdk-21.0.11/bin/java")

    def test_dotnet_root(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.dotnet_root == Path("/t/dotnet-8.0.28")

    def test_dotnet_bin(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.dotnet_bin == Path("/t/dotnet-8.0.28/dotnet")

    def test_fragpipe_dir(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.fragpipe_dir == Path("/t/fragpipe-24.0")

    def test_fragpipe_bin(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.fragpipe_bin == Path("/t/fragpipe-24.0/bin/fragpipe")

    def test_pepquery_jar(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.pepquery_jar == Path("/t/pepquery-2.0.2/pepquery-2.0.2.jar")

    def test_pepquery_lib(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.pepquery_lib == Path("/t/pepquery-2.0.2/lib")

    def test_pepquery_classpath(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        expected = f"{Path('/t/pepquery-2.0.2/pepquery-2.0.2.jar')}:{Path('/t/pepquery-2.0.2/lib')}/*"
        assert env.pepquery_classpath == expected

    def test_pdv_jar(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.pdv_jar == Path("/t/PDV-2.1.2/PDV-2.1.2.jar")

    def test_thermorawfileparser_bin(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        assert env.thermorawfileparser_bin == Path(
            "/t/thermorawfileparser-2.0.0-dev/ThermoRawFileParser"
        )

    def test_env_dict_contains_keys(self) -> None:
        env = ToolEnvironment(tools_dir=Path("/t"))
        result = env.env()
        assert "JAVA_HOME" in result
        assert "DOTNET_ROOT" in result
        assert "DOTNET_GCHeapHardLimit" in result
        assert result["JAVA_HOME"] == "/t/jdk-21.0.11"
        assert result["DOTNET_ROOT"] == "/t/dotnet-8.0.28"
        assert result["DOTNET_GCHeapHardLimit"] == "0x100000000"

    def test_env_dict_inherits_os_env(self) -> None:
        os.environ["TARSUS_TEST_MARKER"] = "should_be_present"
        try:
            env = ToolEnvironment(tools_dir=Path("/t"))
            result = env.env()
            assert result["TARSUS_TEST_MARKER"] == "should_be_present"
        finally:
            del os.environ["TARSUS_TEST_MARKER"]

    def test_env_dict_path_prepends_java_and_dotnet(self) -> None:
        orig_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = "/usr/bin"
            env = ToolEnvironment(tools_dir=Path("/t"))
            result = env.env()
            path_parts = result["PATH"].split(os.pathsep)
            assert path_parts[0] == "/t/jdk-21.0.11/bin"
            assert path_parts[1] == "/t/dotnet-8.0.28"
            assert path_parts[2] == "/usr/bin"
        finally:
            os.environ["PATH"] = orig_path

    def test_verify_all_missing(self, tmp_path: Path) -> None:
        env = ToolEnvironment(tools_dir=tmp_path)
        checks = env.verify()
        assert all(not ok for ok, _ in checks.values())
        for tool, (ok, msg) in checks.items():
            assert not ok
            assert "missing" in msg

    def test_verify_one_present(self, tmp_path: Path) -> None:
        (tmp_path / "jdk-21.0.11" / "bin").mkdir(parents=True)
        (tmp_path / "jdk-21.0.11" / "bin" / "java").touch()
        env = ToolEnvironment(tools_dir=tmp_path)
        checks = env.verify()
        assert checks["java"] == (True, str(tmp_path / "jdk-21.0.11" / "bin" / "java"))
        assert not checks["dotnet"][0]


class TestXvfbDisplayAllocation:
    """Regression: concurrent PDV shards on one host must not share a display.

    The old implementation scanned :99, :98, ... and considered a candidate
    "ready" as soon as /tmp/.X11-unix/X<n> appeared. When two workers landed on
    the same compute node, the second saw the socket the *first* had created,
    declared itself ready, and adopted the first worker's display even though
    its own Xvfb had died on the lock file. When the first worker exited it tore
    down that Xvfb, and the second lost its X connection mid-render: PDV wrote a
    partial PDVExportResult.txt and exited 1 with no Java exception.

    Observed live: of four shards co-scheduled on cn810, exactly one survived;
    every shard that had a host to itself succeeded.
    """

    def test_four_concurrent_displays_are_distinct_and_owned(self) -> None:
        """Four concurrent servers — the exact multiplicity seen on cn810."""
        import os as _os
        from src.tarsus.env import XvfbDisplay

        tools = Path(__file__).resolve().parents[2] / "tools"
        if not (tools / "xvfb" / "bin" / "Xvfb").is_file():
            pytest.skip("bundled Xvfb not present (run `make xvfb`)")

        # XvfbDisplay short-circuits when $DISPLAY is already set.
        prev = _os.environ.pop("DISPLAY", None)
        opened: list[XvfbDisplay] = []
        try:
            displays: list[str] = []
            for _ in range(4):
                d = XvfbDisplay(tools)
                env = d.__enter__()
                opened.append(d)
                displays.append(env["DISPLAY"])

            assert len(set(displays)) == 4, (
                f"concurrent XvfbDisplay instances shared a display: {displays}"
            )
            for d in opened:
                # Each instance must own a live X server, not squat on another's.
                assert d._xvfb_proc is not None
                assert d._xvfb_proc.poll() is None, "adopted a display it does not own"
        finally:
            for d in reversed(opened):
                d.__exit__()
            if prev is not None:
                _os.environ["DISPLAY"] = prev

"""Check the dedicated Recovered Homes MCP profile and optionally inspect a test copy."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROFILE = Path(__file__).resolve().with_name("home_podcast_mcp.json")
PROJECT_ID = "home-podcast"
PORT = 19871
BUILD = "2025.33230"
TEST_FOLDER = "home-podcast-envoy-test"
TOE = "podcast.41.toe"
APPROVED_SHA256 = "f664af7ac69ea0edc881dd9466673d3497f1d204f1e1598c0c1aea69ee306a21"
OWNER = "/project1/podcast_visualizer"
CONTROL = OWNER + "/show_control"
STEMS = ("voices_only_audio", "soundscape_audio", "combined_audio")
IDENTITY = [OWNER, CONTROL, OWNER + "/combined_audio"]
LIVE_TOOLS = {"get_sessions", "get_td_info", "query_network", "get_parameter"}
READ_TOOLS = LIVE_TOOLS | {"get_td_project_context", "get_td_server_health"}


class CheckError(RuntimeError):
    """Expected refusal with no credentials, arbitrary tool response or process output."""


def require(condition, message):
    if not condition:
        raise CheckError(message)


@dataclass(frozen=True)
class Layout:
    workspace: Path

    @property
    def bridge(self):
        return self.workspace / "td-knowledge-mcp"

    @property
    def index(self):
        return self.workspace / "td-ai-assistant/faiss_db"

    @property
    def staged_toe(self):
        return self.workspace / TEST_FOLDER / TOE


def verify_test_copy(layout):
    path = layout.staged_toe
    require(path.is_file() and path.resolve() == path and path.stat().st_nlink == 1
            and not (path.parent / ".git").exists(),
            "Use an ordinary, independent .41 copy in the dedicated sibling test folder.")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    require(digest.hexdigest() == APPROVED_SHA256, "The test copy is not the approved unmodified .41.")


def windows_transport_state():
    require(sys.platform == "win32", "This check requires Windows process and listener verification.")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    # Static command: no supplied path, parameter or protocol response becomes shell source.
    command = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$processes = @(Get-Process -Name TouchDesigner -ErrorAction SilentlyContinue |
    Select-Object Id,Path,MainWindowTitle)
$listeners = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 19871 |
    Select-Object LocalAddress,OwningProcess)
ConvertTo-Json -Compress -InputObject @{processes=$processes; listeners=$listeners}
"""
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
        check=False, capture_output=True, timeout=12,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    require(result.returncode == 0, "Could not verify Windows listener ownership.")
    return json.loads(result.stdout)


def verify_transport(layout, live, state):
    listeners = state["listeners"]
    if not live:
        require(not listeners, "Close the dedicated Envoy listener before a library-only check.")
        return
    processes = state["processes"]
    require(len(listeners) == len(processes) == 1,
            "Open only the isolated .41 test copy with one listener on port 19871.")
    process, listener = processes[0], listeners[0]
    expected_exe = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / (
        f"Derivative/TouchDesigner.{BUILD}/bin/TouchDesigner.exe"
    )
    expected_title = f"TouchDesigner {BUILD}: {layout.staged_toe.as_posix()}".casefold()
    actual_title = process["MainWindowTitle"].replace("\\", "/").casefold()
    require(actual_title == expected_title and Path(process["Path"]) == expected_exe
            and listener["OwningProcess"] == process["Id"]
            and listener["LocalAddress"] == "127.0.0.1",
            "The loopback listener is not owned by the dedicated .41 test session.")


async def call(client, name, arguments=None):
    require(name in READ_TOOLS, "Only the explicitly scoped read tools may be called.")
    reply = await client.call_tool(name, arguments or {})
    require(not reply.is_error, f"{name} failed.")
    value = reply.structured_content
    if value is None:
        blocks = [row.text for row in reply.content if row.type == "text"]
        require(len(blocks) == 1, f"Unrecognized reply from {name}.")
        value = json.loads(blocks[0])
    require(isinstance(value, dict) and not value.get("error") and not value.get("_peers"),
            f"{name} did not return a clean, single-session result.")
    return value


async def verify_connection(client, live):
    context = await call(client, "get_td_project_context", {"section": "network"})
    require(context.get("project_id") == PROJECT_ID and context.get("status") == "configured"
            and context["context"]["identity_operators"] == IDENTITY, "Wrong MCP project context.")
    tools = {item.name for item in (await client.list_tools()).tools}
    for _ in range(16):
        status = await call(client, "get_td_server_health")
        if status["knowledge"]["status"] != "loading":
            break
        await asyncio.sleep(0.5)
    knowledge, envoy = status["knowledge"], status["envoy"]
    require(envoy["endpoint_source"] == "fixed" and envoy["resolved_port"] == PORT,
            "The bridge did not keep the dedicated fixed endpoint.")
    require(knowledge["status"] == "online" and knowledge["total_chunks"] > 0,
            "The local TouchDesigner documentation index did not load.")
    result = {"project": PROJECT_ID, "port": PORT, "library_chunks": knowledge["total_chunks"],
              "envoy_status": envoy["status"], "live_checked": live, "writes_to_touchdesigner": 0}
    if not live:
        require(not LIVE_TOOLS.intersection(tools) and envoy["connected"] is False
                and envoy["status"] in {"offline", "backoff"},
                "Unexpected live tools or listener during the library-only check.")
        return result

    require(LIVE_TOOLS.issubset(tools) and envoy["identity_verified"] is True
            and envoy["connected"] is True and envoy["status"] == "online",
            "Envoy did not verify the isolated project identity.")
    sessions = (await call(client, "get_sessions"))["sessions"]
    require(isinstance(sessions, list) and not sessions,
            "Another MCP session is present; close or coordinate with it first.")
    td = await call(client, "get_td_info")
    require(td["version"] == f"099.{BUILD}", "Unexpected live TouchDesigner build.")
    network = await call(client, "query_network", {"parent_path": OWNER, "recursive": False})
    paths = {node["path"] for node in network["operators"]}
    require({CONTROL, *(OWNER + "/" + stem for stem in STEMS)}.issubset(paths),
            "The show network did not return Show Control and all three audio operators.")
    expected = {
        (CONTROL, "Runtimeprofile"): "3080_safe",
        (CONTROL, "Audiosource"): "combined",
        (CONTROL, "Play"): False,
        (CONTROL, "Livevariations"): False,
        (OWNER + "/audio_out", "active"): False,
    }
    for (path, name), want in expected.items():
        row = await call(client, "get_parameter", {"op_path": path, "par_name": name})
        value = str(row["value"])
        require(row["path"] == path and row["parameter"] == name
                and (value.lower() in {"0", "0.0", "false", "off"} if want is False else value == want),
                f"Unexpected show state for {name}; leave the test copy silent and generation off.")
    return dict(result, identity_verified=True, build=BUILD, audio_source="combined",
                playback_profile="3080_safe", audio_operators_verified=len(STEMS),
                live_parameters_verified=len(expected), show_play_off=True, audio_output_off=True)


async def verify_transport_session(transport, live):
    from mcp.client import Client

    failure = None
    async with Client(transport, read_timeout_seconds=10) as client:
        try:
            return await verify_connection(client, live)
        except CheckError as error:
            # Keep our safe refusal out of stdio's task-group exception wrapper.
            failure = error
    if failure is not None:
        raise failure
    raise CheckError("The bridge closed without an inspection report.")


def probe(layout, live):
    from mcp.client.stdio import StdioServerParameters, stdio_client

    python = layout.bridge / ".venv/Scripts/python.exe"
    bridge = layout.bridge / "td_knowledge_mcp.py"
    require(Path(sys.executable).resolve() == python and bridge.is_file()
            and bridge.resolve() == bridge and layout.index.is_dir()
            and layout.index.resolve() == layout.index,
            "Use the existing sibling TD Knowledge MCP Python and local documentation index.")
    with (tempfile.TemporaryDirectory(prefix="home-podcast-mcp-check-") as scratch,
          open(os.devnull, "w", encoding="utf-8") as stderr):
        parameters = StdioServerParameters(
            command=str(python), cwd=str(layout.bridge),
            args=["-B", "-u", str(bridge), "--port", str(PORT), "--faiss-db", str(layout.index),
                  "--project-context", str(PROFILE), "--envoy-command-timeout", "4"],
            env={"PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1", "NO_PROXY": "127.0.0.1,localhost",
                 # Index health needs no provider key. Override the bridge's dotenv fallback.
                 "GOOGLE_API_KEY": "local-index-validation-placeholder",
                 "GOOGLE_GENAI_USE_VERTEXAI": "false",
                 "TD_EMBED_CACHE": str(Path(scratch) / "unused-docs-cache")},
        )
        transport = stdio_client(parameters, errlog=stderr)
        return asyncio.run(asyncio.wait_for(verify_transport_session(transport, live), timeout=45))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Inspect only the staged .41 test copy.")
    parser.add_argument("--workspace-parent", type=Path,
                        default=PROFILE.parents[2], help="Local directory containing the sibling repos.")
    args = parser.parse_args(argv)
    try:
        layout = Layout(args.workspace_parent.resolve(strict=True))
        if args.live:
            verify_test_copy(layout)
        verify_transport(layout, args.live, windows_transport_state())
        report = probe(layout, args.live)
    except CheckError as error:
        print(f"3080 MCP not verified: {error}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 - SDK and subprocess errors may contain private payloads.
        print(f"3080 MCP check failed ({type(error).__name__}); no payloads printed.", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

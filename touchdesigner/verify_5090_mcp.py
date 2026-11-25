"""Verify the private 5090 .27 MCP test copy; never attach to .26 or 2d-3d."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from touchdesigner import verify_5090_audio_overlay as overlay


TEST_FOLDER = "home-podcast-5090-mcp-test"
PRODUCTION_TOE = "podcast.5090.26.toe"
TEST_TOE = "podcast.5090.27.toe"
INSTANCE = Path(TEST_TOE).stem
PROJECT_ID = "home-podcast-5090-mcp-test-27"
PORT = 10987
BUILD = "2025.32820"
OWNER = "/project1/podcast_visualizer"
IDENTITY = ["/rh_podcast_5090_27_mcp_guard", OWNER]
CONTROL = OWNER + "/show_control"
OFF = {"0", "0.0", "false", "off"}
NEGATIVE_PROFILE = {
    "schema_version": 1,
    "project_id": "podcast-5090-deliberate-mismatch",
    "network": {"identity_operators": ["/rh_mcp_negative_fixture_not_present"]},
}


class CheckError(RuntimeError):
    """An expected failure with no arbitrary MCP payload or credential text."""


def require(condition, message):
    if not condition:
        raise CheckError(message)


@dataclass(frozen=True)
class Layout:
    checkout: Path

    @property
    def test(self):
        return self.checkout.parent / TEST_FOLDER

    @property
    def bridge(self):
        return self.checkout.parent / "td-knowledge-mcp"

    @property
    def registry(self):
        return self.test / ".embody/envoy.json"

    @property
    def profile(self):
        return self.test / "podcast-project-context.json"


def plain_file(path):
    # Reject junctions and redirects as well as a missing file.
    require(path.is_file() and path.resolve() == path, f"Missing or redirected: {path.name}")
    return path


def read_object(path):
    with plain_file(path).open("rb") as stream:
        data = stream.read(64 * 1024 + 1)
    require(len(data) <= 64 * 1024, "Unexpected size for a private MCP JSON file.")
    value = json.loads(data)
    require(isinstance(value, dict), "Expected an object in a private MCP JSON file.")
    return value


def verify_hash(path, expected):
    require(isinstance(expected, str) and re.fullmatch("[0-9a-f]{64}", expected.lower()),
            "Invalid local TOE receipt hash.")
    digest = hashlib.sha256()
    with plain_file(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    require(digest.hexdigest() == expected.lower(), f"TOE no longer matches its receipt: {path.name}")


def verify_files(layout):
    require(layout.test != layout.checkout and layout.test.resolve() == layout.test,
            "Use a separate, non-redirected .27 test folder beside the production checkout.")
    initial = read_object(layout.test / "build-receipt.json")
    final = read_object(layout.test / "paused-clock-receipt.json")
    verify_hash(layout.checkout / PRODUCTION_TOE, initial.get("source_sha256"))
    require(final.get("original_playback_and_edition_bindings_unchanged") is True,
            "The local .27 binding verification receipt is missing or incomplete.")
    verify_hash(layout.test / TEST_TOE, final.get("sha256"))
    profile = read_object(layout.profile)
    require(profile.get("schema_version") == 1 and profile.get("project_id") == PROJECT_ID
            and profile.get("network", {}).get("identity_operators") == IDENTITY,
            "Unexpected podcast project identity profile.")


def registered_pid(layout):
    registry = read_object(layout.registry)
    entries = registry.get("instances", {})
    require(registry.get("active") == INSTANCE and isinstance(entries, dict)
            and set(entries) == {INSTANCE}, "The test registry must contain only the active .27.")
    entry = entries[INSTANCE]
    recorded = Path(entry["toe_path"])
    require(entry.get("port") == PORT and layout.test / recorded == layout.test / TEST_TOE,
            "The test registry does not name the isolated TOE and loopback port.")
    pid = entry.get("td_pid")
    require(type(pid) is int and pid > 0, "The test registry has no valid TouchDesigner PID.")
    return pid


def windows_listener():
    require(sys.platform == "win32", "The live check requires the 5090 Windows receiver.")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = """
$socket = @(Get-NetTCPConnection -State Listen -LocalPort 10987 -ErrorAction SilentlyContinue)
if ($socket.Count -ne 1 -or $socket[0].LocalAddress -ne '127.0.0.1') { exit 2 }
$process = Get-Process -Id $socket[0].OwningProcess -ErrorAction Stop
$tcp = @(Get-NetTCPConnection -OwningProcess $process.Id -State Listen -ErrorAction SilentlyContinue)
$udp = @(Get-NetUDPEndpoint -OwningProcess $process.Id -ErrorAction SilentlyContinue)
if ($tcp.Count -ne 1 -or $udp.Count -ne 0) { exit 3 }
@{pid=$process.Id; exe=$process.Path} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    require(result.returncode == 0, "No isolated .27 listener. Open only the private test copy first.")
    return json.loads(result.stdout)


def verify_listener(layout, probe=windows_listener):
    pid = registered_pid(layout)
    observed = probe()
    expected_exe = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / (
        f"Derivative/TouchDesigner.{BUILD}/bin/TouchDesigner.exe"
    )
    require(observed.get("pid") == pid and Path(observed["exe"]) == expected_exe,
            "The loopback listener does not belong to the registered TouchDesigner build and PID.")


async def call(client, tool, arguments=None):
    reply = await client.call_tool(tool, arguments or {})
    require(not reply.is_error, f"{tool} failed.")
    data = reply.structured_content
    if data is None:
        data = json.loads(next(block.text for block in reply.content if block.type == "text"))
    require(isinstance(data, dict) and not data.get("error"), f"{tool} returned an error.")
    return data


def expected_parameters(layout):
    expected = {(CONTROL, "Runtimeprofile"): "3080_safe",
                (CONTROL, "Audiosource"): "combined",
                (OWNER + "/audiosource_switch", "index"): "2"}
    for node, mode in (("voices_only_audio", "voices_only"),
                       ("soundscape_audio", "soundscape_only"), ("combined_audio", "combined")):
        expected[(OWNER + "/" + node, "playmode")] = "locked"
        expected[(OWNER + "/" + node, "file")] = layout.checkout / overlay.AUDIO[mode]
    for name in ("Play", "Livevariations", "Audioenabled"):
        expected[(CONTROL, name)] = False
    for node in ("audio_out", "syphonspoutout1", "syphonspoutout2"):
        expected[(OWNER + "/" + node, "active")] = False
    for node in ("StreamDiffusionTD", "StreamDiffusionTD2"):
        for name in ("Serveractive", "Streamactive"):
            expected[(OWNER + "/" + node, name)] = False
    expected[(OWNER, "Playlistmanifest")] = layout.checkout / overlay.OVERLAY_PLAYLIST
    for name, path_id in zip(("Scenejson", "Humanfigurejson", "Balancedjson"), overlay.MODES):
        expected[(OWNER, name)] = layout.checkout / overlay.OVERLAY / f"{path_id}-visual-scenes.json"
    for name, stem in (("Livecontroljson", "control"), ("Livestatusjson", "status"),
                       ("Livecurrentjson", "current")):
        expected[(OWNER, name)] = layout.test / "receiver-runtime" / f"{stem}.json"
    return expected


async def verify_parameters(client, layout):
    expected = expected_parameters(layout)
    operations = [{"tool": "get_parameter", "params": {"op_path": op, "par_name": par}}
                  for op, par in expected]
    reply = await call(client, "batch_operations", {"operations": operations})
    require(reply.get("success") is True and reply["count"] == len(expected),
            "The read-only parameter batch did not complete.")
    values = {(row["path"], row["parameter"]): row["value"] for row in reply["results"]}
    require(values.keys() == expected.keys() and len(values) == len(reply["results"]),
            "Unexpected parameter batch results.")
    for key, want in expected.items():
        value = values[key]
        if isinstance(want, Path):
            path = Path(value)
            matches = path.is_absolute() and path.resolve() == want.resolve()
        else:
            matches = str(value).lower() in OFF if want is False else str(value) == want
        require(matches, f"Unexpected .27 parameter state: {key[0]}.{key[1]}")
    return len(expected)


async def verify_connection(client, layout):
    context = await call(client, "get_td_project_context", {"section": "network"})
    require(context["project_id"] == PROJECT_ID and context["context"]["identity_operators"] == IDENTITY,
            "The bridge did not load the .27 identity profile.")
    tools = {tool.name for tool in (await client.list_tools()).tools}
    health = (await call(client, "get_td_server_health"))["envoy"]
    require(health["status"] == "online" and health["identity_verified"] is True
            and health["resolved_port"] == PORT and health["endpoint_source"] == "registry",
            "The .27 live identity did not verify.")
    sessions = await call(client, "get_sessions")
    require(sessions["count"] == 0 and not sessions["sessions"],
            "Another live session is using the test copy; coordinate before probing.")
    info = await call(client, "get_td_info")
    require(info["version"] == f"099.{BUILD}", "Unexpected running TouchDesigner build.")
    network = await call(client, "query_network", {"parent_path": OWNER, "recursive": False})
    require(network["parent"] == OWNER and network["count"] > 0, "Unexpected podcast network.")
    parameters = await verify_parameters(client, layout)
    for _ in range(20):
        docs = await call(client, "get_knowledge_stats")
        if docs["status"] != "loading":
            break
        await asyncio.sleep(0.5)
    require(docs["status"] == "online" and docs["total_chunks"] > 0, "The local TD library did not load.")
    return dict(touchdesigner=info["version"], envoy_version=info["envoyVersion"],
                discovered_tools=len(tools), podcast_operators_read=network["count"],
                live_parameters_verified=parameters, local_docs_chunks=docs["total_chunks"])


async def verify_rejection(client):
    tools = {tool.name for tool in (await client.list_tools()).tools}
    health = (await call(client, "get_td_server_health"))["envoy"]
    require(not tools.intersection({"get_td_info", "query_network", "batch_operations", "execute_python"})
            and health["status"] == "identity_error" and health["identity_verified"] is False
            and health["resolved_port"] == PORT, "The bridge did not reject a wrong project identity.")
    denied = await client.call_tool("get_td_info", {})
    require(denied.is_error, "The bridge accepted a live call with the wrong identity.")


async def live_smoke(layout):
    import anyio
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client

    python = plain_file(layout.bridge / ".venv/Scripts/python.exe")
    require(Path(sys.executable).resolve() == python, "Run --live with the existing TD Knowledge MCP Python.")
    bridge = plain_file(layout.bridge / "td_knowledge_mcp.py")
    faiss = layout.checkout.parent / "td-ai-assistant/faiss_db"
    require(faiss.is_dir() and faiss.resolve() == faiss, "Missing local TouchDesigner library.")

    def transport(registry, profile, stderr):
        verify_listener(layout)
        params = StdioServerParameters(
            command=str(python), cwd=str(layout.bridge),
            args=["-B", "-u", str(bridge), "--faiss-db", str(faiss),
                  "--envoy-config", str(registry), "--project-context", str(profile),
                  "--envoy-command-timeout", "8"],
            env={"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
                 # Stats load the index but never ask Google for an embedding.
                 "GOOGLE_API_KEY": "local-index-validation-placeholder",
                 "GOOGLE_GENAI_USE_VERTEXAI": "false",
                 "TD_EMBED_CACHE": str(profile.parent / "unused-docs-cache")},
        )
        return stdio_client(params, errlog=stderr)

    with (anyio.fail_after(50), tempfile.TemporaryDirectory(prefix="podcast-5090-mcp-check-") as work,
          open(os.devnull, "w", encoding="utf-8") as err):
        scratch = Path(work)
        registry = scratch / "envoy.json"
        # Pin the scope of both probes even if Embody rewrites its registry mid-check.
        registry.write_text(json.dumps({"active": INSTANCE, "instances": {INSTANCE: {"port": PORT}}}),
                            encoding="utf-8")
        profile = scratch / "podcast-profile.json"
        profile.write_text(json.dumps({"schema_version": 1, "project_id": PROJECT_ID,
                                       "network": {"identity_operators": IDENTITY}}), encoding="utf-8")
        wrong = scratch / "wrong-identity.json"
        wrong.write_text(json.dumps(NEGATIVE_PROFILE), encoding="utf-8")
        async with Client(transport(registry, profile, err), read_timeout_seconds=14) as client:
            report = await verify_connection(client, layout)
        async with Client(transport(registry, wrong, err), read_timeout_seconds=14) as client:
            await verify_rejection(client)
    return dict(report, loopback_port=PORT, wrong_identity_rejected=True, writes_to_touchdesigner=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Probe only the already-open isolated .27.")
    args = parser.parse_args(argv)
    layout = Layout(Path(__file__).resolve().parents[1])
    try:
        verify_files(layout)
        report = dict(passed=True, project=TEST_TOE, production=PRODUCTION_TOE, live_checked=args.live)
        if args.live:
            import anyio
            report.update(anyio.run(live_smoke, layout))
    except CheckError as error:
        print(f"5090 MCP not verified: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"5090 MCP check failed ({type(error).__name__}); no payloads printed.", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

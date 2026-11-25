import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from touchdesigner import verify_3080_mcp as mcp


class TransportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.layout = mcp.Layout(Path(directory.name).resolve())
        self.process = {
            "Id": 123,
            "Path": str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) /
                        f"Derivative/TouchDesigner.{mcp.BUILD}/bin/TouchDesigner.exe"),
            "MainWindowTitle": f"TouchDesigner {mcp.BUILD}: {self.layout.staged_toe.as_posix()}",
        }
        self.listener = {"OwningProcess": 123, "LocalAddress": "127.0.0.1"}

    def test_guarded_scratch_copy_must_match_the_approved_hash(self):
        target = self.layout.staged_toe
        target.parent.mkdir()
        target.write_bytes(b"fixture")
        with patch.object(mcp, "APPROVED_SHA256", hashlib.sha256(b"fixture").hexdigest()):
            mcp.verify_test_copy(self.layout)
            target.write_bytes(b"changed")
            with self.assertRaisesRegex(mcp.CheckError, "not the approved"):
                mcp.verify_test_copy(self.layout)

    def test_git_managed_toe_cannot_be_the_scratch_copy(self):
        target = self.layout.staged_toe
        target.parent.mkdir()
        target.write_bytes(b"fixture")
        (target.parent / ".git").mkdir()
        with self.assertRaisesRegex(mcp.CheckError, "independent .41 copy"):
            mcp.verify_test_copy(self.layout)

    def test_hardlinked_toe_cannot_be_the_scratch_copy(self):
        target = self.layout.staged_toe
        target.parent.mkdir()
        source = self.layout.workspace / "original.toe"
        source.write_bytes(b"fixture")
        try:
            os.link(source, target)
        except OSError:
            self.skipTest("Hard links are unavailable in this test directory")
        with self.assertRaisesRegex(mcp.CheckError, "independent .41 copy"):
            mcp.verify_test_copy(self.layout)

    def test_live_requires_matching_title_executable_and_loopback_owner(self):
        state = {"listeners": [self.listener], "processes": [self.process]}
        mcp.verify_transport(self.layout, True, state)
        for area, field, value in (
            ("listeners", "LocalAddress", "0.0.0.0"),
            ("listeners", "OwningProcess", 321),
            ("processes", "MainWindowTitle", "TouchDesigner: podcast.5090.27.toe"),
            ("processes", "Path", "C:/Programs/Other/TouchDesigner.exe"),
        ):
            with self.subTest(field=field):
                wrong = copy.deepcopy(state)
                wrong[area][0][field] = value
                with self.assertRaisesRegex(mcp.CheckError, "not owned"):
                    mcp.verify_transport(self.layout, True, wrong)

    def test_extra_touchdesigner_process_and_busy_library_port_are_refused(self):
        state = {"listeners": [self.listener], "processes": [self.process, {"Id": 234}]}
        with self.assertRaisesRegex(mcp.CheckError, "Open only"):
            mcp.verify_transport(self.layout, True, state)
        with self.assertRaisesRegex(mcp.CheckError, "Close the dedicated"):
            mcp.verify_transport(self.layout, False, state)
        mcp.verify_transport(self.layout, False, {"listeners": [], "processes": [self.process]})


class FakeClient:
    def __init__(self, live):
        self.calls = []
        self.tools = set(mcp.READ_TOOLS if live else mcp.READ_TOOLS - mcp.LIVE_TOOLS)
        if live:
            self.tools.add("execute_python")
        self.responses = {
            "get_td_project_context": {"project_id": mcp.PROJECT_ID, "status": "configured",
                                       "context": {"identity_operators": mcp.IDENTITY}},
            "get_td_server_health": {
                "envoy": {"status": "online" if live else "backoff", "connected": live,
                          "identity_verified": live, "endpoint_source": "fixed",
                          "resolved_port": mcp.PORT},
                "knowledge": {"status": "online", "total_chunks": 2900},
            },
            "get_sessions": {"sessions": []},
            "get_td_info": {"version": f"099.{mcp.BUILD}"},
            "query_network": {"operators": [{"path": mcp.OWNER + "/" + name}
                                            for name in ("show_control", *mcp.STEMS)]},
        }
        self.values = {"Audiosource": "combined", "Runtimeprofile": "3080_safe",
                       "Play": "False", "Livevariations": "False", "active": "False"}

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in self.tools])

    async def call_tool(self, name, arguments):
        self.calls.append(name)
        if name == "get_parameter":
            parameter = arguments["par_name"]
            value = {"path": arguments["op_path"], "parameter": parameter,
                     "value": self.values[parameter]}
        else:
            value = self.responses[name]
        return SimpleNamespace(is_error=False, structured_content=value)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_context_matches_private_identity_guard(self):
        context = json.loads(mcp.PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(context["project_id"], mcp.PROJECT_ID)
        self.assertEqual(context["network"]["identity_operators"], mcp.IDENTITY)
        self.assertEqual(context["overview"]["tested_envoy_build"], mcp.BUILD)

    async def test_library_only_checks_index_and_uses_no_live_calls(self):
        client = FakeClient(False)
        result = await mcp.verify_connection(client, False)
        self.assertEqual(result["library_chunks"], 2900)
        self.assertFalse(result["live_checked"])
        self.assertEqual(client.calls, ["get_td_project_context", "get_td_server_health"])

    async def test_library_failure_or_unexpected_live_catalog_cannot_pass(self):
        client = FakeClient(False)
        client.responses["get_td_server_health"]["knowledge"]["status"] = "offline"
        with self.assertRaisesRegex(mcp.CheckError, "did not load"):
            await mcp.verify_connection(client, False)
        client = FakeClient(False)
        client.tools.update(mcp.LIVE_TOOLS)
        with self.assertRaisesRegex(mcp.CheckError, "Unexpected live tools"):
            await mcp.verify_connection(client, False)

    async def test_identity_endpoint_and_peer_guards_precede_inspection(self):
        for key, value in (("identity_verified", False), ("resolved_port", 9870),
                           ("endpoint_source", "registry")):
            with self.subTest(key=key):
                client = FakeClient(True)
                client.responses["get_td_server_health"]["envoy"][key] = value
                with self.assertRaises(mcp.CheckError):
                    await mcp.verify_connection(client, True)
                self.assertNotIn("get_sessions", client.calls)
        client = FakeClient(True)
        client.responses["get_sessions"]["sessions"] = [{}]
        with self.assertRaisesRegex(mcp.CheckError, "Another MCP session"):
            await mcp.verify_connection(client, True)
        self.assertNotIn("get_td_info", client.calls)

    async def test_live_checks_audio_output_and_never_calls_mutating_tools(self):
        client = FakeClient(True)
        result = await mcp.verify_connection(client, True)
        self.assertEqual(result["audio_operators_verified"], 3)
        self.assertEqual(result["live_parameters_verified"], 5)
        self.assertEqual(result["writes_to_touchdesigner"], 0)
        self.assertTrue(result["audio_output_off"])
        self.assertTrue(set(client.calls).issubset(mcp.READ_TOOLS))
        with self.assertRaisesRegex(mcp.CheckError, "read tools"):
            await mcp.call(client, "execute_python")
        self.assertNotIn("execute_python", client.calls)

    async def test_active_output_or_live_variations_fail(self):
        for name in ("Play", "Livevariations", "active"):
            with self.subTest(parameter=name):
                client = FakeClient(True)
                client.values[name] = "True"
                with self.assertRaisesRegex(mcp.CheckError, "Unexpected show state"):
                    await mcp.verify_connection(client, True)


if __name__ == "__main__":
    unittest.main()

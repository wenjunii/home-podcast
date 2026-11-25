import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from touchdesigner import verify_5090_mcp as mcp


class PrivateCopyTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.layout = mcp.Layout(Path(work.name).resolve() / "home-podcast")
        self.layout.checkout.mkdir()
        self.layout.registry.parent.mkdir(parents=True)
        self.production = self.layout.checkout / mcp.PRODUCTION_TOE
        self.candidate = self.layout.test / mcp.TEST_TOE
        self.production.write_bytes(b"production fixture")
        self.candidate.write_bytes(b"test fixture")
        self.json_file(self.layout.test / "build-receipt.json", {
            "source_sha256": hashlib.sha256(self.production.read_bytes()).hexdigest(),
        })
        self.json_file(self.layout.test / "paused-clock-receipt.json", {
            "sha256": hashlib.sha256(self.candidate.read_bytes()).hexdigest(),
            "original_playback_and_edition_bindings_unchanged": True,
        })
        self.json_file(self.layout.profile, {
            "schema_version": 1, "project_id": mcp.PROJECT_ID,
            "network": {"identity_operators": mcp.IDENTITY},
        })
        self.entry = {"port": mcp.PORT, "toe_path": mcp.TEST_TOE, "td_pid": 123}

    @staticmethod
    def json_file(path, body):
        path.write_text(json.dumps(body), encoding="utf-8")

    def register(self, entry=None, **other):
        self.json_file(self.layout.registry, {
            "active": mcp.INSTANCE, "instances": {mcp.INSTANCE: entry or self.entry, **other},
        })

    def test_offline_check_does_not_require_a_running_listener(self):
        self.assertFalse(self.layout.registry.exists())
        mcp.verify_files(self.layout)

    def test_changed_toe_is_refused_for_either_copy(self):
        for path in (self.production, self.candidate):
            with self.subTest(file=path.name):
                intact = path.read_bytes()
                path.write_bytes(intact + b"drift")
                with self.assertRaisesRegex(mcp.CheckError, "TOE no longer matches"):
                    mcp.verify_files(self.layout)
                path.write_bytes(intact)

    def test_other_identity_is_refused_offline(self):
        self.json_file(self.layout.profile, mcp.NEGATIVE_PROFILE)
        with self.assertRaisesRegex(mcp.CheckError, "Unexpected podcast project identity"):
            mcp.verify_files(self.layout)

    def test_shared_or_wrong_port_registry_never_probes_a_listener(self):
        probe = Mock(side_effect=AssertionError("must not probe an unexpected registry"))
        self.register(**{"2d-3d": {"port": 9870, "td_pid": 22}})
        with self.assertRaisesRegex(mcp.CheckError, "only the active .27"):
            mcp.verify_listener(self.layout, probe)
        for entry in (dict(self.entry, port=9870), dict(self.entry, toe_path=str(self.production)),
                      dict(self.entry, toe_path="../home-podcast/podcast.5090.27.toe")):
            self.register(entry)
            with self.assertRaisesRegex(mcp.CheckError, "isolated TOE and loopback port"):
                mcp.verify_listener(self.layout, probe)
        probe.assert_not_called()

    def test_listener_must_have_correct_pid_and_executable(self):
        self.register(dict(self.entry, toe_path=str(self.candidate)))
        exe = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / (
            f"Derivative/TouchDesigner.{mcp.BUILD}/bin/TouchDesigner.exe"
        )
        mcp.verify_listener(self.layout, lambda: {"pid": 123, "exe": str(exe)})
        for pid, path in ((124, exe), (123, exe.with_name("DifferentApp.exe"))):
            with self.subTest(pid=pid, exe=path.name):
                with self.assertRaisesRegex(mcp.CheckError, "registered TouchDesigner"):
                    mcp.verify_listener(self.layout, lambda: {"pid": pid, "exe": str(path)})


class FixtureClient:
    def __init__(self, *, wrong=False, leak=False, allow=False):
        self.wrong = wrong
        self.leak = leak
        self.allow = allow
        self.calls = []
        self.responses = {}

    async def list_tools(self):
        names = ["get_td_server_health", "get_td_project_context"]
        if not self.wrong or self.leak:
            names.extend(("query_network", "batch_operations", "get_td_info"))
        return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in names])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "get_td_server_health":
            result = {"envoy": {"status": "identity_error" if self.wrong else "online",
                                "identity_verified": not self.wrong, "resolved_port": mcp.PORT,
                                "endpoint_source": "registry"}}
        elif self.wrong and name == "get_td_info":
            return SimpleNamespace(is_error=not self.allow)
        else:
            result = self.responses[name]
        return SimpleNamespace(is_error=False, structured_content=result)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self):
        layout = mcp.Layout(Path.cwd().resolve() / "home-podcast")
        checks = mcp.expected_parameters(layout)
        client = FixtureClient()
        client.responses = {
            "get_td_project_context": {"project_id": mcp.PROJECT_ID,
                                       "context": {"identity_operators": mcp.IDENTITY}},
            "get_sessions": {"count": 0, "sessions": []},
            "get_td_info": {"version": "099.2025.32820", "envoyVersion": "1.4.0"},
            "query_network": {"parent": mcp.OWNER, "count": 36},
            "get_knowledge_stats": {"status": "online", "total_chunks": 2900},
            "batch_operations": {
                "success": True, "count": len(checks),
                "results": [{"path": op, "parameter": par, "value": str(value)}
                            for (op, par), value in checks.items()],
            },
        }
        return client, layout

    async def test_success_is_read_only_and_reports_counts(self):
        client, layout = self.make_client()
        report = await mcp.verify_connection(client, layout)
        self.assertEqual(report["live_parameters_verified"], 26)
        self.assertEqual(report["local_docs_chunks"], 2900)
        self.assertEqual([name for name, _ in client.calls], [
            "get_td_project_context", "get_td_server_health", "get_sessions", "get_td_info",
            "query_network", "batch_operations", "get_knowledge_stats",
        ])
        self.assertTrue(all(op["tool"] == "get_parameter" for op in client.calls[-2][1]["operations"]))

    async def test_shared_session_prevents_other_inspection(self):
        client, layout = self.make_client()
        client.responses["get_sessions"] = {"count": 1, "sessions": [{}]}
        with self.assertRaisesRegex(mcp.CheckError, "Another live session"):
            await mcp.verify_connection(client, layout)
        self.assertEqual(client.calls[-1][0], "get_sessions")

    async def test_changed_renderer_state_or_relative_binding_fails(self):
        for par, value in (("Serveractive", "True"), ("Playlistmanifest", mcp.overlay.OVERLAY_PLAYLIST)):
            with self.subTest(par=par):
                client, layout = self.make_client()
                rows = client.responses["batch_operations"]["results"]
                next(row for row in rows if row["parameter"] == par)["value"] = value
                with self.assertRaisesRegex(mcp.CheckError, "Unexpected .27 parameter state"):
                    await mcp.verify_connection(client, layout)

    async def test_negative_identity_must_hide_tools_and_reject_a_call(self):
        await mcp.verify_rejection(FixtureClient(wrong=True))
        with self.assertRaisesRegex(mcp.CheckError, "did not reject"):
            await mcp.verify_rejection(FixtureClient(wrong=True, leak=True))
        with self.assertRaisesRegex(mcp.CheckError, "accepted a live call"):
            await mcp.verify_rejection(FixtureClient(wrong=True, allow=True))


if __name__ == "__main__":
    unittest.main()

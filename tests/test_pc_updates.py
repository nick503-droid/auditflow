"""Pruebas aisladas: no usan datos personales, Docker ni GitHub reales."""

import contextlib
import http.server
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "pc-app"), str(REPO / "tools"), str(REPO / "deploy")]
from core import pc_updates as updates
import launcher
from package_pc_release import package_release
import publish_pc_update as publisher


def fixture_package(directory, build=1, commit=None):
    directory = Path(directory)
    app = directory / "main"
    (app / "_internal").mkdir(parents=True)
    (app / "main.exe").write_bytes(b"test executable")
    (app / "_internal" / "ffmpeg.exe").write_bytes(b"test ffmpeg")
    stub = directory / "launcher.exe"
    stub.write_bytes(b"test launcher")
    output = directory / "output"
    raw = package_release(app, stub, output, commit or f"{build:040x}", build)
    return output, raw


def custom_archive(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)


@contextlib.contextmanager
def local_server(files):
    counts = {}
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            counts[self.path] = counts.get(self.path, 0) + 1
            if self.path not in files:
                self.send_error(404)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(files[self.path])

        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", counts
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.output, self.raw = fixture_package(self.directory / "fixture")
        self.manifest = updates.validate_manifest(self.raw)
        self.root = self.directory / "client"
        self.root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_manifest_rejects_external_package_and_wrong_protocol(self):
        for changes in ({"package": "https://evil.invalid/app.zip"}, {"package": "/pc-updates/../secret"}, {"launcher_protocol": 2}, {"build": True}, {"size": 0}, {"commit": "short"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                updates.validate_manifest({**self.raw, **changes})

    def test_bootstrap_and_server_metadata_are_same_installation(self):
        self.assertNotIn("installer_sha256", self.manifest)
        updates.stage_archive(self.root, self.output / "auditflow-pc.zip", self.raw)
        updates.stage_archive(self.root, self.output / "auditflow-pc.zip", self.manifest)
        self.assertTrue(updates.is_installed(self.root, self.raw))

    def test_staging_does_not_change_active_version_or_user_data(self):
        updates.atomic_json(self.root / "active.json", {"old": True})
        user_file = self.directory / "Documents" / "evidencia-pendiente.mp4"
        user_file.parent.mkdir()
        user_file.write_bytes(b"pending video")
        updates.stage_archive(self.root, self.output / "auditflow-pc.zip", self.manifest)
        self.assertEqual(updates.read_json(self.root / "active.json"), {"old": True})
        self.assertEqual(user_file.read_bytes(), b"pending video")
        self.assertEqual(updates.read_json(self.root / "pending.json"), self.manifest)

    def test_incomplete_download_never_stages(self):
        package = self.output / "auditflow-pc.zip"
        package.write_bytes(package.read_bytes()[:-10])
        with self.assertRaises(ValueError):
            updates.stage_archive(self.root, package, self.manifest)
        self.assertFalse((self.root / "pending.json").exists())
        self.assertFalse((self.root / "versions").exists())

    def test_archive_rejects_zip_slip_windows_ads_and_case_collisions(self):
        variants = [
            [("main/../../escape.txt", b"x")],
            [("main/a.txt:evil", b"x")],
            [("main/CON.txt", b"x")],
            [("main/a.txt ", b"x")],
            [("main/A.txt", b"x"), ("main/a.txt", b"x")],
            [("main\\escape.txt", b"x")],
            [("other/file.txt", b"x")],
        ]
        for index, entries in enumerate(variants):
            with self.subTest(entries=entries):
                archive = self.directory / f"bad-{index}.zip"
                custom_archive(archive, entries)
                with self.assertRaises(ValueError):
                    updates.safe_extract(archive, self.directory / f"extract-{index}")
        self.assertFalse((self.directory / "escape.txt").exists())

    def test_archive_rejects_symlink_and_expansion_limit(self):
        archive = self.directory / "symlink.zip"
        link = zipfile.ZipInfo("main/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr(link, "../../outside")
        with self.assertRaises(ValueError):
            updates.safe_extract(archive, self.directory / "extract")
        with patch.object(updates, "MAX_EXPANDED_SIZE", 2), self.assertRaises(ValueError):
            updates.safe_extract(self.output / "auditflow-pc.zip", self.directory / "large")

    def test_archive_requires_ffmpeg_and_matching_inner_version(self):
        package = self.output / "auditflow-pc.zip"
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr("main/unexpected.txt", b"x")
        bad = {**self.manifest, "sha256": updates.package_hash(package), "size": package.stat().st_size, "build": 2}
        bad["package"] = f"/pc-updates/packages/{bad['sha256']}.zip"
        with self.assertRaisesRegex(ValueError, "interna"):
            updates.stage_archive(self.root, package, bad)

    def test_download_only_once_then_reuses_pending(self):
        files = {"/pc-updates/manifest.json": json.dumps(self.raw).encode(), self.manifest["package"]: (self.output / "auditflow-pc.zip").read_bytes()}
        with local_server(files) as (base, counts):
            self.assertEqual(updates.check_and_stage(self.root, base, {"build": 0}), self.manifest)
            self.assertEqual(updates.check_and_stage(self.root, base, {"build": 0}), self.manifest)
            self.assertEqual(counts[self.manifest["package"]], 1)
            self.assertEqual(counts["/pc-updates/manifest.json"], 2)

    def test_offline_and_downgrade_do_not_change_state(self):
        updates.atomic_json(self.root / "active.json", self.manifest)
        with local_server({}) as (base, counts), self.assertRaises(urllib.error.HTTPError):
            updates.check_and_stage(self.root, base, self.manifest)
        files = {"/pc-updates/manifest.json": json.dumps(self.raw).encode()}
        with local_server(files) as (base, counts):
            self.assertIsNone(updates.check_and_stage(self.root, base, {"build": 2}))
            self.assertNotIn(self.manifest["package"], counts)
        self.assertEqual(updates.read_json(self.root / "active.json"), self.manifest)

    def test_corrupt_http_package_preserves_active(self):
        updates.atomic_json(self.root / "active.json", {"build": 0})
        files = {"/pc-updates/manifest.json": json.dumps(self.raw).encode(), self.manifest["package"]: b"corrupt"}
        with local_server(files) as (base, counts), self.assertRaises(ValueError):
            updates.check_and_stage(self.root, base, {"build": 0})
        self.assertEqual(updates.read_json(self.root / "active.json"), {"build": 0})
        self.assertFalse((self.root / "pending.json").exists())
        self.assertFalse(list(self.root.glob("download-*")))

    def test_cross_server_redirect_rejected(self):
        with self.assertRaises(ValueError):
            updates.SameOriginRedirect().redirect_request(urllib.request.Request("http://127.0.0.1/app"), None, 302, "Found", {}, "http://evil.invalid/app")

    def test_lock_released_on_failure(self):
        with self.assertRaisesRegex(RuntimeError, "test"):
            with updates.update_lock(self.root):
                raise RuntimeError("test")
        with updates.update_lock(self.root):
            pass
        self.assertEqual((self.root / "update.lock").stat().st_size, 1)

    def test_activate_bootstrap_offline_then_pending_and_rollback(self):
        distribution = self.directory / "distribution"
        distribution.mkdir()
        shutil.copyfile(self.output / "auditflow-pc.zip", distribution / "bootstrap.zip")
        updates.atomic_json(distribution / "bootstrap.json", self.raw)
        first, old = launcher.select_version(self.root, distribution)
        self.assertEqual(first, self.manifest)
        self.assertIsNone(old)
        output2, raw2 = fixture_package(self.directory / "second", build=2)
        updates.stage_archive(self.root, output2 / "auditflow-pc.zip", raw2)
        second, old = launcher.select_version(self.root, distribution)
        self.assertEqual(second["build"], 2)
        self.assertEqual(old, first)
        launcher.restore_previous(self.root, second, old)
        self.assertEqual(updates.read_json(self.root / "active.json"), first)
        self.assertEqual(updates.read_json(self.root / "rejected.json")["sha256"], second["sha256"])
        self.assertTrue(updates.is_installed(self.root, second))

    def test_rejected_bootstrap_not_retried_every_launch(self):
        updates.stage_archive(self.root, self.output / "auditflow-pc.zip", self.raw)
        first, _ = launcher.select_version(self.root, self.directory)
        output2, raw2 = fixture_package(self.directory / "second", build=2)
        distribution = self.directory / "distribution"
        distribution.mkdir()
        shutil.copyfile(output2 / "auditflow-pc.zip", distribution / "bootstrap.zip")
        updates.atomic_json(distribution / "bootstrap.json", raw2)
        updates.atomic_json(self.root / "rejected.json", {"sha256": raw2["sha256"]})
        selected, old = launcher.select_version(self.root, distribution)
        self.assertEqual(selected, first)
        self.assertIsNone(old)

    def test_fallback_survives_restart_between_activation_and_ui(self):
        updates.stage_archive(self.root, self.output / "auditflow-pc.zip", self.raw)
        first, _ = launcher.select_version(self.root, self.directory)
        launcher.confirm_version(self.root, first)
        output2, raw2 = fixture_package(self.directory / "second", build=2)
        updates.stage_archive(self.root, output2 / "auditflow-pc.zip", raw2)
        second, old = launcher.select_version(self.root, self.directory)
        after_restart, fallback = launcher.select_version(self.root, self.directory)
        self.assertEqual(after_restart, second)
        self.assertEqual(fallback, first)
        launcher.confirm_version(self.root, second)
        self.assertIsNone(launcher.select_version(self.root, self.directory)[1])


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output, self.raw = fixture_package(self.root / "fixture", build=2)
        self.revision = self.raw["commit"]
        self.private, self.public = self.root / "private", self.root / "public"
        self.private.mkdir()
        self.config = {"repository": "owner/repo"}
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(publisher, "ROOT", self.root))
        self.stack.enter_context(patch.object(publisher, "PRIVATE", self.private))
        self.stack.enter_context(patch.object(publisher, "PUBLIC", self.public))
        self.stack.enter_context(patch.object(publisher, "request_matches", return_value=True))
        self.stack.enter_context(patch.object(publisher.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)))
        self.stack.enter_context(patch.object(publisher, "github_release", return_value={}))
        self.stack.enter_context(patch.object(publisher, "download_asset", side_effect=lambda release, name, dest, config, max_bytes: shutil.copyfile(self.output / name, dest)))
        self.stack.enter_context(patch.object(publisher, "deployment_ready", return_value=False))

    def tearDown(self):
        self.stack.close()
        self.temporary.cleanup()

    def test_publish_after_backend_confirmed(self):
        with patch.object(publisher, "deploy_backend") as backend:
            self.assertTrue(publisher.publish_once(self.config, self.revision))
        backend.assert_called_once()
        manifest = updates.read_json(self.public / "manifest.json")
        self.assertEqual(manifest["commit"], self.revision)
        self.assertTrue((self.public / "packages" / (manifest["sha256"] + ".zip")).is_file())
        self.assertTrue((self.public / "installers" / (self.raw["installer_sha256"] + ".zip")).is_file())

    def test_failed_backend_leaves_previous_manifest(self):
        previous = {"build": 1, "commit": "1" * 40}
        updates.atomic_json(self.public / "manifest.json", previous)
        with patch.object(publisher, "deploy_backend", side_effect=RuntimeError("backend failed")), self.assertRaises(RuntimeError):
            publisher.publish_once(self.config, self.revision)
        self.assertEqual(updates.read_json(self.public / "manifest.json"), previous)
        self.assertFalse((self.public / "packages").exists())

    def test_corrupt_artifact_never_deploys(self):
        (self.output / "auditflow-pc.zip").write_bytes(b"corrupt")
        with patch.object(publisher, "deploy_backend") as backend, self.assertRaises(ValueError):
            publisher.publish_once(self.config, self.revision)
        backend.assert_not_called()
        self.assertFalse((self.public / "manifest.json").exists())

    def test_commit_mismatch_never_deploys(self):
        with patch.object(publisher, "deploy_backend") as backend, self.assertRaisesRegex(ValueError, "commit"):
            publisher.publish_once(self.config, "3" * 40)
        backend.assert_not_called()

    def test_new_pull_during_download_does_not_publish_old_commit(self):
        with patch.object(publisher, "request_matches", side_effect=[True, False]), patch.object(publisher, "deploy_backend") as backend:
            self.assertFalse(publisher.publish_once(self.config, self.revision))
        backend.assert_not_called()
        self.assertFalse((self.public / "manifest.json").exists())

    def test_api_unavailable_keeps_old_manifest(self):
        updates.atomic_json(self.public / "manifest.json", {"build": 1})
        with patch.object(publisher, "github_release", side_effect=urllib.error.HTTPError("https://api.github.com", 404, "Not found", {}, None)), self.assertRaises(urllib.error.HTTPError):
            publisher.publish_once(self.config, self.revision)
        self.assertEqual(updates.read_json(self.public / "manifest.json"), {"build": 1})

    def test_backend_uses_commit_snapshot_and_preserves_existing_dependencies(self):
        calls = []
        def run(arguments, **kwargs):
            if "archive" in arguments:
                archive = Path(arguments[arguments.index("-o") + 1])
                with zipfile.ZipFile(archive, "w") as handle:
                    handle.writestr("backend/Dockerfile", "FROM node:20-alpine")
                    handle.writestr("docker-compose.yml", "services: {}")
            else:
                calls.append((arguments, kwargs))
            return types.SimpleNamespace(returncode=0)
        snapshot = self.root / "isolated-snapshot"
        with patch.object(publisher.subprocess, "run", side_effect=run), patch.object(publisher, "deployment_ready", return_value=True):
            publisher.deploy_backend(self.config, self.revision, snapshot)
        command, kwargs = calls[0]
        self.assertIn("--no-deps", command)
        self.assertEqual(command[-1], "backend")
        self.assertEqual(kwargs["env"]["AUDITFLOW_DEPLOY_COMMIT"], self.revision)
        override = updates.read_json(snapshot / "override.json")
        self.assertEqual(override["services"]["backend"]["build"]["context"], str(snapshot / "backend"))


if __name__ == "__main__":
    unittest.main()

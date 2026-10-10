"""Regresiones de despliegue: Docker/GitHub/systemctl simulados, sin producción."""
import copy
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "pc-app"), str(REPO / "deploy")]
import install_pc_updates as installer
import publish_pc_update as publisher
from core.pc_updates import read_json, atomic_json


class SystemdTests(unittest.TestCase):
    def test_raw_directory_and_quoted_arguments_use_distinct_parsers(self):
        root = '/home/auditor/Audit Flow %h $HOME "uno" \\dos'
        service = installer.render_units(root, '/usr/bin/python3')[installer.SERVICE_NAME]
        self.assertIn('WorkingDirectory=' + root.replace('%', '%%') + '\n', service)
        self.assertIn('ExecStart=:"/usr/bin/python3"', service)
        self.assertIn('$HOME', service)
        self.assertIn('\\"uno\\"', service)
        self.assertIn('\\\\dos', service)
        self.assertNotIn('WorkingDirectory="', service)

    def test_cannot_inject_unit_directives_or_relative_directory(self):
        for root in ('relative', '/repo\nExecStart=/evil', '/repo\x00', '/repo ', '/repo\\'):
            with self.subTest(root=root), self.assertRaises(ValueError):
                installer.render_units(root, '/usr/bin/python3')

    def test_reinstallation_is_identical_and_validated_before_reload(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(installer.Path, 'home', return_value=Path(temporary)), patch.object(installer, 'ROOT', PurePosixPath('/home/monitores/servidor/auditflow')), patch.object(installer.sys, 'executable', '/usr/bin/python3'), patch('shutil.which', return_value='/usr/bin/tool'), patch.object(installer.subprocess, 'run') as run:
            installer.install_timer()
            unit = Path(temporary) / '.config/systemd/user' / installer.SERVICE_NAME
            first = unit.read_text()
            installer.install_timer()
            self.assertEqual(unit.read_text(), first)
            self.assertEqual(run.call_args_list[0].args[0][:3], ['systemd-analyze', '--user', 'verify'])
            self.assertNotIn('start', [arg for call in run.call_args_list for arg in call.args[0]])

    def test_invalid_units_do_not_overwrite_installed_files(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(installer.Path, 'home', return_value=Path(temporary)), patch.object(installer, 'ROOT', PurePosixPath('/home/repo')), patch.object(installer.sys, 'executable', '/usr/bin/python3'), patch('shutil.which', return_value='/usr/bin/tool'), patch.object(installer.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['verify'])):
            directory = Path(temporary) / '.config/systemd/user'
            directory.mkdir(parents=True)
            unit = directory / installer.SERVICE_NAME
            unit.write_text('AuditFlow anterior')
            with self.assertRaises(subprocess.CalledProcessError):
                installer.install_timer()
            self.assertEqual(unit.read_text(), 'AuditFlow anterior')

    @unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('systemd-analyze'), 'Requiere systemd-analyze en Linux; no instala ni inicia servicios')
    def test_real_systemd_verify_without_starting_units(self):
        with tempfile.TemporaryDirectory(prefix='audit flow-%-$-"-') as temporary:
            units = installer.render_units(temporary, sys.executable)
            paths = []
            for name, text in units.items():
                path = Path(temporary) / name
                path.write_text(text, encoding='utf-8')
                paths.append(str(path))
            result = subprocess.run(['systemd-analyze', '--user', 'verify', *paths], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


def runtime_fixture():
    model = {'name': 'auditflow', 'services': {'backend': {
        'container_name': 'auditflow-api', 'build': {'context': '/repo/backend'},
        'environment': {'AUDITFLOW_DEPLOY_COMMIT': 'new'}, 'restart': 'always',
        'ports': [{'target': 3000, 'published': '3000', 'protocol': 'tcp'}],
        'volumes': [{'type': 'bind', 'source': '/repo/storage_data', 'target': '/usr/src/app/storage'},
                    {'type': 'bind', 'source': '/repo/pc_updates', 'target': '/usr/src/app/pc_updates', 'read_only': True}],
        'networks': {'default': None}, 'depends_on': {'db': {}},
    }}, 'networks': {'default': {'name': 'auditflow_default'}}, 'volumes': {'mysql_data': {'name': 'auditflow_mysql_data'}}}
    container = {'Id': 'old-container', 'Image': 'sha256:old', 'State': {'Running': True},
                 'Config': {'Env': ['AUDITFLOW_DEPLOY_COMMIT=development', 'PASSWORD=local$value'],
                            'Cmd': ['npm', 'run', 'start:prod'], 'Entrypoint': ['docker-entrypoint.sh'],
                            'WorkingDir': '/usr/src/app', 'User': '',
                            'Labels': {'com.docker.compose.project': 'auditflow', 'com.docker.compose.service': 'backend'}},
                 'HostConfig': {'PortBindings': {'3000/tcp': [{'HostIp': '', 'HostPort': '3000'}]}, 'RestartPolicy': {'Name': 'always'}},
                 'Mounts': [{'Type': 'bind', 'Source': '/repo/storage_data', 'Destination': '/usr/src/app/storage', 'RW': True},
                            {'Type': 'bind', 'Source': '/repo/pc_updates', 'Destination': '/usr/src/app/pc_updates', 'RW': False}],
                 'NetworkSettings': {'Networks': {'auditflow_default': {}}}}
    return model, container


class RecoveryTests(unittest.TestCase):
    def test_capture_previous_image_environment_and_storage_without_credentials_in_logs(self):
        model, container = runtime_fixture()
        previous = publisher.recovery_model(model, container)
        backend = previous['services']['backend']
        self.assertEqual(backend['image'], 'sha256:old')
        self.assertEqual(backend['environment']['PASSWORD'], 'local$value')
        self.assertEqual(backend['volumes'], model['services']['backend']['volumes'])
        self.assertNotIn('build', backend)
        self.assertNotIn('depends_on', backend)
        self.assertTrue(previous['networks']['default']['external'])
        self.assertTrue(previous['volumes']['mysql_data']['external'])
        self.assertEqual(publisher.compose_literals(previous)['services']['backend']['environment']['PASSWORD'], 'local$$value')

    def test_changed_storage_ports_network_or_custom_options_abort(self):
        model, container = runtime_fixture()
        for field in ('storage', 'port', 'network', 'custom', 'stopped'):
            changed = copy.deepcopy(model)
            old = copy.deepcopy(container)
            if field == 'storage': changed['services']['backend']['volumes'][0]['source'] = '/different'
            if field == 'port': changed['services']['backend']['ports'][0]['published'] = '4000'
            if field == 'network': changed['networks']['default']['name'] = 'other'
            if field == 'custom': changed['services']['backend']['privileged'] = True
            if field == 'stopped': old['State']['Running'] = False
            with self.subTest(field=field), self.assertRaises(ValueError):
                publisher.recovery_model(changed, old)


class BackendDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.private = self.root / 'private'
        self.private.mkdir()
        self.snapshot = self.root / 'snapshot'
        self.revision = 'a' * 40
        self.model, self.old = runtime_fixture()
        self.commands = []
        self.fail_preflight = False
        self.stack = __import__('contextlib').ExitStack()
        for name, value in [('ROOT', self.root), ('PRIVATE', self.private)]:
            self.stack.enter_context(patch.object(publisher, name, value))
        self.stack.enter_context(patch.object(publisher, 'request_matches', return_value=True))
        self.stack.enter_context(patch.object(publisher, 'inspect_container', return_value=self.old))
        self.stack.enter_context(patch.object(publisher, 'deployment_commit', return_value='development'))
        self.stack.enter_context(patch.object(publisher.subprocess, 'run', side_effect=self.run_command))

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    def run_command(self, args, **kwargs):
        self.commands.append(args)
        if 'archive' in args:
            archive = Path(args[args.index('-o') + 1])
            with zipfile.ZipFile(archive, 'w') as target:
                target.writestr('backend/Dockerfile', 'FROM node:20-alpine')
                target.writestr('docker-compose.yml', 'services: {}')
        if 'config' in args:
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(self.model))
        if 'image' in args:
            return types.SimpleNamespace(returncode=0, stdout=json.dumps([{'Id': 'sha256:new', 'Config': {'Labels': {'org.opencontainers.image.revision': self.revision}}}]))
        if 'run' in args and self.fail_preflight:
            raise subprocess.CalledProcessError(1, args)
        return types.SimpleNamespace(returncode=0)

    def test_success_builds_and_probes_before_backend_replacement(self):
        with patch.object(publisher, 'wait_backend', return_value=True):
            self.assertTrue(publisher.deploy_backend({}, self.revision, self.snapshot))
        build = next(i for i, c in enumerate(self.commands) if 'build' in c)
        probe = next(i for i, c in enumerate(self.commands) if 'run' in c)
        up = next(i for i, c in enumerate(self.commands) if 'up' in c)
        self.assertLess(build, probe)
        self.assertLess(probe, up)
        self.assertIn('none', self.commands[probe])
        self.assertNotIn('-v', self.commands[probe])
        self.assertEqual(publisher.deployment_state()['state'], 'deployed')
        self.assertEqual(read_json(self.snapshot / 'override.json')['services']['backend']['image'], 'sha256:new')

    def test_failed_probe_never_replaces_backend_or_retries_by_timer(self):
        self.fail_preflight = True
        with self.assertRaisesRegex(publisher.DeploymentError, 'no reemplazado'):
            publisher.deploy_backend({}, self.revision, self.snapshot)
        self.assertFalse(any('up' in c for c in self.commands))
        with self.assertRaises(publisher.DeploymentError):
            publisher.ensure_deployment_allowed(self.revision)

    def test_failed_candidate_restores_previous_image_not_db_or_volumes(self):
        with patch.object(publisher, 'wait_backend', side_effect=[False, True]), self.assertRaisesRegex(publisher.DeploymentError, 'anterior recuperada'):
            publisher.deploy_backend({}, self.revision, self.snapshot)
        ups = [c for c in self.commands if 'up' in c]
        self.assertEqual(len(ups), 2)
        for command in ups:
            self.assertIn('--no-deps', command)
            self.assertIn('--no-build', command)
            self.assertNotIn('down', command)
            self.assertNotIn('-v', command)
        backup = self.private / 'recovery' / self.revision / 'compose.json'
        self.assertEqual(read_json(backup)['services']['backend']['image'], 'sha256:old')
        self.assertEqual(publisher.deployment_state()['state'], 'recovered')

    def test_recovery_failure_blocks_even_new_commit(self):
        with patch.object(publisher, 'wait_backend', return_value=False), self.assertRaisesRegex(publisher.DeploymentError, 'intervención'):
            publisher.deploy_backend({}, self.revision, self.snapshot)
        with self.assertRaises(publisher.DeploymentError):
            publisher.ensure_deployment_allowed('b' * 40)

    def test_corrupt_recovery_journal_is_not_ignored(self):
        (self.private / 'deployment-state.json').write_text('invalid json')
        with self.assertRaisesRegex(publisher.DeploymentError, 'Journal'):
            publisher.ensure_deployment_allowed(self.revision)
        self.assertFalse(self.commands)

    def test_same_failed_revision_requires_explicit_request(self):
        publisher.record_deployment(self.revision, 'recovered')
        atomic_json(self.private / 'config.json', {'enabled': True})
        with patch.object(publisher, 'head', return_value=self.revision), patch.object(publisher, 'git', return_value=self.revision), patch.object(publisher.subprocess, 'Popen'):
            publisher.request_publication()
        self.assertEqual(publisher.deployment_state()['state'], 'retry_requested')
        publisher.ensure_deployment_allowed(self.revision)

    def test_request_does_not_reset_failed_recovery(self):
        publisher.record_deployment(self.revision, 'recovery_failed')
        atomic_json(self.private / 'config.json', {'enabled': True})
        with patch.object(publisher, 'head', return_value=self.revision), patch.object(publisher, 'git', return_value=self.revision), patch.object(publisher.subprocess, 'Popen'):
            publisher.request_publication()
        self.assertEqual(publisher.deployment_state()['state'], 'recovery_failed')
        with self.assertRaises(publisher.DeploymentError):
            publisher.ensure_deployment_allowed(self.revision)

    def test_new_request_during_build_never_replaces_backend(self):
        with patch.object(publisher, 'request_matches', return_value=False):
            self.assertFalse(publisher.deploy_backend({}, self.revision, self.snapshot))
        self.assertFalse(any('up' in c for c in self.commands))

    def test_second_pull_is_queued_without_erasing_active_recovery_journal(self):
        publisher.record_deployment(self.revision, 'replacing')
        atomic_json(self.private / 'config.json', {'enabled': True})
        new = 'b' * 40
        with patch.object(publisher, 'head', return_value=new), patch.object(publisher, 'git', return_value=new), patch.object(publisher.subprocess, 'Popen'):
            publisher.request_publication()
        self.assertEqual(read_json(self.private / 'requested.json')['commit'], new)
        self.assertEqual(publisher.deployment_state()['state'], 'replacing')


if __name__ == '__main__':
    unittest.main()

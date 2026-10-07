import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def bootstrap():
    spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).resolve().parents[2] / 'start_windows.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_newer_python_uses_312_and_preserves_old_environment(tmp_path, bootstrap):
    old = tmp_path / '.venv-windows' / 'Scripts' / 'python.exe'
    old.parent.mkdir(parents=True); old.write_bytes(b'old interpreter')
    data = tmp_path / 'data' / 'catalog.db'
    data.parent.mkdir(); data.write_bytes(b'user records')
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if '-c' in command:
            return SimpleNamespace(returncode=0 if command[:2] == ['py', '-3.12'] else 1)
        return SimpleNamespace(returncode=0)

    assert bootstrap.start(tmp_path, runner, lambda url: pytest.fail('Compatible Python exists')) == 0
    created = tmp_path / '.venv-windows-312'
    assert ['py', '-3.12', '-m', 'venv', str(created)] in calls
    assert calls[-2] == [str(created / 'Scripts' / 'python.exe'), str(tmp_path / 'install_dependencies.py')]
    assert calls[-1] == [str(created / 'Scripts' / 'python.exe'), str(tmp_path / 'launch_windows.py')]
    assert old.read_bytes() == b'old interpreter' and data.read_bytes() == b'user records'


def test_compatible_existing_environment_is_reused(tmp_path, bootstrap):
    executable = tmp_path / '.venv-windows' / 'Scripts' / 'python.exe'
    executable.parent.mkdir(parents=True); executable.touch()
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    assert bootstrap.start(tmp_path, runner) == 0
    assert not any('venv' in command for command in calls)
    assert all(command[0] == str(executable) for command in calls)


def test_missing_python_explains_install_before_pip(tmp_path, bootstrap, capsys):
    calls, opened = [], []

    def runner(command, **kwargs):
        calls.append(command)
        raise FileNotFoundError()

    assert bootstrap.start(tmp_path, runner, opened.append) == 1
    assert opened == [bootstrap.PYTHON_DOWNLOAD]
    assert 'Python 3.12 (64-bit)' in capsys.readouterr().out
    assert all('-c' in command for command in calls)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('failure', ['venv', 'install_dependencies.py'])
def test_failed_setup_never_launches_server(tmp_path, bootstrap, failure):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if '-c' in command:
            return SimpleNamespace(returncode=0)
        failed = 'venv' in command if failure == 'venv' else command[-1].endswith(failure)
        return SimpleNamespace(returncode=2 if failed else 0)

    assert bootstrap.start(tmp_path, runner) == 2
    assert not any(command[-1].endswith('launch_windows.py') for command in calls)


def test_installer_rejects_unsupported_python_before_pip(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location('installer', Path(__file__).resolve().parents[2] / 'install_dependencies.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, 'version_info', (3, 14, 0))
    assert module.install(tmp_path, lambda command: pytest.fail('Do not attempt pip under Python 3.14')) == 1
    assert 'Python 3.12' in capsys.readouterr().out

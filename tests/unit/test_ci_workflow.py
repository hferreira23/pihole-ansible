"""Guard latest-only CI, conservative change detection, and required statuses."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

from packaging.requirements import Requirement
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / '.github/scripts/ci_test_changes.py'
spec = importlib.util.spec_from_file_location('ci_test_changes', SCRIPT)
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)


@pytest.fixture
def workflow():
    # BaseLoader keeps the GitHub Actions key "on" from becoming YAML 1.1 True.
    return yaml.load((ROOT / '.github/workflows/tests.yml').read_text(), Loader=yaml.BaseLoader)


def test_single_test_job_tracks_latest_stable_ansible(workflow):
    assert set(workflow['jobs']) == {'changes', 'unit'}
    job = workflow['jobs']['unit']
    assert job['name'] == 'unit (ansible-core)'
    assert 'strategy' not in job
    install = next(step['run'] for step in job['steps'] if step['name'] == 'Install test dependencies')
    assert 'pip install --upgrade -r tests/requirements.txt ansible-core' in install
    assert '--pre' not in install


def test_test_requirements_do_not_cap_ansible_core():
    requirements = [Requirement(line) for line in (ROOT / 'tests/requirements.txt').read_text().splitlines()
                    if line.strip() and not line.startswith('#')]
    requirement, = [item for item in requirements if item.name == 'ansible-core']
    assert all(item.operator in ('>', '>=') for item in requirement.specifier)


def test_triggers_skip_feature_pushes_and_pr_metadata_edits(workflow):
    events = workflow['on']
    assert events['push']['branches'] == ['main']
    assert 'workflow_dispatch' in events
    assert set(events['pull_request']['types']) == {
        'opened', 'synchronize', 'reopened', 'ready_for_review', 'converted_to_draft'}
    assert workflow['permissions'] == {'contents': 'read'}
    assert workflow['concurrency']['cancel-in-progress'] == 'true'


def test_change_gate_keeps_required_status_and_fails_open(workflow):
    assert 'paths' not in workflow['on']['push']
    assert 'paths' not in workflow['on']['pull_request']
    job = workflow['jobs']['changes']
    assert '!github.event.pull_request.draft' in job['if']
    checkout = job['steps'][0]
    assert checkout['with']['fetch-depth'] == '0'
    assert job['outputs']['required'] == '${{ steps.changes.outputs.required }}'
    unit = workflow['jobs']['unit']
    assert unit['needs'] == 'changes'
    assert "needs.changes.result == 'failure'" in unit['if']
    assert "needs.changes.outputs.required == 'true'" in unit['if']
    assert '!cancelled()' in unit['if']


def test_cache_does_not_freeze_python_or_ansible(workflow):
    steps = workflow['jobs']['unit']['steps']
    setup = next(step for step in steps if step.get('uses', '').startswith('actions/setup-python@'))
    assert setup['with']['cache'] == 'pip'
    assert setup['with']['python-version'] == '3.x'
    assert setup['with']['check-latest'] == 'true'
    assert setup['with']['cache-dependency-path'] == 'tests/requirements.txt'
    install = next(step for step in steps if step['name'] == 'Install test dependencies')
    assert 'if' not in install
    assert 'python -m pip check' in install['run']


def test_failure_report_is_outside_collection_and_retained_on_reruns(workflow):
    job = workflow['jobs']['unit']
    assert int(job['timeout-minutes']) > 0
    steps = job['steps']
    test = next(step for step in steps if step['name'] == 'Run regression tests')
    assert '--junitxml="$RUNNER_TEMP/pytest.xml"' in test['run']
    upload = next(step for step in steps if step['name'] == 'Upload test report')
    assert upload['if'] == '${{ always() }}'
    assert upload['with']['name'] == 'pytest-latest-${{ github.run_attempt }}'
    assert upload['with']['path'] == '${{ runner.temp }}/pytest.xml'


@pytest.mark.parametrize('paths', [
    [], ['README.md'], ['examples/README.md', 'CONTRIBUTING.md'],
    ['AGENTS.md', 'CHANGELOG.md'], ['roles/manage_lists/tasks/main.yml'],
    ['.github/workflows/commit-lint.yml', '.github/release-please-manifest.json'],
    ['LICENSE', '.gitignore', '.ansible-lint', '.yamllint'],
])
def test_irrelevant_changes_skip_tests(paths):
    assert not changes.tests_required(paths)


@pytest.mark.parametrize('path', [
    'plugins/modules/groups.py', 'plugins/doc_fragments/list_management.py',
    'tests/fixtures/example.md', 'tests/requirements.txt', 'meta/runtime.yml',
    'examples/manage-block-lists.yml', 'galaxy.yml', '.github/workflows/tests.yml',
    '.github/scripts/ci_test_changes.py', 'new-source/main.py',
])
def test_relevant_unknown_and_mixed_changes_run_tests(path):
    assert changes.tests_required(['README.md', path])


def test_nul_separated_paths_and_renames_are_not_hidden(monkeypatch):
    calls = []

    def git(args, **kwargs):
        calls.append(args)
        if args[1] == 'merge-base':
            return 'common-base\n'
        return b'plugins/old.py\0README.md\0filename\nwith-newline.py\0'

    monkeypatch.setattr(changes.subprocess, 'check_output', git)
    paths = changes.changed_paths('base', 'head', pull_request=True)
    assert paths == ['plugins/old.py', 'README.md', 'filename\nwith-newline.py']
    assert '--no-renames' in calls[-1]
    assert calls[-1][-3:] == ['common-base', 'head', '--']
    assert changes.tests_required(paths)


@pytest.mark.parametrize('event', ['push', 'pull_request', 'workflow_dispatch', 'unknown'])
def test_cli_runs_on_manual_events_and_missing_comparison(tmp_path, event):
    output = tmp_path / 'output'
    env = dict(os.environ, EVENT_NAME=event, BASE_SHA='', HEAD_SHA='', GITHUB_OUTPUT=str(output))
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == 'required=true\n'


@pytest.mark.parametrize('paths,expected', [(['README.md'], 'false'), (['tests/test_new.py'], 'true')])
def test_selector_writes_job_output(monkeypatch, tmp_path, paths, expected):
    output = tmp_path / 'output'
    monkeypatch.setenv('EVENT_NAME', 'push')
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    monkeypatch.setattr(changes, 'changed_paths', lambda *args: paths)
    changes.main()
    assert output.read_text() == 'required={0}\n'.format(expected)


def test_git_failure_runs_tests_instead_of_hiding_changes(monkeypatch, tmp_path):
    output = tmp_path / 'output'
    monkeypatch.setenv('EVENT_NAME', 'push')
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))

    def fail(*args):
        raise subprocess.CalledProcessError(128, ['git', 'diff'])

    monkeypatch.setattr(changes, 'changed_paths', fail)
    changes.main()
    assert output.read_text() == 'required=true\n'

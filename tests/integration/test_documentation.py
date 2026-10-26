"""Validate the documentation and examples shipped in the built collection."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest
import yaml

from ansible_collections.hferreira23.pihole.plugins.module_utils.lists import list_argument_spec
from ansible_collections.hferreira23.pihole.plugins.module_utils.domains import domain_argument_spec


ROOT = Path(__file__).resolve().parents[2]
MODULES = ('allow_list', 'block_list', 'clients', 'groups', 'domains', 'dhcp_config',
           'dhcp_remove_lease', 'listening_mode', 'local_a_record', 'local_aaaa_record', 'local_cname')
LIST_MODULES = ('allow_list', 'block_list')


@pytest.fixture(scope='module')
def collection_docs(tmp_path_factory):
    directory = tmp_path_factory.mktemp('collection-docs')
    env = dict(os.environ, ANSIBLE_HOME=str(directory / 'ansible'),
               ANSIBLE_COLLECTIONS_PATH=str(directory / 'collections'), ANSIBLE_NOCOLOR='1')

    def run(tool, *args):
        command = [str(Path(sys.executable).with_name(tool)), *map(str, args)]
        result = subprocess.run(command, env=env, capture_output=True, text=True, cwd=ROOT)
        assert result.returncode == 0, result.stdout + result.stderr
        assert '[ERROR]' not in result.stderr, result.stderr
        return result.stdout

    run('ansible-galaxy', 'collection', 'build', ROOT, '--output-path', directory)
    archive, = directory.glob('*.tar.gz')
    assert 'pihole-creds' in yaml.safe_load((ROOT / 'galaxy.yml').read_text())['build_ignore']
    with tarfile.open(archive) as package:
        assert all(Path(member.name).name != 'pihole-creds' for member in package.getmembers())
    run('ansible-galaxy', 'collection', 'install', archive, '-p', directory / 'collections', '--offline', '--force')
    docs = json.loads(run('ansible-doc', '--json', *['hferreira23.pihole.' + name for name in MODULES]))
    return docs, run


@pytest.mark.parametrize('name', MODULES)
def test_packaged_ansible_doc_connection_options(collection_docs, name):
    docs, _ = collection_docs
    module = docs['hferreira23.pihole.' + name]
    assert 'error' not in module
    options = module['doc']['options']
    assert options['validate_certs']['type'] == 'bool'
    assert options['validate_certs']['default'] is True
    assert options['ca_path']['type'] == 'path'
    assert 'authentication' in ' '.join(options['validate_certs']['description'])
    assert 'executing the module' in ' '.join(options['ca_path']['description'])
    assert any('verification is enabled by default' in note for note in module['doc']['notes'])
    examples = yaml.safe_load(module['examples'])
    assert examples and any('hferreira23.pihole.' + name in task for task in examples)
    assert 'sbarbett.pihole.' not in module['examples']


def assert_options_match_spec(documented, actual):
    """Compare public docs with argument parsing, including nested entries."""
    assert set(documented) == set(actual)
    for option, spec in actual.items():
        assert documented[option]['type'] == spec['type']
        assert documented[option].get('default') == spec.get('default')
        assert documented[option].get('required', False) == spec.get('required', False)
        assert documented[option].get('choices') == spec.get('choices')
        assert documented[option].get('elements') == spec.get('elements')
        if 'options' in spec:
            assert_options_match_spec(documented[option]['suboptions'], spec['options'])


@pytest.mark.parametrize('name', LIST_MODULES)
def test_list_docs_match_runtime_contract(collection_docs, name):
    docs, _ = collection_docs
    module = docs['hferreira23.pihole.' + name]
    documented = module['doc']['options']
    assert_options_match_spec(documented, list_argument_spec())
    nested = documented['lists']['suboptions']
    assert documented['groups']['elements'] == nested['groups']['elements'] == 'raw'
    assert documented['gravity_timeout']['type'] == 'int'
    assert documented['gravity_timeout']['default'] == 60
    assert 'Positive request timeout' in ' '.join(documented['gravity_timeout']['description'])
    assert 'clears' in ' '.join(documented['groups']['description'])
    assert 'preserve' in ' '.join(nested['groups']['description'])
    assert module['doc']['attributes']['check_mode']['support'] == 'full'
    assert module['doc']['attributes']['diff_mode']['support'] == 'none'
    assert {'result', 'changed', 'response', 'status_code'} <= module['return'].keys()
    assert {'address', 'action', 'response', 'current'} == module['return']['result']['contains'].keys()


@pytest.mark.parametrize('name', ('allow_list', 'block_list', 'groups', 'clients', 'domains'))
def test_human_readable_help_renders_new_features(collection_docs, name):
    _, run = collection_docs
    output = run('ansible-doc', 'hferreira23.pihole.' + name)
    assert 'validate_certs' in output and 'ca_path' in output
    assert 'processed.errors' in output
    assert 'check_mode' in output
    assert 'RETURN VALUES' in output
    assert 'status_code' in output
    assert 'EXAMPLES' in output
    assert 'O(' not in output and 'RV(' not in output


@pytest.mark.parametrize('name', ('groups', 'clients'))
def test_packaged_comment_docs_explain_preserve_and_clear(collection_docs, name):
    docs, _ = collection_docs
    description = docs['hferreira23.pihole.' + name]['doc']['options'][name]['suboptions']['comment']['description']
    rendered = ' '.join(description)
    assert 'preserves' in rendered and "C('')" in rendered


@pytest.mark.parametrize('name', ('allow_list', 'block_list', 'groups', 'clients', 'domains'))
def test_task_snippet_includes_shared_tls_options(collection_docs, name):
    _, run = collection_docs
    output = run('ansible-doc', '--snippet', 'hferreira23.pihole.' + name)
    # ansible-doc emits short module names even when invoked with an FQCN.
    assert '\n  ' + name + ':' in output
    assert 'validate_certs:' in output and 'ca_path:' in output
    if name in LIST_MODULES:
        assert 'gravity_timeout:' in output


def test_domain_docs_match_runtime_contract(collection_docs):
    docs, _ = collection_docs
    module = docs['hferreira23.pihole.domains']
    documented = module['doc']['options']
    assert_options_match_spec(documented, domain_argument_spec())
    nested = documented['domains']['suboptions']
    assert nested['groups']['elements'] == 'raw'
    assert 'preserves' in ' '.join(nested['groups']['description'])
    assert 'preserves' in ' '.join(nested['enabled']['description'])
    assert module['doc']['attributes']['check_mode']['support'] == 'full'
    assert module['doc']['attributes']['diff_mode']['support'] == 'none'
    assert {'changed', 'domains', 'response', 'status_code'} == module['return'].keys()
    assert {'domain', 'type', 'kind', 'action', 'comment', 'groups', 'enabled', 'response'} == module['return']['domains']['contains'].keys()
    assert module['return']['domains']['contains']['comment']['type'] == 'raw'


@pytest.mark.parametrize('name', MODULES)
def test_module_authors_include_fork_maintainer(collection_docs, name):
    docs, _ = collection_docs
    assert 'Hugo Ferreira (@hferreira23)' in docs['hferreira23.pihole.' + name]['doc']['author']


def validate_inputs(inputs, options):
    assert set(inputs) <= options.keys(), 'Unknown module options: {0}'.format(set(inputs) - options.keys())
    for key, value in inputs.items():
        if isinstance(value, list) and options[key].get('elements') == 'dict':
            suboptions = options[key]['suboptions']
            for entry in value:
                assert set(entry) <= suboptions.keys()
                assert all(field in entry for field, spec in suboptions.items() if spec.get('required'))


@pytest.mark.parametrize('name', MODULES)
def test_embedded_examples_are_valid_module_inputs(collection_docs, name):
    docs, _ = collection_docs
    module = docs['hferreira23.pihole.' + name]
    options = module['doc']['options']
    tasks = yaml.safe_load(module['examples'])
    for task in tasks:
        if 'hferreira23.pihole.' + name not in task:
            continue
        inputs = task['hferreira23.pihole.' + name]
        validate_inputs(inputs, options)


@pytest.mark.parametrize('path', sorted((ROOT / 'examples').glob('*.yml')), ids=lambda path: path.name)
def test_example_playbook_syntax(collection_docs, path):
    _, run = collection_docs
    run('ansible-playbook', '--syntax-check', '-i', 'localhost,', path)


@pytest.mark.parametrize('path', sorted((ROOT / 'examples').glob('*.yml')), ids=lambda path: path.name)
def test_example_playbook_module_inputs(collection_docs, path):
    docs, _ = collection_docs

    def validate_tasks(tasks):
        for task in tasks:
            for key in ('block', 'rescue', 'always'):
                validate_tasks(task.get(key, []))
            for key, inputs in task.items():
                if key.startswith('hferreira23.pihole.'):
                    validate_inputs(inputs, docs[key]['doc']['options'])

    for play in yaml.safe_load(path.read_text()):
        for name, inputs in play.get('module_defaults', {}).items():
            if name.startswith('hferreira23.pihole.'):
                validate_inputs(inputs, docs[name]['doc']['options'])
        for key in ('pre_tasks', 'tasks', 'post_tasks', 'handlers'):
            validate_tasks(play.get(key, []))

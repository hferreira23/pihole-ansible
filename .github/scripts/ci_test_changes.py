"""Conservatively skip collection tests for changes they cannot exercise."""

import os
from pathlib import Path
import subprocess
import sys


IGNORED_FILES = {
    'LICENSE', '.gitignore', '.ansible-lint', '.yamllint',
    '.github/dependabot.yml', '.github/release-please-config.json',
    '.github/release-please-manifest.json',
}


def tests_required(paths):
    for path in paths:
        # Documentation fixtures and embedded module docs are test inputs too.
        if path.startswith(('plugins/', 'tests/', 'meta/')):
            return True
        if path.startswith(('roles/', '.github/ISSUE_TEMPLATE/')):
            continue
        if path.lower().endswith('.md') or path in IGNORED_FILES:
            continue
        if path.startswith('.github/workflows/') and path != '.github/workflows/tests.yml':
            continue
        # Examples, packaging, the test workflow/selector, and unknown paths run.
        return True
    return False


def changed_paths(base, head, pull_request):
    if not base or not head or set(base) == {'0'}:
        raise ValueError('No usable comparison revision')
    if pull_request:
        base = subprocess.check_output(['git', 'merge-base', base, head], text=True).strip()
    output = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', '-z', base, head, '--'])
    return [os.fsdecode(path) for path in output.split(b'\0') if path]


def main():
    event = os.environ.get('EVENT_NAME', '')
    required = True  # Manual/unknown events and failed detection always run.
    if event in ('push', 'pull_request'):
        try:
            required = tests_required(changed_paths(os.environ.get('BASE_SHA'), os.environ.get('HEAD_SHA'),
                                                   event == 'pull_request'))
        except (subprocess.CalledProcessError, ValueError) as error:
            print('::warning::Changed-file detection failed; running tests: {0}'.format(error), file=sys.stderr)
    value = 'true' if required else 'false'
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        output.write('required={0}\n'.format(value))
    print('Collection tests required: {0}'.format(value))


if __name__ == '__main__':
    main()

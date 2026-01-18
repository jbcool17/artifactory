import json
import os
import subprocess
from pathlib import Path

from yaml import safe_load

REPO_OWNER = os.getenv('GITHUB_REPOSITORY_OWNER', 'jbcool17')
SCRIPT_MODE = os.getenv('PY_SCRIPT_MODE', 'dockerfile_changes')

def set_github_output(name, value):
    """
    Appends a key-value pair to the GITHUB_OUTPUT file.
    """
    output_file = os.getenv('GITHUB_OUTPUT')
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{name}={value}\n")
        print(f"Set GitHub output: {name}={value}")
    else:
        # Fallback for local testing or unexpected environments
        print(f"GITHUB_OUTPUT environment variable not found. \n Output would be: {name}={value}")


def run_gh_command(command):
    """Runs a GitHub CLI command and returns the JSON output as a Python dictionary."""
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, check=True
    )
    return json.loads(
        result.stdout
    )  # Convert JSON string to a Python dictionary


def get_latest_commit_sha(repo, branch='main'):
    """
    Gets the latest commit SHA for the given repository and branch.
    Default branch is 'main' if none is specified.
    """
    # Note the added '?sha={branch}' so we query the correct branch
    command = f'gh api repos/{repo}/commits?sha={branch}'
    commits = run_gh_command(command)
    return commits[0]['sha']  # Extract SHA from the latest commit


def get_changed_files(repo, commit_sha):
    """Gets the list of changed files in a given commit."""
    command = f'gh api repos/{repo}/commits/{commit_sha}'
    commit_data = run_gh_command(command)

    # Extract filenames from the commit details
    files = [file['filename'] for file in commit_data.get('files', [])]
    return files


def setup_dockerfile_data(path: str) -> dict:
    """Load docker-build-config.yml for each path and add PROJECT_FOLDER."""
    print(f'Loading docker-build-config.yml from path: {path}')
    config_file = Path(path) / 'docker-build-config.yml'

    if not config_file.exists():
        print(f'{config_file} not found. Skipping')
        return {}

    with config_file.open('r') as f:
        config = safe_load(f) or {}

    # Add PROJECT_FOLDER based on the path
    config['PROJECT_FOLDER'] = f'./{path}'

    print(f'Loaded config: {config}')

    return config


if __name__ == '__main__':
    # Default behavior: get changed files from latest commit
    output_data = []
    repo_name = run_gh_command('gh repo view --json name')['name']
    repo = f'{REPO_OWNER}/{repo_name}'
    print(f'Repo: {repo}')

    # Read branch from env var, default to 'main'
    branch = os.getenv('PY_SCRIPT_BRANCH', 'main')
    print(f'Using branch: {branch}')

    # Get latest commit SHA
    latest_commit_sha = get_latest_commit_sha(repo, branch)
    print(f"Latest commit on '{branch}': {latest_commit_sha}")

    # Get changed files in the latest commit
    changed_files = get_changed_files(repo, latest_commit_sha)
    print(f'Changed files: {json.dumps(changed_files, indent=2)}')

    # Process changed files to find Dockerfiles and load their configs
    for file in changed_files:
        print(f'Processing changed file: {file}')
        
        # Check if the changed file is a Dockerfile
        if 'Dockerfile' in file and SCRIPT_MODE == 'dockerfile_changes':
            print(f'Found Dockerfile change: {file}')
            path = '/'.join(file.split('/')[:-1])
            output_data.append(setup_dockerfile_data(path))

        # Check if the changed file is a Helm Chart definition
        if "Chart.yml" in file and SCRIPT_MODE == 'helm_chart_changes':
            print(f'Found Helm Chart change: {file}')
            path = '/'.join(file.split('/')[:-1])
            with open(file, 'r') as f:
                chart_data = safe_load(f) or {}
            chart_data['CHART_PATH'] = f'./{path}'
            output_data.append(chart_data)

    print(f'Output data: {json.dumps(output_data, indent=2)}')

    set_github_output('matrix', json.dumps(output_data))

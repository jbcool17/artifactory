import json
import logging
import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from yaml import safe_load

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

REPO_OWNER = os.getenv('GITHUB_REPOSITORY_OWNER', 'jbcool17')
BRANCH_DEFAULT = 'main'
CONFIG_FILENAME = 'docker-build-config.yml'
CHART_FILENAME = 'Chart.yml'


class ScriptMode(Enum):
    """Script execution modes."""
    DOCKERFILE_CHANGES = 'dockerfile_changes'
    HELM_CHART_CHANGES = 'helm_chart_changes'

    @classmethod
    def from_env(cls) -> 'ScriptMode':
        """Get script mode from environment variable."""
        mode_str = os.getenv('PY_SCRIPT_MODE', cls.DOCKERFILE_CHANGES.value)
        try:
            return cls(mode_str)
        except ValueError:
            logger.warning(
                f'Invalid script mode "{mode_str}", using default: {cls.DOCKERFILE_CHANGES.value}'
            )
            return cls.DOCKERFILE_CHANGES

def set_github_output(name: str, value: str) -> None:
    """
    Append a key-value pair to the GITHUB_OUTPUT file.
    
    Args:
        name: The output variable name.
        value: The output variable value.
    """
    output_file = os.getenv('GITHUB_OUTPUT')
    if output_file:
        try:
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(f'{name}={value}\n')
            logger.info(f'Set GitHub output: {name}={value}')
        except OSError as e:
            logger.error(f'Failed to write to GITHUB_OUTPUT: {e}')
    else:
        logger.warning(
            f'GITHUB_OUTPUT environment variable not found. '
            f'Output would be: {name}={value}'
        )


def run_gh_command(command: str) -> Dict[str, Any]:
    """
    Run a GitHub CLI command and return the JSON output.
    
    Args:
        command: The GitHub CLI command to execute.
        
    Returns:
        Parsed JSON response as a dictionary.
        
    Raises:
        subprocess.CalledProcessError: If the command fails.
        json.JSONDecodeError: If the output is not valid JSON.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f'GitHub CLI command failed: {e.stderr}')
        raise
    except json.JSONDecodeError as e:
        logger.error(f'Invalid JSON response: {e}')
        raise


def get_latest_commit_sha(repo: str, branch: str = BRANCH_DEFAULT) -> str:
    """
    Get the latest commit SHA for the given repository and branch.
    
    Args:
        repo: Repository in format 'owner/name'.
        branch: The branch to query (default: 'main').
        
    Returns:
        The latest commit SHA.
        
    Raises:
        subprocess.CalledProcessError: If the command fails.
        IndexError: If no commits found.
    """
    command = f'gh api repos/{repo}/commits?sha={branch}'
    try:
        commits = run_gh_command(command)
        if not commits:
            raise IndexError(f'No commits found for {repo} on branch {branch}')
        return commits[0]['sha']  # type: ignore[index]
    except IndexError as e:
        logger.error(str(e))
        raise


def get_changed_files(repo: str, commit_sha: str) -> List[str]:
    """
    Get the list of changed files in a given commit.
    
    Args:
        repo: Repository in format 'owner/name'.
        commit_sha: The commit SHA to query.
        
    Returns:
        List of changed file paths.
    """
    command = f'gh api repos/{repo}/commits/{commit_sha}'
    commit_data = run_gh_command(command)
    files = [file['filename'] for file in commit_data.get('files', [])]
    return files


def load_docker_config(path: str) -> Dict[str, Any]:
    """
    Load docker-build-config.yml from the given path.
    
    Args:
        path: Path to the directory containing docker-build-config.yml.
        
    Returns:
        Configuration dictionary with PROJECT_FOLDER added, or empty dict if file not found.
    """
    logger.info(f'Loading {CONFIG_FILENAME} from path: {path}')
    config_file = Path(path) / CONFIG_FILENAME

    if not config_file.exists():
        logger.debug(f'{config_file} not found. Skipping.')
        return {}

    try:
        with config_file.open('r', encoding='utf-8') as f:
            config = safe_load(f) or {}
        config['PROJECT_FOLDER'] = f'./{path}'
        logger.debug(f'Loaded config: {config}')
        return config
    except OSError as e:
        logger.error(f'Failed to read {config_file}: {e}')
        return {}


def load_chart_config(file_path: str, dir_path: str) -> Dict[str, Any]:
    """
    Load Chart.yml configuration.
    
    Args:
        file_path: Path to the Chart.yml file.
        dir_path: Directory containing the chart.
        
    Returns:
        Chart configuration dictionary with CHART_PATH added.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            chart_data = safe_load(f) or {}
        chart_data['CHART_PATH'] = f'./{dir_path}'
        return chart_data
    except OSError as e:
        logger.error(f'Failed to read {file_path}: {e}')
        return {}


def extract_directory_from_filepath(file_path: str) -> str:
    """
    Extract directory path from a file path.
    
    Args:
        file_path: The full file path.
        
    Returns:
        The directory containing the file.
    """
    return '/'.join(file_path.split('/')[:-1])


def process_changed_file(
    file_path: str,
    script_mode: ScriptMode
) -> Dict[str, Any]:
    """
    Process a changed file and extract configuration data based on script mode.
    
    Args:
        file_path: The path of the changed file.
        script_mode: The current script execution mode.
        
    Returns:
        Configuration dictionary if file matches mode, otherwise empty dict.
    """
    if script_mode == ScriptMode.DOCKERFILE_CHANGES:
        if 'Dockerfile' in file_path:
            logger.info(f'Found Dockerfile change: {file_path}')
            directory = extract_directory_from_filepath(file_path)
            return load_docker_config(directory)

    elif script_mode == ScriptMode.HELM_CHART_CHANGES:
        if CHART_FILENAME in file_path:
            logger.info(f'Found Helm Chart change: {file_path}')
            directory = extract_directory_from_filepath(file_path)
            return load_chart_config(file_path, directory)

    return {}


def main() -> None:
    """Main entry point for the script."""
    # Get repository information
    repo_data = run_gh_command('gh repo view --json name')
    repo_name = repo_data.get('name')
    if not repo_name:
        logger.error('Failed to retrieve repository name')
        return
    
    repo = f'{REPO_OWNER}/{repo_name}'
    logger.info(f'Repo: {repo}')

    # Get script mode and branch configuration
    script_mode = ScriptMode.from_env()
    logger.info(f'Script mode: {script_mode.value}')

    branch = os.getenv('PY_SCRIPT_BRANCH', BRANCH_DEFAULT)
    logger.info(f'Using branch: {branch}')

    # Get latest commit and changed files
    try:
        latest_commit_sha = get_latest_commit_sha(repo, branch)
        logger.info(f"Latest commit on '{branch}': {latest_commit_sha}")

        changed_files = get_changed_files(repo, latest_commit_sha)
        logger.info(f'Changed files: {json.dumps(changed_files, indent=2)}')
    except (subprocess.CalledProcessError, IndexError) as e:
        logger.error(f'Failed to retrieve commit information: {e}')
        return

    # Process changed files
    output_data = []
    for file_path in changed_files:
        logger.debug(f'Processing changed file: {file_path}')
        config = process_changed_file(file_path, script_mode)
        if config:
            output_data.append(config)

    logger.info(f'Output data: {json.dumps(output_data, indent=2)}')


if __name__ == '__main__':
    main()

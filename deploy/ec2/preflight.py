"""Offline check: never initializes tables or prints credential values."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.deployment import deployment_errors, read_deployment_values
from backend.ai_config import resolve_openai_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    args = parser.parse_args()
    values = read_deployment_values(args.env_file)
    errors = deployment_errors(values)
    if not Path(args.env_file).is_file():
        errors.append('ENV_FILE_MISSING')
    if not resolve_openai_key(values):
        errors.append('LUNA_KEY_NOT_READABLE')
    print(json.dumps({'configuration_ready': not errors, 'errors': errors,
                      'database_verified': False, 'aws_role_verified': False,
                      'https_verified': False, 'application_deployed': False}))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())

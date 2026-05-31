#!/usr/bin/env python3
"""Jelastic REST API client for Infomaniak Cloud.

Provides deployment, environment management, and snapshot operations.

Usage (CLI):
    uv run jelastic_client.py list-envs
    uv run jelastic_client.py get-status --env-name <name>
    uv run jelastic_client.py create-env --env-name <name> --node-type nodejs20-npm
    uv run jelastic_client.py deploy --env-name <name> --branch <branch>
    uv run jelastic_client.py clone-env --env-name <name> --clone-name <backup>

Environment variables:
    JELASTIC_TOKEN — Personal Access Token (required)
    JELASTIC_API_URL — API base URL (default: Infomaniak)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_API_URL = "https://jca.jpc.infomaniak.com/1.0"


class JelasticError(Exception):
    """Jelastic API error."""

    def __init__(self, message: str, result_code: int = -1):
        super().__init__(message)
        self.result_code = result_code


class JelasticClient:
    """Infomaniak Jelastic REST API client."""

    def __init__(self, token: str, api_url: str = DEFAULT_API_URL):
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _call(self, endpoint: str, **params: Any) -> dict:
        """Make a POST request to the Jelastic API."""
        url = f"{self.api_url}/{endpoint}"
        params["session"] = self.token

        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            # URL is constructed from self.api_url (Jelastic API endpoint configured at client init) + a fixed endpoint path.
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with urllib.request.urlopen(req, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise JelasticError(f"HTTP {e.code}: {e.reason}", e.code)
        except urllib.error.URLError as e:
            raise JelasticError(f"Connection error: {e.reason}")

        if body.get("result") != 0:
            raise JelasticError(
                body.get("error", f"API error (result={body.get('result')})"),
                body.get("result", -1),
            )

        return body

    def list_envs(self) -> list[dict]:
        """List all environments."""
        response = self._call("environment/control/rest/getenvs")
        return response.get("infos", [])

    def get_env_info(self, env_name: str) -> dict:
        """Get environment details."""
        return self._call("environment/control/rest/getenvinfo", envName=env_name)

    def create_env(
        self,
        env_name: str,
        node_type: str = "nodejs20-npm",
        cloudlets: int = 8,
    ) -> dict:
        """Create a new environment."""
        env_config = json.dumps({
            "shortdomain": env_name,
            "engine": "nodejs20",
            "region": "default_hn_group",
        })
        nodes_config = json.dumps([{
            "nodeType": node_type,
            "nodeGroup": "cp",
            "flexibleCloudlets": cloudlets,
            "fixedCloudlets": 1,
        }])
        return self._call(
            "environment/control/rest/createenvironment",
            env=env_config,
            nodes=nodes_config,
        )

    def deploy_from_git(
        self,
        env_name: str,
        repo_url: str,
        branch: str = "main",
        context: str = "ROOT",
    ) -> dict:
        """Deploy from a git repository.

        First creates a VCS project if needed, then updates.
        """
        # Try update first (project may already exist)
        try:
            return self._call(
                "environment/vcs/rest/update",
                envName=env_name,
                context=context,
            )
        except JelasticError:
            # Project doesn't exist — create it
            self._call(
                "environment/vcs/rest/createproject",
                envName=env_name,
                type="git",
                context=context,
                url=repo_url,
                branch=branch,
            )
            return self._call(
                "environment/vcs/rest/update",
                envName=env_name,
                context=context,
            )

    def clone_env(self, env_name: str, clone_name: str) -> dict:
        """Clone an environment (for backup/rollback)."""
        return self._call(
            "environment/control/rest/cloneenv",
            srcEnvName=env_name,
            dstEnvName=clone_name,
        )

    def delete_env(self, env_name: str) -> dict:
        """Delete an environment."""
        return self._call("environment/control/rest/deleteenv", envName=env_name)

    def start_env(self, env_name: str) -> dict:
        """Start an environment."""
        return self._call("environment/control/rest/startenv", envName=env_name)

    def stop_env(self, env_name: str) -> dict:
        """Stop an environment."""
        return self._call("environment/control/rest/stopenv", envName=env_name)

    def restart_nodes(self, env_name: str, node_group: str = "cp") -> dict:
        """Restart compute nodes."""
        return self._call(
            "environment/control/rest/restartnodes",
            envName=env_name,
            nodeGroup=node_group,
        )

    def set_env_vars(self, env_name: str, vars: dict, node_group: str = "cp") -> dict:
        """Set environment variables."""
        return self._call(
            "environment/control/rest/addcontainerenvvars",
            envName=env_name,
            vars=json.dumps(vars),
            nodeGroup=node_group,
        )

    def get_env_url(self, env_name: str) -> str:
        """Get the public URL for an environment."""
        return f"https://{env_name}.jpc.infomaniak.com"


def get_client() -> JelasticClient:
    """Create a client from environment variables."""
    token = os.environ.get("JELASTIC_TOKEN")
    if not token:
        raise JelasticError("JELASTIC_TOKEN environment variable not set")
    api_url = os.environ.get("JELASTIC_API_URL", DEFAULT_API_URL)
    return JelasticClient(token, api_url)


# CLI interface
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jelastic API client")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-envs")

    p = subparsers.add_parser("get-status")
    p.add_argument("--env-name", required=True)

    p = subparsers.add_parser("create-env")
    p.add_argument("--env-name", required=True)
    p.add_argument("--node-type", default="nodejs20-npm")
    p.add_argument("--cloudlets", type=int, default=8)

    p = subparsers.add_parser("deploy")
    p.add_argument("--env-name", required=True)
    p.add_argument("--repo-url", default="")
    p.add_argument("--branch", default="main")

    p = subparsers.add_parser("clone-env")
    p.add_argument("--env-name", required=True)
    p.add_argument("--clone-name", required=True)

    args = parser.parse_args()

    try:
        client = get_client()

        if args.command == "list-envs":
            envs = client.list_envs()
            print(json.dumps({"success": True, "environments": envs}, indent=2))

        elif args.command == "get-status":
            info = client.get_env_info(args.env_name)
            print(json.dumps({"success": True, "info": info}, indent=2))

        elif args.command == "create-env":
            result = client.create_env(args.env_name, args.node_type, args.cloudlets)
            print(json.dumps({"success": True, "result": result}, indent=2))

        elif args.command == "deploy":
            result = client.deploy_from_git(args.env_name, args.repo_url, args.branch)
            print(json.dumps({"success": True, "result": result}, indent=2))

        elif args.command == "clone-env":
            result = client.clone_env(args.env_name, args.clone_name)
            print(json.dumps({"success": True, "result": result}, indent=2))

    except JelasticError as e:
        print(json.dumps({"success": False, "error": str(e)}, indent=2))
        sys.exit(1)

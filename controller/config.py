"""Static experiment configuration and credential boundary."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts"
RUNTIME_ROOT = ARTIFACTS_ROOT / "runtime"
FIXTURES_ROOT = REPO_ROOT / "fixtures"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

EXPERIMENT_VERSION = "spike-001-live-validation"
AGENT_ID_ENV_VAR = "ARMIE_SRE_AGENT_ID"
OPENAI_PROJECT_ID_ENV_VAR = "OPENAI_PROJECT_ID"
MODEL = "gpt-5.6-luna"
TARGET_SERVICE_VERSION = "synthetic-payment-api-2026.09.20.2"
DEPLOYMENT_VERSION = "deploy-2026-09-20.2"
ENVIRONMENT_TYPE = "self_hosted"
TARGET_BASE_URL = "http://127.0.0.1:18080"

AGENT_INSTRUCTIONS = """You are an SRE assistant investigating production incidents. Help the user understand the impact, identify the likely cause, and choose a safe next step.

1. Establish the affected service, symptoms, incident time window, and customer impact. Ask for missing details that materially affect the investigation.
2. Inspect the evidence provided by the user and relevant logs, runbooks, repositories, and incident history available in your workspace. Use configured scripts or command-line tools for additional read-only investigation when available. Do not assume access to Slack, GitHub, AWS, or monitoring systems; explain which missing access or evidence is needed.
3. Build a timeline, compare recent deployments or configuration changes, and test competing explanations. Distinguish observations from hypotheses and cite the files, log entries, or query results supporting each conclusion.
4. Summarize impact, the most likely cause, confidence, and remaining questions. Recommend a mitigation with its risks, verification steps, and rollback plan.

Do not change infrastructure, restart services, or perform a rollback without explicit authorization. Never invent telemetry or claim an action succeeded without evidence."""

INITIAL_USER_MESSAGE = (
    "A production incident is affecting the checkout service. Error rates increased "
    "during the reported incident window. Investigate the available system evidence, "
    "establish a timeline, test competing hypotheses, identify the most likely cause "
    "and remaining uncertainty, and recommend the safest next action. Do not make any "
    "production changes without explicit approval."
)


def _required_value(name: str, env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    value = source.get(name, "")
    if not value.strip():
        raise RuntimeError(f"{name} is required for this operation")
    return value.strip()


def require_openai_api_key(env: Mapping[str, str] | None = None) -> str:
    """Return the controller credential without ever displaying it."""

    return _required_value("OPENAI_API_KEY", env)


def require_executor_api_key(env: Mapping[str, str] | None = None) -> str:
    """Return the separately scoped executor credential without displaying it."""

    return _required_value("OPENAI_EXECUTOR_API_KEY", env)


def credential_presence(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Report credential readiness without exposing any credential property."""

    source = os.environ if env is None else env
    return {
        "OPENAI_API_KEY": "present" if source.get("OPENAI_API_KEY", "").strip() else "missing",
        "OPENAI_EXECUTOR_API_KEY": (
            "present" if source.get("OPENAI_EXECUTOR_API_KEY", "").strip() else "missing"
        ),
    }


def require_runtime_identifiers(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Read non-secret saved-agent/project identifiers from the local environment."""

    return (
        _required_value(AGENT_ID_ENV_VAR, env),
        _required_value(OPENAI_PROJECT_ID_ENV_VAR, env),
    )


def session_payload(
    agent_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, object]:
    """Build the saved-agent reference plus the requested session overrides."""

    if agent_id is None or project_id is None:
        configured_agent_id, configured_project_id = require_runtime_identifiers()
        agent_id = agent_id or configured_agent_id
        project_id = project_id or configured_project_id

    return {
        "agent_id": agent_id,
        "agent": {
            "model": MODEL,
            "instructions": AGENT_INSTRUCTIONS,
            "reasoning": {"effort": "medium", "summary": "auto"},
            "text": {"format": {"type": "text"}, "verbosity": "medium"},
        },
        "environment": {
            "type": ENVIRONMENT_TYPE,
            "workspace_directory": "/workspace",
        },
        "metadata": {
            "experiment": "armie-operational-intelligence",
            "experiment_version": EXPERIMENT_VERSION,
            "openai_project_id": project_id,
        },
    }

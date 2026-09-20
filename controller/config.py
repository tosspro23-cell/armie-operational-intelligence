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

EXPERIMENT_VERSION = "spike-001"
AGENT_ID = "agent_8041a399c9434e048f081b847bd11b74bf6e735fde2f4685a4"
OPENAI_PROJECT_ID = "proj_9sCbaTpOFpqXFsKs4FXhbzFz"
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


def require_openai_api_key(env: Mapping[str, str] | None = None) -> str:
    """Return the only accepted credential, without ever displaying it."""

    source = os.environ if env is None else env
    value = source.get("OPENAI_API_KEY", "")
    if not value.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is required for the real Agents API acceptance run"
        )
    return value


def session_payload() -> dict[str, object]:
    """Build the saved-agent reference plus the requested session overrides."""

    return {
        "agent_id": AGENT_ID,
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
            "openai_project_id": OPENAI_PROJECT_ID,
        },
    }


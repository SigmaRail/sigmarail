#!/usr/bin/env bash
# Run sigmarail-studio MCP in stdio mode (Cursor MCP config).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT}/.." && pwd)"
FINANCE_PROJECTS="${SIGMARAIL_WORKSPACE_ROOT:-}"
if [[ -z "${FINANCE_PROJECTS}" ]]; then
  candidate="${REPO_ROOT}"
  while [[ "${candidate}" != "/" ]]; do
    if [[ -d "${candidate}/packages/sigmarail-spec/src" ]]; then
      FINANCE_PROJECTS="${candidate}"
      break
    fi
    candidate="$(dirname "${candidate}")"
  done
fi
FINANCE_PROJECTS="${FINANCE_PROJECTS:-${REPO_ROOT}}"
SIGMARAIL_SPEC_SOURCE="${SIGMARAIL_SPEC_SOURCE:-${REPO_ROOT}/packages/sigmarail-spec/src}"
SIGMARAIL_CORE_SOURCE="${SIGMARAIL_CORE_SOURCE:-${REPO_ROOT}/src}"
export SIGMARAIL_WORKSPACE_ROOT="${SIGMARAIL_WORKSPACE_ROOT:-${FINANCE_PROJECTS}}"

export PYTHONPATH="${ROOT}:${SIGMARAIL_SPEC_SOURCE}:${SIGMARAIL_CORE_SOURCE}${PYTHONPATH:+:${PYTHONPATH}}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-stdio}"

# Use the repository environment by default; deployments may select a managed interpreter.
PYTHON_EXE="${SIGMARAIL_STUDIO_PYTHON:-${REPO_ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON_EXE}" ]]; then
  echo "SigmaRail Studio Python not found at ${PYTHON_EXE}; create .venv and install the project dependencies or set SIGMARAIL_STUDIO_PYTHON." >&2
  exit 1
fi

exec "${PYTHON_EXE}" -m sigmarail_studio_mcp.server

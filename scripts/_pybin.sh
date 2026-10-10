#!/usr/bin/env bash
set -euo pipefail

readonly PLANVEYOR_PYTHON_MIN_MAJOR=3
readonly PLANVEYOR_PYTHON_MIN_MINOR=10

planveyor_pybin_validate_version() {
  local python_cmd="${1:-}"
  local min_major="${2:-${PLANVEYOR_PYTHON_MIN_MAJOR}}"
  local min_minor="${3:-${PLANVEYOR_PYTHON_MIN_MINOR}}"

  if [[ -z "${python_cmd}" ]]; then
    echo "[pybin] Usage: planveyor_pybin_validate_version <PYTHON_CMD> [MIN_MAJOR] [MIN_MINOR]" >&2
    return 2
  fi

  if ! "${python_cmd}" -c "import sys; raise SystemExit(0 if (${min_major}, ${min_minor}) <= sys.version_info[:2] < (3, 13) else 1)" >/dev/null 2>&1; then
    echo "[pybin] Python >=${min_major}.${min_minor},<3.13 required by pyproject.toml: ${python_cmd}" >&2
    echo "[pybin] Bootstrap after selecting interpreter:" >&2
    echo "[pybin]   ${python_cmd} -m pip install -r requirements-dev.lock" >&2
    return 2
  fi
}

planveyor_pybin_resolve() {
  local root="${1:-}"
  if [[ -z "${root}" ]]; then
    echo "[pybin] Usage: planveyor_pybin_resolve <REPO_ROOT>" >&2
    return 2
  fi

  if [[ -n "${PYBIN:-}" ]]; then
    if [[ "${PYBIN}" == *[[:space:]]* ]]; then
      echo "[pybin] PYBIN must be a single executable path or command name (no spaces): ${PYBIN}" >&2
      return 2
    fi
    if [[ "${PYBIN}" == /* ]]; then
      if [[ ! -x "${PYBIN}" ]]; then
        echo "[pybin] PYBIN not executable: ${PYBIN}" >&2
        return 2
      fi
    else
      if ! command -v "${PYBIN}" >/dev/null 2>&1; then
        echo "[pybin] PYBIN not found in PATH: ${PYBIN}" >&2
        return 2
      fi
    fi
    export PYBIN
    return 0
  fi

  # A project file is never an executable selector. Trust only the caller's
  # explicit process environment or a Python discovered on that PATH.
  if [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
    PYBIN="${CONDA_PREFIX}/bin/python"
    export PYBIN
    return 0
  fi

  local path_python3=""
  path_python3="$(command -v python3 2>/dev/null || true)"
  if [[ -n "${path_python3}" && -x "${path_python3}" ]]; then
    PYBIN="${path_python3}"
    export PYBIN
    return 0
  fi

  echo "[pybin] Missing trusted PYBIN and no python3 fallback found." >&2
  echo "[pybin] Fix options:" >&2
  echo "[pybin]   - export PYBIN=/abs/path/to/conda/env/bin/python" >&2
  echo "[pybin]   - then bootstrap the repo: \"\$PYBIN\" -m pip install -r requirements-dev.lock" >&2
  return 2
}

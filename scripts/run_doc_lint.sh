#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"

if [[ -r "${project_root}/scripts/_pybin.sh" ]]; then
  # Load validation even when the caller explicitly selected PYBIN.
  # shellcheck source=/dev/null
  source "${project_root}/scripts/_pybin.sh"
  if [[ -z "${PYBIN:-}" ]]; then
    planveyor_pybin_resolve "${project_root}" >/dev/null 2>&1 || true
  fi
fi

python_cmd="${PYBIN:-}"
if [[ -z "${python_cmd}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python_cmd="python3"
  elif command -v python >/dev/null 2>&1; then
    python_cmd="python"
  fi
fi

if [[ -z "${python_cmd}" ]]; then
  echo "ERROR: cannot resolve python interpreter for doc-lint." >&2
  echo "Fix: set PYBIN=/abs/path/to/python, or select the planveyor conda env in PATH." >&2
  echo "Then bootstrap the repo with: \"\$PYBIN\" -m pip install -r requirements-dev.lock" >&2
  exit 2
fi

if [[ "${python_cmd}" == /* ]]; then
  if [[ ! -x "${python_cmd}" ]]; then
    echo "ERROR: PYBIN is not executable: ${python_cmd}" >&2
    exit 2
  fi
else
  if ! command -v "${python_cmd}" >/dev/null 2>&1; then
    echo "ERROR: python command not found in PATH: ${python_cmd}" >&2
    exit 2
  fi
fi

if declare -F planveyor_pybin_validate_version >/dev/null 2>&1; then
  planveyor_pybin_validate_version "${python_cmd}" || exit 2
fi

exec env PYTHONDONTWRITEBYTECODE=1 "${python_cmd}" "${project_root}/scripts/doc_lint.py" "$@"

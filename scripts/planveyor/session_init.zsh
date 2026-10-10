# --- Session init (new sessions; no resume) ---
typeset -g _PLANVEYOR_LAST_SAVED_SESSION_ID=""
typeset -g _PLANVEYOR_LAST_SAVED_SESSION_KEY=""

# Engaged initialization publishes a session pointer only after a successful
# init receipt exists for the exact SID.  The public setter performs the
# bridge-side receipt validation; this private path merely keeps the receipt
# and pointer ordering explicit for provider-created SIDs.
_planveyor_init_run_publish_validated_session() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_init_run_publish_validated_session)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local session_key=""
  session_key="$(_planveyor_normalize_session_key "${1:-}")" || return 1
  local sid="${2:-}"
  local meta="${3:-}"
  [[ -n "${sid//[[:space:]]/}" ]] || return 1

  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    _planveyor_session_authority_resume_validate "$session_key" "$sid" || return $?
  fi
  planveyor_session_set "$session_key" "$sid" "$meta" || return $?
  echo "Saved session: key=${session_key} sid=${sid}" >&2
}

_planveyor_runner_selection_init_consume() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_runner_selection_init_consume)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local expected_role=""
  expected_role="$(_planveyor_normalize_role_id "${1:-}")" || {
    echo "runner_selection_error=invalid_role" >&2
    return 1
  }
  local expected_init_attempt_id="${2:-}"
  if (( $# != 3 )) || ! _planveyor_is_uuid "$expected_init_attempt_id" || [[ "$expected_init_attempt_id" != "${expected_init_attempt_id:l}" ]]; then
    echo "runner_selection_error=invalid_init_attempt_id" >&2
    return 1
  fi
  local policy_path=""
  policy_path="$(_planveyor_runner_selection_policy_path)" || {
    echo "runner_selection_error=policy_host_missing" >&2
    return 1
  }
  _planveyor_py_any - "$policy_path" "$expected_role" "$expected_init_attempt_id" "$3" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import unicodedata

policy_path = Path(sys.argv[1])
expected_role = sys.argv[2]
expected_attempt_id = sys.argv[3]
raw_resolution = sys.argv[4]

EXPECTED_MATRIX = {
    "architect": ["codex"],
    "coder": ["codex"],
    "manager": ["codex"],
    "planner": ["codex", "claude"],
    "reviewer": ["codex", "claude"],
}
EXPECTED_POLICY_KEYS = {
    "carrier_states",
    "identity_schema_version",
    "role_runner_matrix",
    "schema_version",
    "selection_fields",
}
EXPECTED_FIELDS = [
    "carrier_state",
    "init_attempt_id",
    "role",
    "runner",
    "schema_version",
    "selection_digest",
]
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def fail(reason: str) -> None:
    print(f"runner_selection_error={reason}", file=sys.stderr)
    raise SystemExit(1)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def load_policy() -> dict[str, object]:
    try:
        info = os.lstat(policy_path)
    except FileNotFoundError:
        fail("policy_host_missing")
    except OSError:
        fail("policy_host_invalid")
    if not stat.S_ISREG(info.st_mode) or not info.st_mode & (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH):
        fail("policy_host_invalid")
    try:
        raw = policy_path.read_text(encoding="utf-8")
        policy = json.loads(raw, object_pairs_hook=unique_object)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        fail("policy_host_invalid")
    if not isinstance(policy, dict) or set(policy) != EXPECTED_POLICY_KEYS:
        fail("policy_host_invalid")
    if policy.get("schema_version") != "runner_selection_resolution.v1":
        fail("policy_host_invalid")
    if policy.get("identity_schema_version") != "runner_selection_identity.v1":
        fail("policy_host_invalid")
    if policy.get("carrier_states") != ["absent_default", "present_valid"]:
        fail("policy_host_invalid")
    if policy.get("selection_fields") != EXPECTED_FIELDS:
        fail("policy_host_invalid")
    if policy.get("role_runner_matrix") != EXPECTED_MATRIX:
        fail("policy_host_invalid")
    return policy


if not UUID_RE.fullmatch(expected_attempt_id):
    fail("invalid_init_attempt_id")
policy = load_policy()
decoder = json.JSONDecoder(object_pairs_hook=unique_object)
start = len(raw_resolution) - len(raw_resolution.lstrip())
try:
    resolution, end = decoder.raw_decode(raw_resolution, start)
except (ValueError, json.JSONDecodeError):
    fail("resolution_malformed")
if raw_resolution[end:].strip():
    fail("resolution_multiple_documents")
if not isinstance(resolution, dict) or set(resolution) != set(EXPECTED_FIELDS):
    fail("resolution_malformed")
if resolution.get("schema_version") != "runner_selection_resolution.v1":
    fail("resolution_malformed")
if resolution.get("role") != expected_role:
    fail("resolution_wrong_role")
if resolution.get("init_attempt_id") != expected_attempt_id:
    fail("resolution_foreign_attempt")
carrier_state = resolution.get("carrier_state")
runner = resolution.get("runner")
digest = resolution.get("selection_digest")
if carrier_state not in {"absent_default", "present_valid"}:
    fail("resolution_malformed")
if not isinstance(runner, str) or runner not in EXPECTED_MATRIX[expected_role]:
    fail("resolution_role_invalid")
if carrier_state == "absent_default" and runner != "codex":
    fail("resolution_malformed")
if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
    fail("resolution_bad_digest")
identity = {
    "carrier_state": carrier_state,
    "role": expected_role,
    "runner": runner,
    "schema_version": "runner_selection_identity.v1",
}
canonical_identity = unicodedata.normalize(
    "NFC",
    json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
)
if hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest() != digest:
    fail("resolution_bad_digest")
print(f"{runner}\t{digest}")
PY
}

_planveyor_runner_selection_init_resolve() {
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "${1:-}")" || return 1
  local init_attempt_id=""
  init_attempt_id="$(_planveyor_uuid4)" || {
    echo "runner_selection_error=init_attempt_id_unavailable" >&2
    return 1
  }
  local resolution_json=""
  resolution_json="$(planveyor_runner_resolve_strict "$role_id" "$init_attempt_id")" || return $?
  local selection=""
  selection="$(_planveyor_runner_selection_init_consume "$role_id" "$init_attempt_id" "$resolution_json")" || {
    local rc=$?
    resolution_json=""
    return $rc
  }
  resolution_json=""
  print -r -- "$selection"
}

_planveyor_init_run_artifacts_root() {
  local root=""
  root="$(_planveyor_project_root)" || return $?
  echo "${root}/.planveyor.init_runs"
}

_planveyor_init_run_provider_home_state() {
  emulate -L zsh
  case "${1:-}" in
    codex)
      [[ -n "${PLANVEYOR_CODEX_HOME//[[:space:]]/}" ]] && print -r -- external-configured || print -r -- consumer-default
      ;;
    *)
      print -r -- unavailable
      ;;
  esac
}

_planveyor_init_run_capture_begin() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_init_run_capture_begin)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || return 1

  local run_id=""
  run_id="$(_planveyor_uuid4 2>/dev/null || true)"
  [[ -n "${run_id//[[:space:]]/}" ]] || run_id="$(TZ=UTC date "+%Y%m%dT%H%M%SZ").$$"

  local capture_dir="$(_planveyor_init_run_artifacts_root)/pending/${role_id}/${run_id}"
  mkdir -p "$capture_dir" || {
    echo "⚠️ Failed to create init run capture dir: ${capture_dir}" >&2
    return 1
  }
  printf '%s\n' "$(_planveyor_now_utc_iso)" > "${capture_dir}/.launched_at" || {
    echo "⚠️ Failed to stamp init run capture dir: ${capture_dir}" >&2
    return 1
  }
  echo "$capture_dir"
}

_planveyor_init_run_capture_finalize() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_init_run_capture_finalize)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local capture_dir="${1:-}"
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$2")" || return 1
  local session_key="${3:-$role_id}"
  local runner="${4:-codex}"
  local profile="${5:-}"
  local provider_home_state="${6:-unavailable}"
  case "$provider_home_state" in
    consumer-default|external-configured|unavailable) ;;
    *) provider_home_state="$(_planveyor_init_run_provider_home_state "$runner")" ;;
  esac
  local output="${7-}"
  local exit_code="${8:-0}"
  local sid="${9:-}"
  local model="${10:-}"
  local runner_alias="${11:-}"
  local configured_model_id="${12:-}"
  local observable_model_id="${13:-}"
  local model_id_state="${14:-}"
  local configured_effort="${15:-}"
  local effort_state="${16:-}"
  local pointer_meta="${17:-}"
  [[ -n "${capture_dir//[[:space:]]/}" ]] || return 1

  local authority_context_json=""
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
    authority_context_json="$PLANVEYOR_CTX_JSON"
    [[ -n "${authority_context_json//[[:space:]]/}" ]] || return 1
  fi

  local launched_at=""
  launched_at="$(cat "${capture_dir}/.launched_at" 2>/dev/null || true)"
  [[ -n "${launched_at//[[:space:]]/}" ]] || launched_at="$(_planveyor_now_utc_iso)"

  local final_dir="$capture_dir"
  if [[ -n "${sid//[[:space:]]/}" ]]; then
    local stable_dir="$(_planveyor_init_run_artifacts_root)/by_sid/${sid}"
    if [[ "$PLANVEYOR_CTX_STATE" == "engaged" && -e "${stable_dir}/meta.json" ]]; then
      echo "⚠️ Refusing to reuse an existing engaged init receipt for sid=${sid}" >&2
      return 1
    fi
    mkdir -p "${stable_dir:h}" || {
      echo "⚠️ Failed to create stable init run parent dir: ${stable_dir:h}" >&2
      stable_dir=""
    }
    if [[ -n "${stable_dir//[[:space:]]/}" ]]; then
      if [[ ! -e "$stable_dir" ]]; then
        if mv "$capture_dir" "$stable_dir" 2>/dev/null; then
          final_dir="$stable_dir"
        else
          mkdir -p "$stable_dir" || {
            echo "⚠️ Failed to create stable init run dir: ${stable_dir}" >&2
            stable_dir=""
          }
          [[ -n "${stable_dir//[[:space:]]/}" ]] && final_dir="$stable_dir"
        fi
      else
        mkdir -p "$stable_dir" || {
          echo "⚠️ Failed to reuse stable init run dir: ${stable_dir}" >&2
          stable_dir=""
        }
        [[ -n "${stable_dir//[[:space:]]/}" ]] && final_dir="$stable_dir"
      fi
    fi
  fi

  mkdir -p "$final_dir" || {
    echo "⚠️ Failed to persist init run artifact dir: ${final_dir}" >&2
    return 1
  }

  print -r -- "$output" > "${final_dir}/run.log" || {
    echo "⚠️ Failed to write init run log: ${final_dir}/run.log" >&2
    return 1
  }

  local meta_tmp="${final_dir}/meta.json.tmp.$$"
  local repo_root=""
  repo_root="$(_planveyor_project_root)" || return $?
  local cwd="$PWD"
  _planveyor_py_any - "$meta_tmp" "$role_id" "$session_key" "$runner" "$profile" "$provider_home_state" "$cwd" "$repo_root" "$launched_at" "$exit_code" "$sid" "$model" "$runner_alias" "$configured_model_id" "$observable_model_id" "$model_id_state" "$configured_effort" "$effort_state" "$authority_context_json" <<'PY'
import json
import sys

(
    meta_path,
    role_id,
    session_key,
    runner,
    profile,
    provider_home_state,
    cwd,
    repo_root,
    launched_at,
    exit_code_s,
    sid,
    model,
    runner_alias,
    configured_model_id,
    observable_model_id,
    model_id_state,
    configured_effort,
    effort_state,
    authority_context_raw,
) = sys.argv[1:20]

exit_code = int(exit_code_s)

payload = {
    "role": role_id,
    "runner": runner,
    "profile": profile,
    "cwd": cwd,
    "repo_root": repo_root,
    "provider_home_state": provider_home_state,
    "launched_at": launched_at,
    "exit_code": exit_code,
    "outcome": "success" if exit_code == 0 else "failed",
    "sid": sid or None,
}
if session_key:
    payload["session_key"] = session_key
if model:
    payload["model"] = model
if runner_alias:
    payload["runner_alias"] = runner_alias
if configured_model_id:
    payload["configured_model_id"] = configured_model_id
if observable_model_id:
    payload["observable_model_id"] = observable_model_id
if model_id_state:
    payload["model_id_state"] = model_id_state
if configured_effort:
    payload["configured_effort"] = configured_effort
if effort_state:
    payload["effort_state"] = effort_state
if authority_context_raw:
    try:
        authority_context = json.loads(authority_context_raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise SystemExit(1)
    if not isinstance(authority_context, dict):
        raise SystemExit(1)
    payload["authority_context"] = authority_context

with open(meta_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PY
  local meta_rc=$?
  if (( meta_rc != 0 )); then
    rm -f "$meta_tmp" 2>/dev/null || true
    echo "⚠️ Failed to write init run metadata: ${final_dir}/meta.json" >&2
    return 1
  fi
  mv "$meta_tmp" "${final_dir}/meta.json" || {
    rm -f "$meta_tmp" 2>/dev/null || true
    echo "⚠️ Failed to finalize init run metadata: ${final_dir}/meta.json" >&2
    return 1
  }

  if [[ "$capture_dir" != "$final_dir" ]]; then
    rm -f "${capture_dir}/.launched_at" 2>/dev/null || true
    rmdir "$capture_dir" 2>/dev/null || true
  fi
  rm -f "${final_dir}/.launched_at" 2>/dev/null || true

  # A provider-created SID is only admitted after its immutable successful
  # receipt has been atomically published.  A failed provider result remains
  # an audit artifact but cannot establish a reusable engaged session.
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" && "$exit_code" == "0" && -n "${sid//[[:space:]]/}" ]]; then
    _planveyor_init_run_publish_validated_session "$session_key" "$sid" "$pointer_meta" || return $?
  fi
}

_planveyor_save_session_key_from_output() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_save_session_key_from_output)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local session_key="$(_planveyor_normalize_session_key "$1")" || return 1
  local output="$2"
  local meta="${3:-}"
  local sid=""
  _PLANVEYOR_LAST_SAVED_SESSION_ID=""
  _PLANVEYOR_LAST_SAVED_SESSION_KEY=""
  sid="$(_planveyor_extract_session_id "$output" || true)"
  if [[ -n "${sid//[[:space:]]/}" ]]; then
    _PLANVEYOR_LAST_SAVED_SESSION_ID="$sid"
    _PLANVEYOR_LAST_SAVED_SESSION_KEY="$session_key"
    if [[ "$PLANVEYOR_CTX_STATE" == "engaged" ]]; then
      # The matching init receipt is written by the caller immediately after
      # this return; publishing here would let an arbitrary SID bypass it.
      echo "Detected session: key=${session_key} sid=${sid}; awaiting init receipt." >&2
    else
      planveyor_session_set "$session_key" "$sid" "$meta" >/dev/null || true
      echo "Saved session: key=${session_key} sid=${sid}" >&2
    fi
  else
    echo "⚠️ Could not detect session id in output. Set manually: planveyor_session_set ${session_key} <SESSION_ID>" >&2
  fi
}

_planveyor_save_session_from_output() {
  local role_id="$(_planveyor_normalize_role_id "$1")" || return 1
  _planveyor_save_session_key_from_output "$role_id" "$2" "${3:-}"
}

planveyor_arch_init() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_init)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect init)" || return $?
  local pybin=""
  pybin="$(_planveyor_resolve_pybin_for_role architect 2>/dev/null || true)"
  pushd "$root" >/dev/null || return 1
  local selection=""
  selection="$(_planveyor_runner_selection_init_resolve architect)" || {
    local selection_rc=$?
    popd >/dev/null || true
    return $selection_rc
  }
  local runner="${selection%%$'\t'*}"
  selection=""
  _planveyor_prepare_role_bundle architect "$pybin"

  local out
  local profile=""
  profile="$(_planveyor_profile_for_role_mode architect main)" || {
    local profile_rc=$?
    popd >/dev/null || true
    return $profile_rc
  }
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$profile")
  local provider_home_state="$(_planveyor_init_run_provider_home_state codex)"
  local capture_dir=""
  local meta="runner=${runner} profile=${profile} provider_home_state=${provider_home_state}"
  local payload=""
  payload="$({ echo "ROLE=Architect"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; })"
  capture_dir="$(_planveyor_init_run_capture_begin architect 2>/dev/null || true)"
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" && -z "${capture_dir//[[:space:]]/}" ]]; then
    echo "Unable to prepare engaged Architect init receipt." >&2
    popd >/dev/null || true
    return 1
  fi
  out="$(printf '%s\n' "$payload" | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" - 2>&1)"
  local rc=$?
  printf '%s\n' "$out"
  _planveyor_save_session_from_output architect "$out" "$meta"
  if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
    _planveyor_init_run_capture_finalize "$capture_dir" architect architect "$runner" "$profile" "$provider_home_state" "$out" "$rc" "${_PLANVEYOR_LAST_SAVED_SESSION_ID:-}" "" "" "" "" "" "" "" "$meta"
    local capture_rc=$?
    [[ "$PLANVEYOR_CTX_STATE" == "engaged" && "$rc" == "0" && "$capture_rc" != "0" ]] && rc=$capture_rc
  fi
  popd >/dev/null || return 1
  return $rc
}

planveyor_manager_init() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_init)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body manager init)" || return $?
  local pybin=""
  pybin="$(_planveyor_resolve_pybin_for_role manager 2>/dev/null || true)"
  pushd "$root" >/dev/null || return 1
  local selection=""
  selection="$(_planveyor_runner_selection_init_resolve manager)" || {
    local selection_rc=$?
    popd >/dev/null || true
    return $selection_rc
  }
  local runner="${selection%%$'\t'*}"
  selection=""

  local out
  local profile=""
  profile="$(_planveyor_profile_for_role_mode manager main)" || {
    local profile_rc=$?
    popd >/dev/null || true
    return $profile_rc
  }
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$profile")
  local provider_home_state="$(_planveyor_init_run_provider_home_state codex)"
  local capture_dir=""
  local meta="runner=${runner} profile=${profile} provider_home_state=${provider_home_state}"
  local payload=""
  payload="$({ echo "ROLE=Manager"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; })"
  capture_dir="$(_planveyor_init_run_capture_begin manager 2>/dev/null || true)"
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" && -z "${capture_dir//[[:space:]]/}" ]]; then
    echo "Unable to prepare engaged Manager init receipt." >&2
    popd >/dev/null || true
    return 1
  fi
  _planveyor_manager_prompt_body_still_current init "$prompt_body" || {
    local binding_rc=$?
    if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
      rm -f "${capture_dir}/.launched_at" >/dev/null 2>&1 || true
      rmdir "$capture_dir" >/dev/null 2>&1 || true
    fi
    popd >/dev/null || return 1
    return $binding_rc
  }
  out="$(printf '%s\n' "$payload" | _planveyor_with_role_env manager "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" - 2>&1)"
  local rc=$?
  printf '%s\n' "$out"
  _planveyor_save_session_from_output manager "$out" "$meta"
  if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
    _planveyor_init_run_capture_finalize "$capture_dir" manager manager "$runner" "$profile" "$provider_home_state" "$out" "$rc" "${_PLANVEYOR_LAST_SAVED_SESSION_ID:-}" "" "" "" "" "" "" "" "$meta"
    local capture_rc=$?
    [[ "$PLANVEYOR_CTX_STATE" == "engaged" && "$rc" == "0" && "$capture_rc" != "0" ]] && rc=$capture_rc
  fi
  popd >/dev/null || return 1
  return $rc
}

planveyor_coder_init() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_coder_init)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body coder init)" || return $?
  local pybin=""
  pybin="$(_planveyor_resolve_pybin_for_role coder 2>/dev/null || true)"
  pushd "$root" >/dev/null || return 1
  local selection=""
  selection="$(_planveyor_runner_selection_init_resolve coder)" || {
    local selection_rc=$?
    popd >/dev/null || true
    return $selection_rc
  }
  local runner="${selection%%$'\t'*}"
  selection=""
  _planveyor_prepare_role_bundle coder "$pybin"

  case "$runner" in
    codex)
      local out
      local profile=""
      profile="$(_planveyor_profile_for_role_mode coder main)" || {
        local profile_rc=$?
        popd >/dev/null || true
        return $profile_rc
      }
      local -a codex_profile_args
      codex_profile_args=()
      [[ -n "${profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$profile")
      local provider_home_state="$(_planveyor_init_run_provider_home_state codex)"
      local capture_dir=""
      local meta="runner=codex profile=${profile} provider_home_state=${provider_home_state}"
      local payload=""
      payload="$({ echo "ROLE=Coder"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; })"
      capture_dir="$(_planveyor_init_run_capture_begin coder 2>/dev/null || true)"
      if [[ "$PLANVEYOR_CTX_STATE" == "engaged" && -z "${capture_dir//[[:space:]]/}" ]]; then
        echo "Unable to prepare engaged Coder init receipt." >&2
        popd >/dev/null || true
        return 1
      fi
      out="$(printf '%s\n' "$payload" | _planveyor_with_role_env coder "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" - 2>&1)"
      local rc=$?
      printf '%s\n' "$out"
      _planveyor_save_session_from_output coder "$out" "$meta"
      if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
        _planveyor_init_run_capture_finalize "$capture_dir" coder coder codex "$profile" "$provider_home_state" "$out" "$rc" "${_PLANVEYOR_LAST_SAVED_SESSION_ID:-}" "" "" "" "" "" "" "" "$meta"
        local capture_rc=$?
        [[ "$PLANVEYOR_CTX_STATE" == "engaged" && "$rc" == "0" && "$capture_rc" != "0" ]] && rc=$capture_rc
      fi
      popd >/dev/null || return 1
      return $rc
      ;;
    *)
      echo "Unsupported coder runner: ${runner} (use: planveyor_runner_set coder codex)" >&2
      popd >/dev/null || return 1
      return 1
      ;;
  esac
}

planveyor_planner_init() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_planner_init)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body planner init)" || return $?
  local pybin=""
  pybin="$(_planveyor_resolve_pybin_for_role planner 2>/dev/null || true)"
  pushd "$root" >/dev/null || return 1
  local selection=""
  selection="$(_planveyor_runner_selection_init_resolve planner)" || {
    local selection_rc=$?
    popd >/dev/null || true
    return $selection_rc
  }
  local runner="${selection%%$'\t'*}"
  selection=""
  _planveyor_prepare_role_bundle planner "$pybin"

  case "$runner" in
    codex)
      local out
      local profile=""
      profile="$(_planveyor_profile_for_role_mode planner main)" || {
        local profile_rc=$?
        popd >/dev/null || true
        return $profile_rc
      }
      local -a codex_profile_args
      codex_profile_args=()
      [[ -n "${profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$profile")
      local provider_home_state="$(_planveyor_init_run_provider_home_state codex)"
      local capture_dir=""
      local meta="runner=codex profile=${profile} provider_home_state=${provider_home_state}"
      local payload=""
      payload="$({ echo "ROLE=Planner"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; })"
      capture_dir="$(_planveyor_init_run_capture_begin planner 2>/dev/null || true)"
      if [[ "$PLANVEYOR_CTX_STATE" == "engaged" && -z "${capture_dir//[[:space:]]/}" ]]; then
        echo "Unable to prepare engaged Planner init receipt." >&2
        popd >/dev/null || true
        return 1
      fi
      out="$(printf '%s\n' "$payload" | _planveyor_with_role_env planner "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" - 2>&1)"
      local rc=$?
      printf '%s\n' "$out"
      _planveyor_save_session_from_output planner "$out" "$meta"
      if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
        _planveyor_init_run_capture_finalize "$capture_dir" planner planner codex "$profile" "$provider_home_state" "$out" "$rc" "${_PLANVEYOR_LAST_SAVED_SESSION_ID:-}" "" "" "" "" "" "" "" "$meta"
        local capture_rc=$?
        [[ "$PLANVEYOR_CTX_STATE" == "engaged" && "$rc" == "0" && "$capture_rc" != "0" ]] && rc=$capture_rc
      fi
      popd >/dev/null || return 1
      return $rc
      ;;
    claude)
      local sid payload out
      sid="$(_planveyor_uuid4)" || { popd >/dev/null; return 1; }
      local claude_model="$(_planveyor_claude_configured_model 2>/dev/null || true)"
      local claude_effort="$(_planveyor_claude_configured_effort 2>/dev/null || true)"
      local claude_model_state="consumer_default"
      local claude_effort_state="consumer_default"
      [[ -n "${claude_model//[[:space:]]/}" ]] && claude_model_state="configured_explicit"
      [[ -n "${claude_effort//[[:space:]]/}" ]] && claude_effort_state="configured_explicit"
      payload="$({ echo "ROLE=Planner"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; })"
      local capture_dir=""
      capture_dir="$(_planveyor_init_run_capture_begin planner)" || {
        echo "Unable to prepare Planner init receipt." >&2
        popd >/dev/null || true
        return 1
      }
      _planveyor_authority_before_raw_claude_launch || {
        local guard_rc=$?
        popd >/dev/null || return 1
        return "$guard_rc"
      }
      out="$(_planveyor_with_role_env planner "$pybin" _planveyor_claude_direct_run -p --session-id "${sid}" --permission-mode acceptEdits "${payload}" 2>&1)"
      local rc=$?
      printf '%s\n' "$out"
      if [[ "$PLANVEYOR_CTX_STATE" != "engaged" ]]; then
        planveyor_session_set planner "$sid" "runner=claude profile=direct_child provider_provenance=direct_child" >/dev/null || true
        echo "Saved session: role=planner sid=${sid}" >&2
      fi
      if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
        _planveyor_init_run_capture_finalize "$capture_dir" planner planner claude direct_child unavailable "$out" "$rc" "$sid" "$claude_model" claude "$claude_model" "" "$claude_model_state" "$claude_effort" "$claude_effort_state" "runner=claude profile=direct_child provider_provenance=direct_child"
        local capture_rc=$?
        [[ "$rc" == "0" && "$capture_rc" != "0" ]] && rc=$capture_rc
      fi
      if (( rc != 0 )); then
        echo "⚠️ Planner init returned non-zero exit code; rerun planveyor_planner_init or retry using this session id." >&2
      fi
      popd >/dev/null || return 1
      return $rc
      ;;
    *)
      echo "Unsupported planner runner: ${runner} (use: planveyor_runner_set planner codex|claude)" >&2
      popd >/dev/null || return 1
      return 1
      ;;
  esac
}

_planveyor_reviewer_init_for_session_key() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_reviewer_init_for_session_key)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  local session_key="${1:-reviewer}"
  local lane_id="${2:-reviewer}"
  local runner=""
  session_key="$(_planveyor_normalize_session_key "$session_key")" || return 1
  [[ -n "${lane_id//[[:space:]]/}" ]] || lane_id="$session_key"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body reviewer init)" || return $?
  local pybin=""
  pybin="$(_planveyor_resolve_pybin_for_role reviewer 2>/dev/null || true)"
  pushd "$root" >/dev/null || return 1
  local selection=""
  selection="$(_planveyor_runner_selection_init_resolve reviewer)" || {
    local selection_rc=$?
    popd >/dev/null || true
    return $selection_rc
  }
  runner="${selection%%$'\t'*}"
  selection=""
  _planveyor_prepare_role_bundle reviewer "$pybin"

  case "$runner" in
    codex)
      local out
      local profile=""
      profile="$(_planveyor_profile_for_role_mode reviewer main)" || {
        local profile_rc=$?
        popd >/dev/null || true
        return $profile_rc
      }
      local -a codex_profile_args
      codex_profile_args=()
      [[ -n "${profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$profile")
      local codex_home="$(_planveyor_codex_home_effective)"
      local provider_home_state="$(_planveyor_init_run_provider_home_state codex)"
      local capture_dir=""
      local model=""
      if [[ -n "${profile//[[:space:]]/}" ]]; then
        model="$(_planveyor_codex_expected_model_for_profile "$profile")" || {
          local model_rc=$?
          popd >/dev/null || true
          return $model_rc
        }
      fi
      local meta="runner=codex profile=${profile} model=${model} session_key=${session_key} lane_id=${lane_id} provider_home_state=${provider_home_state}"
      local payload=""
      payload="$({ echo "ROLE=Reviewer"; echo "REVIEWER_LANE=${lane_id}"; echo "REVIEWER_SESSION_KEY=${session_key}"; echo "REVIEWER_RUNNER=codex"; echo "REVIEWER_PROFILE=${profile}"; echo "REVIEWER_MODEL=${model}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; })"
      capture_dir="$(_planveyor_init_run_capture_begin reviewer)" || {
        echo "Unable to prepare Reviewer init receipt." >&2
        popd >/dev/null || true
        return 1
      }
      out="$(printf '%s\n' "$payload" | _planveyor_with_role_env reviewer "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" - 2>&1)"
      local rc=$?
      printf '%s\n' "$out"
      _planveyor_save_session_key_from_output "$session_key" "$out" "$meta"
      if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
        _planveyor_init_run_capture_finalize "$capture_dir" reviewer "$session_key" codex "$profile" "$provider_home_state" "$out" "$rc" "${_PLANVEYOR_LAST_SAVED_SESSION_ID:-}" "$model" "" "" "" "" "" "" "$meta"
        local capture_rc=$?
        [[ "$PLANVEYOR_CTX_STATE" == "engaged" && "$rc" == "0" && "$capture_rc" != "0" ]] && rc=$capture_rc
      fi
      popd >/dev/null || return 1
      return $rc
      ;;
    claude)
      local sid payload out
      sid="$(_planveyor_uuid4)" || { popd >/dev/null; return 1; }
      local claude_model="$(_planveyor_claude_configured_model 2>/dev/null || true)"
      local claude_effort="$(_planveyor_claude_configured_effort 2>/dev/null || true)"
      local claude_model_state="consumer_default"
      local claude_effort_state="consumer_default"
      [[ -n "${claude_model//[[:space:]]/}" ]] && claude_model_state="configured_explicit"
      [[ -n "${claude_effort//[[:space:]]/}" ]] && claude_effort_state="configured_explicit"
      payload="$({ echo "ROLE=Reviewer"; echo "REVIEWER_LANE=${lane_id}"; echo "REVIEWER_SESSION_KEY=${session_key}"; echo "REVIEWER_RUNNER=claude"; echo "REVIEWER_PROFILE=direct_child"; [[ -n "${claude_model//[[:space:]]/}" ]] && echo "REVIEWER_MODEL=${claude_model}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; })"
      local capture_dir=""
      capture_dir="$(_planveyor_init_run_capture_begin reviewer)" || {
        echo "Unable to prepare Reviewer init receipt." >&2
        popd >/dev/null || true
        return 1
      }
      _planveyor_authority_before_raw_claude_launch || {
        local guard_rc=$?
        popd >/dev/null || return 1
        return "$guard_rc"
      }
      out="$(_planveyor_with_role_env reviewer "$pybin" _planveyor_claude_direct_run -p --session-id "${sid}" --permission-mode acceptEdits "${payload}" 2>&1)"
      local rc=$?
      printf '%s\n' "$out"
      if [[ "$PLANVEYOR_CTX_STATE" != "engaged" ]]; then
        planveyor_session_set "$session_key" "$sid" "runner=claude profile=direct_child provider_provenance=direct_child session_key=${session_key} lane_id=${lane_id}" >/dev/null || true
        echo "Saved session: key=${session_key} sid=${sid}" >&2
      fi
      if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
        _planveyor_init_run_capture_finalize "$capture_dir" reviewer "$session_key" claude direct_child unavailable "$out" "$rc" "$sid" "$claude_model" claude "$claude_model" "" "$claude_model_state" "$claude_effort" "$claude_effort_state" "runner=claude profile=direct_child provider_provenance=direct_child session_key=${session_key} lane_id=${lane_id}"
        local capture_rc=$?
        [[ "$rc" == "0" && "$capture_rc" != "0" ]] && rc=$capture_rc
      fi
      if (( rc != 0 )); then
        echo "⚠️ Reviewer init returned non-zero exit code; rerun ${session_key}_init or retry using this session id." >&2
      fi
      popd >/dev/null || return 1
      return $rc
      ;;
    *)
      echo "Unsupported reviewer runner: ${runner} (use: planveyor_runner_set reviewer codex|claude)" >&2
      popd >/dev/null || return 1
      return 1
      ;;
  esac
  popd >/dev/null || return 1
  return 1
}

planveyor_reviewer_init() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_init)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  _planveyor_reviewer_init_for_session_key reviewer reviewer
}

planveyor_reviewer_code_risk_init() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_code_risk_init)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  _planveyor_reviewer_init_for_session_key reviewer_code_risk reviewer_code_risk
}

planveyor_reviewer_code_contracts_init() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_code_contracts_init)" || return $?
  local _planveyor_ctx_tuple=""
  _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
  local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
  IFS=$'\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
  [[ -z "${_planveyor_ctx_remainder:-}" && ( "$_planveyor_ctx_state" == legacy || "$_planveyor_ctx_state" == engaged ) && -n "${_planveyor_ctx_root//[[:space:]]/}" && ${#_planveyor_ctx_generation} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
  local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
  local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
  local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"

  _planveyor_reviewer_init_for_session_key reviewer_code_contracts reviewer_code_contracts
}

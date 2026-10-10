# --- Doc-finalization helpers (memory-dump; use before switching sessions) ---
# These commands do NOT change plan/status and do NOT require a valid PLAN_PATH.
# They are meant to capture "what the agent remembers" and:
# - update canonical docs (`docs/**`) through the shared `general docs sync` lane
#   (including the exact `Process improvements` section when applicable), and/or
# - create follow-up backlog files in `docs/followups/` through the paired
#   `followups backlog` lane.
planveyor_arch_docs_general() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_docs_general)" || return $?
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

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect docs_finalize_general)" || return $?
  local root="$PLANVEYOR_CTX_ROOT"
  local plan_path; plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local status_pre=""
  local receipt_path=""

  if (( $# > 0 )); then
    if [[ "${1:-}" != "--receipt-path" || $# -ne 2 || -z "${2:-}" ]]; then
      echo "Usage: planveyor_arch_docs_general [--receipt-path docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md]" >&2
      return 2
    fi
    receipt_path="$2"
    if [[ "$receipt_path" == /* || "$receipt_path" == *[[:space:]]* || "$receipt_path" != docs/reviews/* || "$receipt_path" == *".."* ]]; then
      echo "planveyor_arch_docs_general: --receipt-path must be an exact repo-relative docs/reviews path" >&2
      return 2
    fi

    local base="" head="" b7="" h7="" suffix="" stamp=""
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
    b7="$(_planveyor_sha7 "$base" 2>/dev/null || true)"
    h7="$(_planveyor_sha7 "$head" 2>/dev/null || true)"
    suffix="_docs_finalize_receipt_range_${b7}_${h7}.md"
    [[ "$receipt_path" == docs/reviews/*"$suffix" ]] || {
      echo "planveyor_arch_docs_general: --receipt-path does not match current range ${base}..${head}" >&2
      return 2
    }
    stamp="${receipt_path#docs/reviews/}"
    stamp="${stamp%$suffix}"
    [[ "$stamp" =~ '^[0-9]{6}_[0-9]{4}$' ]] || {
      echo "planveyor_arch_docs_general: --receipt-path must use <stamp>_docs_finalize_receipt_range_<base7>_<head7>.md" >&2
      return 2
    }
  fi

  local sid; sid="$(planveyor_session architect)" || return 1
  _planveyor_session_authority_resume_validate architect "$sid" || return $?
  local pybin; pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")

  pushd "$root" >/dev/null || return 1
  if [[ -n "${plan_path//[[:space:]]/}" && -f "$plan_path" ]]; then
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || _planveyor_plan_status_line_lenient "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  fi

  if [[ -n "$receipt_path" ]]; then
    local output=""
    output="$({ echo "ROLE=Architect"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; echo "DOCS_FINALIZE_RECEIPT_PATH=${receipt_path}"; printf '%s\n' "$prompt_body"; } \
      | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
          resume "${sid}" -)"
    local rc=$?
    [[ -n "$output" ]] && print -r -- "$output"
    if (( rc != 0 )); then
      popd >/dev/null || return 1
      return $rc
    fi

    local expected_readback="docs_finalize_receipt_path=${receipt_path}"
    local line="" readback_count=0 exact_readback_count=0
    while IFS= read -r line; do
      if [[ "$line" == docs_finalize_receipt_path=* ]]; then
        (( readback_count += 1 ))
        [[ "$line" == "$expected_readback" ]] && (( exact_readback_count += 1 ))
      fi
    done <<< "$output"
    if (( readback_count != 1 || exact_readback_count != 1 )); then
      echo "planveyor_arch_docs_general: expected exactly ${expected_readback}" >&2
      popd >/dev/null || return 1
      return 2
    fi
  else
    { echo "ROLE=Architect"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
      | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
          resume "${sid}" -
    local rc=$?
  fi
  popd >/dev/null || return 1
  return $rc
}

planveyor_arch_followups() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_followups)" || return $?
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

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect docs_finalize_followups)" || return $?
  local root="$PLANVEYOR_CTX_ROOT"
  local plan_path; plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local sid; sid="$(planveyor_session architect)" || return 1
  _planveyor_session_authority_resume_validate architect "$sid" || return $?
  local pybin; pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre=""

  pushd "$root" >/dev/null || return 1
  if [[ -n "${plan_path//[[:space:]]/}" && -f "$plan_path" ]]; then
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || _planveyor_plan_status_line_lenient "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  fi

  { echo "ROLE=Architect"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_coder_docs_general() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_coder_docs_general)" || return $?
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

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body coder docs_finalize_general)" || return $?
  local root="$PLANVEYOR_CTX_ROOT"
  local plan_path; plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local sid; sid="$(planveyor_session coder)" || return 1
  _planveyor_session_authority_resume_validate coder "$sid" || return $?
  local pybin; pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode coder main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre=""

  pushd "$root" >/dev/null || return 1
  if [[ -n "${plan_path//[[:space:]]/}" && -f "$plan_path" ]]; then
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || _planveyor_plan_status_line_lenient "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  fi

  { echo "ROLE=Coder"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env coder "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_coder_followups() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_coder_followups)" || return $?
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

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body coder docs_finalize_followups)" || return $?
  local root="$PLANVEYOR_CTX_ROOT"
  local plan_path; plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local sid; sid="$(planveyor_session coder)" || return 1
  _planveyor_session_authority_resume_validate coder "$sid" || return $?
  local pybin; pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode coder main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre=""

  pushd "$root" >/dev/null || return 1
  if [[ -n "${plan_path//[[:space:]]/}" && -f "$plan_path" ]]; then
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || _planveyor_plan_status_line_lenient "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  fi

  { echo "ROLE=Coder"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env coder "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_planner_docs_general() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_planner_docs_general)" || return $?
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

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body planner docs_finalize_general)" || return $?
  local root="$PLANVEYOR_CTX_ROOT"
  local plan_path; plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local sid; sid="$(planveyor_session planner)" || return 1
  _planveyor_session_authority_resume_validate planner "$sid" || return $?
  local pybin; pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode planner main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre=""

  pushd "$root" >/dev/null || return 1
  if [[ -n "${plan_path//[[:space:]]/}" && -f "$plan_path" ]]; then
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || _planveyor_plan_status_line_lenient "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  fi

  { echo "ROLE=Planner"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env planner "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_planner_followups() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_planner_followups)" || return $?
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

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body planner docs_finalize_followups)" || return $?
  local root="$PLANVEYOR_CTX_ROOT"
  local plan_path; plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local sid; sid="$(planveyor_session planner)" || return 1
  _planveyor_session_authority_resume_validate planner "$sid" || return $?
  local pybin; pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode planner main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre=""

  pushd "$root" >/dev/null || return 1
  if [[ -n "${plan_path//[[:space:]]/}" && -f "$plan_path" ]]; then
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || _planveyor_plan_status_line_lenient "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  fi

  { echo "ROLE=Planner"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env planner "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_reviewer_docs_general() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_docs_general)" || return $?
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

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body reviewer docs_finalize_general)" || return $?
  local root="$PLANVEYOR_CTX_ROOT"
  local plan_path; plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local sid; sid="$(planveyor_session reviewer)" || return 1
  _planveyor_session_authority_resume_validate reviewer "$sid" || return $?
  local pybin; pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode reviewer main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre=""

  pushd "$root" >/dev/null || return 1
  if [[ -n "${plan_path//[[:space:]]/}" && -f "$plan_path" ]]; then
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || _planveyor_plan_status_line_lenient "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  fi

  { echo "ROLE=Reviewer"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env reviewer "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_reviewer_followups() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_followups)" || return $?
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

  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body reviewer docs_finalize_followups)" || return $?
  local root="$PLANVEYOR_CTX_ROOT"
  local plan_path; plan_path="$(planveyor_planpath 2>/dev/null || true)"
  local sid; sid="$(planveyor_session reviewer)" || return 1
  _planveyor_session_authority_resume_validate reviewer "$sid" || return $?
  local pybin; pybin="$(_planveyor_get_pybin)" || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode reviewer main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local status_pre=""

  pushd "$root" >/dev/null || return 1
  if [[ -n "${plan_path//[[:space:]]/}" && -f "$plan_path" ]]; then
    status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || _planveyor_plan_status_line_lenient "$plan_path" 2>/dev/null || true)"
    [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (pre): ${status_pre}" >&2
  fi

  { echo "ROLE=Reviewer"; [[ -n "${plan_path//[[:space:]]/}" ]] && echo "PLAN_PATH=${plan_path}"; [[ -n "${status_pre//[[:space:]]/}" ]] && echo "PRE_STATUS_LINE=${status_pre}"; echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env reviewer "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

# Contract-authority shell seam.
#
# This file is sourced by scripts/planveyor.zsh only after its pre-line-one
# bootstrap has observed the candidate facade.  It intentionally does not
# select a project root, alter the environment, or define a wrapper registry.

typeset -gr _PLANVEYOR_AUTHORITY_CONTEXT_SEAL='planveyor-contract-context.v1'

_planveyor_authority_fail() {
  print -u2 -r -- "planveyor authority: $*"
  return 1
}

_planveyor_authority_python() {
  local candidate="${_PLANVEYOR_AUTHORITY_BOOT_PYTHON_BIN:-}"
  if [[ -n "${_PLANVEYOR_AUTHORITY_SOURCE_STATE+x}" ]]; then
    _planveyor_authority_source_state_internal || return 1
    candidate="$_PLANVEYOR_AUTHORITY_PYTHON_BIN"
  fi
  [[ "$candidate" == /* && -x "$candidate" ]] || return 1
  print -r -- "$candidate"
}

_planveyor_authority_source_state_internal() {
  # During source bootstrap these locals do not exist yet.  A nounset caller
  # must receive a normal false result so module lookup can use the boot root.
  [[ ${(t)_PLANVEYOR_AUTHORITY_SOURCE_STATE-} == scalar-readonly ]] || return 1
  [[ ${(t)_PLANVEYOR_AUTHORITY_SOURCE_PATH-} == scalar-readonly ]] || return 1
  [[ ${(t)_PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR-} == scalar-readonly ]] || return 1
  [[ ${(t)_PLANVEYOR_AUTHORITY_RUNTIME_ROOT-} == scalar-readonly ]] || return 1
  [[ ${(t)_PLANVEYOR_AUTHORITY_PYTHON_BIN-} == scalar-readonly ]] || return 1
  case "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" in
    pinned)
      [[ ${(t)_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY-} == scalar-readonly ]] || return 1
      [[ ${(t)_PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL-} == scalar-readonly ]] || return 1
      ;;
    unattested_legacy) ;;
    *) return 1 ;;
  esac
}

_planveyor_authority_runtime_root_loaded() {
  if _planveyor_authority_source_state_internal; then
    print -r -- "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT"
    return 0
  fi
  if [[ -n "${_PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT:-}" ]]; then
    print -r -- "$_PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT"
    return 0
  fi
  return 1
}

_planveyor_authority_bridge_path() {
  local runtime_root=""
  runtime_root="$(_planveyor_authority_runtime_root_loaded 2>/dev/null || true)"
  [[ -n "${runtime_root//[[:space:]]/}" ]] || return 1
  local bridge_path="${runtime_root}/scripts/contract_authority_bridge.py"
  [[ -f "$bridge_path" && ! -L "$bridge_path" ]] || return 1
  print -r -- "$bridge_path"
}

_planveyor_authority_bridge() {
  local python_bin="" bridge_path=""
  python_bin="$(_planveyor_authority_python 2>/dev/null || true)"
  bridge_path="$(_planveyor_authority_bridge_path 2>/dev/null || true)"
  [[ -n "${python_bin//[[:space:]]/}" && -n "${bridge_path//[[:space:]]/}" ]] || {
    _planveyor_authority_fail 'authority bridge is unavailable'
    return 1
  }
  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-${_PLANVEYOR_AUTHORITY_BOOT_SOURCE_STATE:-}}" == pinned ]]; then
    local bootstrap="${_PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL:-${PLANVEYOR_SOURCE_BOOTSTRAP:-}}"
    [[ -n "$bootstrap" ]] || return 1
    "$python_bin" -I -B -c "$bootstrap" "$bridge_path" "$@"
  else
    "$python_bin" -B "$bridge_path" "$@"
  fi
}

_planveyor_authority_finalize_loaded_source() {
  local state="${_PLANVEYOR_AUTHORITY_BOOT_SOURCE_STATE:-}"
  local source_path="${_PLANVEYOR_AUTHORITY_BOOT_SOURCE_PATH:-}"
  local source_descriptor="${_PLANVEYOR_AUTHORITY_BOOT_SOURCE_DESCRIPTOR:-}"
  local runtime_root="${_PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT:-}"
  local pin_summary="${_PLANVEYOR_AUTHORITY_BOOT_RUNTIME_PIN_SUMMARY:-}"
  local python_bin="${_PLANVEYOR_AUTHORITY_BOOT_PYTHON_BIN:-}"
  case "$state" in
    pinned|unattested_legacy) ;;
    *) _planveyor_authority_fail 'source bootstrap was not initialized'; return 1 ;;
  esac
  [[ "$python_bin" == /* && -x "$python_bin" && -z "${_PLANVEYOR_AUTHORITY_PYTHON_BIN+x}" ]] || {
    _planveyor_authority_fail 'source interpreter state is invalid'
    return 1
  }
  [[ -n "${source_path//[[:space:]]/}" && -n "${source_descriptor//[[:space:]]/}" && -n "${runtime_root//[[:space:]]/}" ]] || {
    _planveyor_authority_fail 'source bootstrap is incomplete'
    return 1
  }

  _planveyor_authority_bridge source-verify --path "$source_path" \
    --runtime-root "$runtime_root" --descriptor "$source_descriptor" >/dev/null || return $?
  if [[ "$state" == pinned ]]; then
    [[ -n "${pin_summary//[[:space:]]/}" ]] || {
      _planveyor_authority_fail 'pinned source has no runtime pin'
      return 1
    }
    _planveyor_authority_bridge runtime-verify --runtime-pin-summary "$pin_summary" >/dev/null || return $?
  fi

  typeset +x _PLANVEYOR_AUTHORITY_PYTHON_BIN _PLANVEYOR_AUTHORITY_SOURCE_STATE \
    _PLANVEYOR_AUTHORITY_SOURCE_PATH _PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR \
    _PLANVEYOR_AUTHORITY_RUNTIME_ROOT
  typeset -gr _PLANVEYOR_AUTHORITY_PYTHON_BIN="$python_bin"
  typeset -gr _PLANVEYOR_AUTHORITY_SOURCE_STATE="$state"
  typeset -gr _PLANVEYOR_AUTHORITY_SOURCE_PATH="$source_path"
  typeset -gr _PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR="$source_descriptor"
  typeset -gr _PLANVEYOR_AUTHORITY_RUNTIME_ROOT="$runtime_root"
  if [[ "$state" == pinned ]]; then
    [[ ${(t)PLANVEYOR_SOURCE_BOOTSTRAP-} == scalar-local-readonly ]] || return 1
    typeset +x _PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL _PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY
    typeset -gr _PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL="$PLANVEYOR_SOURCE_BOOTSTRAP"
    typeset -gr _PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY="$pin_summary"
  fi
  unset _PLANVEYOR_AUTHORITY_BOOT_SOURCE_STATE _PLANVEYOR_AUTHORITY_BOOT_SOURCE_PATH \
    _PLANVEYOR_AUTHORITY_BOOT_SOURCE_DESCRIPTOR _PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT \
    _PLANVEYOR_AUTHORITY_BOOT_RUNTIME_PIN_SUMMARY _PLANVEYOR_AUTHORITY_BOOT_PYTHON_BIN
  return 0
}

_planveyor_authority_context_field() {
  local context_json="${1:-}" field="${2:-}"
  [[ -n "${context_json//[[:space:]]/}" && -n "${field//[[:space:]]/}" ]] || return 1
  _planveyor_authority_bridge context-field --context "$context_json" --field "$field"
}

# Emit the fixed caller-local tuple in one parser round trip.  The bridge
# validates the compact envelope structurally first and uses tabs only because
# canonical authority paths/text reject all control characters.  Callers must
# bind the values to their own readonly locals; this helper never creates a
# dynamic context or an ambient cache.
_planveyor_authority_context_bindings() {
  local context_json="${1:-}"
  [[ -n "${context_json//[[:space:]]/}" ]] || return 1
  _planveyor_authority_bridge context-bindings --context "$context_json"
}

_planveyor_authority_parent_context_shape() {
  [[ ${(t)PLANVEYOR_CTX_SEAL} == scalar-local-readonly ]] || return 1
  [[ ${(t)PLANVEYOR_CTX_ROOT} == scalar-local-readonly ]] || return 1
  [[ ${(t)PLANVEYOR_CTX_GENERATION} == scalar-local-readonly ]] || return 1
  [[ ${(t)PLANVEYOR_CTX_JSON} == scalar-local-readonly ]] || return 1
  [[ ${(t)PLANVEYOR_CTX_STATE} == scalar-local-readonly ]] || return 1
  [[ "${PLANVEYOR_CTX_SEAL:-}" == "$_PLANVEYOR_AUTHORITY_CONTEXT_SEAL" ]] || return 1
  case "${PLANVEYOR_CTX_STATE:-}" in legacy|engaged) ;; *) return 1 ;; esac
  [[ -n "${PLANVEYOR_CTX_ROOT//[[:space:]]/}" && -n "${PLANVEYOR_CTX_GENERATION//[[:space:]]/}" && -n "${PLANVEYOR_CTX_JSON//[[:space:]]/}" ]] || return 1
}

_planveyor_authority_parent_context_json() {
  _planveyor_authority_parent_context_shape || return 1

  # One parser round trip validates all three caller-local fields.  Do not
  # split this into independent JSON field calls: `_planveyor_root` reaches this
  # path frequently during a guarded invocation.
  _planveyor_authority_bridge context-match --context "$PLANVEYOR_CTX_JSON" \
    --state "$PLANVEYOR_CTX_STATE" --project-root "$PLANVEYOR_CTX_ROOT" \
    --generation-sha256 "$PLANVEYOR_CTX_GENERATION" >/dev/null || return 1
  print -r -- "$PLANVEYOR_CTX_JSON"
}

# Dynamic zsh locals are intentionally the only carrier for a nested context.
# Treat even one visible carrier variable as an assertion: callers must not
# silently fall back to cwd after receiving a forged or incomplete tuple.
_planveyor_authority_context_carrier_present() {
  [[ -n "${PLANVEYOR_CTX_SEAL+x}" || -n "${PLANVEYOR_CTX_ROOT+x}" || \
    -n "${PLANVEYOR_CTX_GENERATION+x}" || -n "${PLANVEYOR_CTX_JSON+x}" || \
    -n "${PLANVEYOR_CTX_STATE+x}" ]]
}

# Only a dynamically inherited, fully verified tuple may keep its original
# root after a nested `cd`.  An expected child envelope is not such a carrier:
# it is always compared against a fresh capture of the child's actual cwd.
_planveyor_authority_local_context_root_for() {
  local context_json="${1:-}" parent_json=""
  _planveyor_authority_context_carrier_present || return 1
  parent_json="$(_planveyor_authority_parent_context_json)" || return $?
  [[ "$parent_json" == "$context_json" ]] || return 1
  print -r -- "$PLANVEYOR_CTX_ROOT"
}

_planveyor_authority_validate_runtime_pin() {
  _planveyor_authority_source_state_internal || {
    _planveyor_authority_fail 'loaded source state is invalid'
    return 1
  }
  [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]] || return 0
  _planveyor_authority_bridge runtime-verify --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" >/dev/null
}

_planveyor_authority_context_command() {
  local mode="${1:-capture}" context_json="${2:-}" output_format="${3:-json}"
  _planveyor_authority_source_state_internal || {
    _planveyor_authority_fail 'loaded source state is invalid'
    return 1
  }
  local -a command_args
  if [[ "$mode" == capture ]]; then
    command_args=(context)
  else
    command_args=(context-validate --context "$context_json" --format "$output_format")
    if _planveyor_authority_context_carrier_present; then
      _planveyor_authority_parent_context_shape && [[ "$context_json" == "$PLANVEYOR_CTX_JSON" ]] || {
        _planveyor_authority_fail 'caller-local context does not match the effect context'
        return 1
      }
      # The active bridge matches this complete tuple before observing its
      # claimed root.  Keep the shell's exact local/readonly shape checks here;
      # no cached structural verdict or unchecked root is accepted.
      command_args+=(--project-root "$PLANVEYOR_CTX_ROOT" --caller-state "$PLANVEYOR_CTX_STATE" \
        --caller-generation-sha256 "$PLANVEYOR_CTX_GENERATION")
    fi
  fi
  if [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]]; then
    command_args+=(--runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY")
  else
    command_args+=(--runtime-root "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT")
  fi
  if [[ "$mode" == capture && -n "${_PLANVEYOR_AUTHORITY_CONTEXT_V1:-}" ]]; then
    command_args+=(--expected "$_PLANVEYOR_AUTHORITY_CONTEXT_V1")
  fi
  _planveyor_authority_bridge "${command_args[@]}"
}

_planveyor_authority_enforce_loaded_root() {
  # State comes from a completed active bridge validation (or from the parser
  # immediately after capture).  This helper only enforces the live shell
  # environment assertion; it never captures or grants authority by itself.
  local state="${1:-}"
  case "$state" in
    legacy|engaged) ;;
    *)
      _planveyor_authority_fail 'authority context state is invalid'
      return 1
      ;;
  esac
  [[ "$state" == engaged ]] || return 0
  [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]] || {
    _planveyor_authority_fail 'engaged authority requires a pinned runtime'
    return 1
  }
  if [[ -n "${PLANVEYOR_ROOT:-}" ]]; then
    [[ -d "$PLANVEYOR_ROOT" ]] || {
      _planveyor_authority_fail 'PLANVEYOR_ROOT is not a directory'
      return 1
    }
    [[ "${PLANVEYOR_ROOT:A}" == "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT" ]] || {
      _planveyor_authority_fail 'PLANVEYOR_ROOT differs from the loaded runtime'
      return 1
    }
  fi
}

# Prints a newly captured compact context.  Callers must put the result into
# their own readonly locals; helpers cannot create caller-local zsh variables.
_planveyor_pre_dispatch() {
  local entrypoint="${1:-}"
  [[ -n "${entrypoint//[[:space:]]/}" ]] || {
    _planveyor_authority_fail 'pre-dispatch caller is required'
    return 1
  }
  if _planveyor_authority_context_carrier_present; then
    _planveyor_authority_parent_context_json >/dev/null || {
      _planveyor_authority_fail 'caller-local context is invalid'
      return 1
    }
  fi
  local context_json=""
  context_json="$(_planveyor_authority_context_command capture)" || return $?
  local state=""
  state="$(_planveyor_authority_context_field "$context_json" state)" || return $?
  _planveyor_authority_enforce_loaded_root "$state" || return $?
  print -r -- "$context_json"
}

# Revalidates the same captured authority before a nested/low-level effect and
# returns the original compact envelope, preserving its entry observation.
_planveyor_authority_before_effect_json() {
  local context_json="${1:-}"
  [[ -n "${context_json//[[:space:]]/}" ]] || {
    _planveyor_authority_fail 'authority context is required before an effect'
    return 1
  }
  local state=""
  state="$(_planveyor_authority_context_command validate "$context_json" state)" || return $?
  _planveyor_authority_enforce_loaded_root "$state" || return $?
  print -r -- "$context_json"
}

_planveyor_authority_before_effect() {
  local context_json=""
  _planveyor_authority_parent_context_shape || {
    _planveyor_authority_fail 'no caller-local authority context'
    return 1
  }
  context_json="$PLANVEYOR_CTX_JSON"
  [[ -n "${context_json//[[:space:]]/}" ]] || {
    _planveyor_authority_fail 'no caller-local authority context'
    return 1
  }
  _planveyor_authority_before_effect_json "$context_json" >/dev/null
}

# Direct content readers do not have a public owner's locals to inherit.  They
# still capture or validate once before their first repository-owned read.
_planveyor_authority_context_for_reader() {
  local caller="${1:-reader}" context_json=""
  if _planveyor_authority_context_carrier_present; then
    _planveyor_authority_parent_context_shape || {
      _planveyor_authority_fail 'caller-local context is invalid'
      return 1
    }
    context_json="$PLANVEYOR_CTX_JSON"
    _planveyor_authority_before_effect_json "$context_json"
    return $?
  fi
  _planveyor_pre_dispatch "$caller"
}

# An explicit workspace launch starts a destination invocation.  Ordinary
# nested readers keep their caller's root; only this named launch boundary
# validates that parent and then captures the explicitly selected workspace.
_planveyor_authority_workspace_launch_context() {
  local caller="${1:-}" workspace_root="${2:-}"
  [[ -n "${caller//[[:space:]]/}" && -n "${workspace_root//[[:space:]]/}" ]] || {
    _planveyor_authority_fail 'workspace launch requires an owner and a destination'
    return 1
  }
  local parent_json="" parent_root=""
  parent_json="$(_planveyor_authority_context_for_reader "$caller")" || return $?
  parent_root="$(_planveyor_authority_context_field "$parent_json" project_root)" || return $?
  local -a runtime_arguments
  if [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]]; then
    runtime_arguments=(--runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY")
  else
    runtime_arguments=(--runtime-root "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT")
  fi
  if [[ -n "${_PLANVEYOR_AUTHORITY_CONTEXT_V1+x}" ]]; then
    # Even a malformed or empty visible assertion must be rejected against A
    # before the explicit destination B may be considered.
    _planveyor_authority_bridge context-validate \
      --context "$_PLANVEYOR_AUTHORITY_CONTEXT_V1" --project-root "$parent_root" \
      "${runtime_arguments[@]}" >/dev/null || return $?
  fi
  if [[ "${workspace_root:A}" == "$parent_root" ]]; then
    print -r -- "$parent_json"
    return 0
  fi
  # This is a process-local removal after parent assertion validation, never a
  # sticky environment change or permission to select a root from transport.
  (
    unset _PLANVEYOR_AUTHORITY_CONTEXT_V1
    _planveyor_authority_bridge context --project-root "${workspace_root:A}" \
      "${runtime_arguments[@]}"
  )
}

# A multi-workspace Desktop launch retains each destination independently.
# Validate a previously captured destination without treating the first local
# destination as an authority selector for every other workspace.
_planveyor_authority_workspace_validate() {
  local workspace_root="${1:-}" context_json="${2:-}"
  [[ -n "${workspace_root//[[:space:]]/}" && -n "${context_json//[[:space:]]/}" ]] || return 1
  _planveyor_authority_source_state_internal || return 1
  local -a runtime_arguments
  if [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]]; then
    runtime_arguments=(--runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY")
  else
    runtime_arguments=(--runtime-root "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT")
  fi
  _planveyor_authority_bridge context-validate --project-root "$workspace_root" \
    --context "$context_json" "${runtime_arguments[@]}" >/dev/null
}

_planveyor_authority_context_json() {
  _planveyor_authority_parent_context_json
}

_planveyor_authority_runtime_root() {
  local context_json=""
  if _planveyor_authority_context_carrier_present; then
    context_json="$(_planveyor_authority_parent_context_json)" || return $?
    _planveyor_authority_context_field "$context_json" runtime_root
    return $?
  fi
  _planveyor_authority_runtime_root_loaded
}

_planveyor_runtime_api_guard() {
  local minimum="${1:-}" maximum="${2:-}" expected_pin="${3:-}"
  [[ "$minimum" == <-> ]] || {
    _planveyor_authority_fail 'minimum runtime API is required'
    return 1
  }
  [[ -n "$maximum" ]] || maximum="$minimum"
  [[ "$maximum" == <-> && "$maximum" -ge "$minimum" ]] || {
    _planveyor_authority_fail 'runtime API range is invalid'
    return 1
  }
  _planveyor_authority_source_state_internal || {
    _planveyor_authority_fail 'loaded source state is invalid'
    return 1
  }
  if [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" != pinned ]]; then
    # A post-source guard cannot promote an unattested legacy source, but it
    # must still enforce the compiled API range without requiring a pin.
    local observed_api=""
    observed_api="$(_planveyor_authority_bridge runtime-api-version 2>/dev/null || true)"
    [[ "$observed_api" == <-> && "$observed_api" -ge "$minimum" && "$observed_api" -le "$maximum" ]] || {
      _planveyor_authority_fail 'loaded runtime API is outside the requested range'
      return 1
    }
    return 0
  fi
  # The pinned command checks the compiled API, supplied pin and requested
  # range together.  A separate version process would repeat the same check.
  _planveyor_authority_bridge runtime-api --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" \
    --minimum "$minimum" --maximum "$maximum" >/dev/null || return $?
  if [[ -n "${expected_pin//[[:space:]]/}" ]]; then
    local observed_pin=""
    observed_pin="$(_planveyor_authority_bridge runtime-field --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" --field pin_sha256 2>/dev/null || true)"
    [[ "$observed_pin" == "$expected_pin" ]] || {
      _planveyor_authority_fail 'loaded runtime pin differs from child expectation'
      return 1
    }
  fi
}

_planveyor_contract_root() {
  local context_json=""
  context_json="$(_planveyor_authority_parent_context_json)" || return $?
  local -a command_args
  command_args=(contract-root --context "$context_json")
  local inherited_root=""
  inherited_root="$(_planveyor_authority_local_context_root_for "$context_json")" || return $?
  command_args+=(--project-root "$inherited_root")
  if [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]]; then
    command_args+=(--runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY")
  else
    command_args+=(--runtime-root "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT")
  fi
  _planveyor_authority_bridge "${command_args[@]}"
}

_planveyor_contract_canonical_relative_path() {
  local relative_path="${1:-}"
  [[ -n "${relative_path//[[:space:]]/}" && "$relative_path" != /* && "$relative_path" != *'/../'* && "$relative_path" != '..' && "$relative_path" != ../* ]] || return 1
  case "$relative_path" in
    docs/tools/prompts/profiles/planveyor/*)
      print -r -- "docs/tools/prompts/${relative_path##*/}"
      ;;
    docs/roles/profiles/planveyor/*)
      print -r -- "docs/roles/${relative_path##*/}"
      ;;
    docs/playbooks/profiles/planveyor/*)
      print -r -- "docs/playbooks/${relative_path##*/}"
      ;;
    *) print -r -- "$relative_path" ;;
  esac
}

_planveyor_contract_path() {
  local relative_path="${1:-}" purpose="${2:-contract}" context_json=""
  relative_path="$(_planveyor_contract_canonical_relative_path "$relative_path")" || return 1
  context_json="$(_planveyor_authority_parent_context_json)" || return $?
  if [[ "${PLANVEYOR_CTX_STATE:-}" == engaged ]]; then
    local -a command_args
    command_args=(contract-path --context "$context_json" --relative-path "$relative_path" --purpose "$purpose")
    local inherited_root=""
    inherited_root="$(_planveyor_authority_local_context_root_for "$context_json")" || return $?
    command_args+=(--project-root "$inherited_root")
    if [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]]; then
      command_args+=(--runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY")
    else
      _planveyor_authority_fail 'engaged authority requires a pinned runtime'
      return 1
    fi
    _planveyor_authority_bridge "${command_args[@]}"
    return $?
  fi
  local contract_root=""
  contract_root="$(_planveyor_contract_root)" || return 1
  print -r -- "${contract_root}/${relative_path}"
}

_planveyor_contract_read() {
  local relative_path="${1:-}" purpose="${2:-contract}" context_json=""
  relative_path="$(_planveyor_contract_canonical_relative_path "$relative_path")" || return 1
  context_json="$(_planveyor_authority_parent_context_json)" || return $?
  if [[ "${PLANVEYOR_CTX_STATE:-}" == engaged ]]; then
    local inherited_root=""
    inherited_root="$(_planveyor_authority_local_context_root_for "$context_json")" || return $?
    _planveyor_authority_bridge contract-read --context "$context_json" \
      --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" \
      --project-root "$inherited_root" \
      --relative-path "$relative_path" --purpose "$purpose"
    return $?
  fi
  local source_path=""
  source_path="$(_planveyor_contract_path "$relative_path" "$purpose")" || return 1
  command cat -- "$source_path"
}

_planveyor_session_authority_resume_validate() {
  local session_key="${1:-}" sid="${2:-}" context_json=""
  [[ -n "${session_key//[[:space:]]/}" && -n "${sid//[[:space:]]/}" ]] || return 1
  context_json="$(_planveyor_authority_parent_context_json)" || {
    _planveyor_authority_fail 'no caller-local authority context for resume'
    return 1
  }
  local -a command_args
  command_args=(receipt-validate --project-root "$PLANVEYOR_CTX_ROOT" --session-key "$session_key" --sid "$sid" --mode "$PLANVEYOR_CTX_STATE")
  [[ "$PLANVEYOR_CTX_STATE" == engaged ]] && command_args+=(--context "$context_json")
  _planveyor_authority_bridge "${command_args[@]}" >/dev/null
}

# Neutral provider adapters.  They retain the public runner names while
# delegating to consumer-installed CLIs in the clean child environment.  No
# account settings, endpoint, key, profile, or shell startup file is read or
# written by this module.

_planveyor_neutral_provider_fail() {
  print -u2 -r -- "planveyor: $*"
  return 1
}

_planveyor_neutral_provider_external_path() {
  emulate -L zsh
  local value="${1:-}" label="${2:-provider path}" runtime_root="${PLANVEYOR_RUNTIME_ROOT:-${PLANVEYOR_ROOT:-}}"
  [[ -n "${value//[[:space:]]/}" && "$value" == /* ]] || {
    _planveyor_neutral_provider_fail "${label} must be an absolute path"
    return 1
  }
  case "$value" in
    *'//'*|*/./*|*/../*|*/.|*/..)
      _planveyor_neutral_provider_fail "${label} must be canonical"
      return 1
      ;;
  esac
  if [[ -n "${runtime_root//[[:space:]]/}" && ( "$value" == "$runtime_root" || "$value" == "$runtime_root"/* ) ]]; then
    _planveyor_neutral_provider_fail "${label} must be outside the Planveyor product tree"
    return 1
  fi
  print -r -- "${value:A}"
}






_planveyor_private_provider_claude_command() {
  emulate -L zsh
  local selected="${PLANVEYOR_CLAUDE_COMMAND:-claude}"
  [[ "$selected" != *[^A-Za-z0-9_./-]* ]] || {
    _planveyor_neutral_provider_fail 'PLANVEYOR_CLAUDE_COMMAND contains unsupported characters'
    return 1
  }
  [[ -n "$selected" ]] || return 1
  print -r -- "$selected"
}

_planveyor_private_provider_claude_configured_model() {
  [[ -n "${PLANVEYOR_CLAUDE_MODEL:-}" ]] && print -r -- "$PLANVEYOR_CLAUDE_MODEL"
}

_planveyor_private_provider_claude_configured_effort() {
  [[ -n "${PLANVEYOR_CLAUDE_EFFORT:-}" ]] && print -r -- "$PLANVEYOR_CLAUDE_EFFORT"
}

_planveyor_private_provider_provenance() {
  print -r -- 'direct_child'
}

_planveyor_private_provider_claude_direct_run() {
  emulate -L zsh
  local executable="" model="" effort=""
  executable="$(_planveyor_private_provider_claude_command)" || return $?
  if [[ "$executable" == /* ]]; then
    [[ -x "$executable" ]] || {
      _planveyor_neutral_provider_fail "Claude executable is unavailable: ${executable}"
      return 127
    }
  else
    command -v "$executable" >/dev/null 2>&1 || {
      _planveyor_neutral_provider_fail 'Claude CLI is unavailable; configure the consumer provider first'
      return 127
    }
  fi
  model="$(_planveyor_private_provider_claude_configured_model)"
  effort="$(_planveyor_private_provider_claude_configured_effort)"
  local -a claude_args
  claude_args=()
  [[ -n "${model//[[:space:]]/}" ]] && claude_args+=(--model "$model")
  [[ -n "${effort//[[:space:]]/}" ]] && claude_args+=(--effort "$effort")
  command "$executable" "${claude_args[@]}" "$@"
}

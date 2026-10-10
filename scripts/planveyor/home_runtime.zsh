# Consumer-owned Codex-home adapter.
#
# Planveyor deliberately neither installs dotfiles nor manufactures a profile.
# The normal Codex CLI keeps its consumer-owned default at ~/.codex; an
# operator may select a separate external directory with PLANVEYOR_CODEX_HOME.

_planveyor_neutral_home_fail() {
  print -u2 -r -- "planveyor: $*"
  return 1
}

_planveyor_neutral_external_path() {
  emulate -L zsh
  local value="${1:-}" label="${2:-path}" runtime_root="${PLANVEYOR_RUNTIME_ROOT:-${PLANVEYOR_ROOT:-}}"
  [[ -n "${value//[[:space:]]/}" && "$value" == /* ]] || {
    _planveyor_neutral_home_fail "${label} must be an absolute path"
    return 1
  }
  case "$value" in
    *'//'*|*/./*|*/../*|*/.|*/..)
      _planveyor_neutral_home_fail "${label} must be canonical"
      return 1
      ;;
  esac
  if [[ -n "${runtime_root//[[:space:]]/}" && ( "$value" == "$runtime_root" || "$value" == "$runtime_root"/* ) ]]; then
    _planveyor_neutral_home_fail "${label} must be outside the Planveyor product tree"
    return 1
  fi
  print -r -- "${value:A}"
}

_planveyor_private_home_codex_home() {
  emulate -L zsh
  local selected="${PLANVEYOR_CODEX_HOME:-${HOME:-}/.codex}"
  _planveyor_neutral_external_path "$selected" 'Codex home'
}

_planveyor_private_home_codex_home_ensure() {
  emulate -L zsh
  local selected="${1:-$(_planveyor_private_home_codex_home 2>/dev/null || true)}"
  selected="$(_planveyor_neutral_external_path "$selected" 'Codex home')" || return $?
  whence -p codex >/dev/null 2>&1 || {
    _planveyor_neutral_home_fail 'Codex CLI is required; install it and authenticate in the consumer-owned home first'
    return 127
  }
  print -r -- "$selected"
}

_planveyor_private_home_codex_config_ensure_multi_agent_v2_routing() {
  emulate -L zsh
  # This historical "ensure" entrypoint is intentionally non-mutating.  The
  # selected Codex config belongs to the consumer and is never rewritten by
  # Planveyor.
  _planveyor_private_home_codex_home_ensure >/dev/null || return $?
  print -u2 -r -- 'planveyor: using consumer-owned Codex configuration without rewriting it'
}

_planveyor_private_home_default_codex_profile_for_role_mode() {
  # Retain the wrapper contract while selecting the ordinary consumer CLI.
  # A role-specific profile is an operator choice, not a product default.
  return 0
}

_planveyor_private_home_expected_model_for_profile() {
  [[ -n "${PLANVEYOR_CODEX_MODEL:-}" ]] && print -r -- "$PLANVEYOR_CODEX_MODEL"
}

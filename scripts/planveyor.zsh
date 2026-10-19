# This bootstrap must stay before every normal facade assignment or function
# definition.  It records the *actual* source path, rejects an exported/fake
# loaded-pin state, and refuses a conflicting re-source before it can replace a
# function from the original facade.
_PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED=0
if [[ ${(t)PLANVEYOR_SOURCE_SEAL-} == scalar-local-readonly &&
      "${PLANVEYOR_SOURCE_SEAL:-}" == planveyor-source-buffer.v1 &&
      ${(t)PLANVEYOR_SOURCE_PATH-} == scalar-local-readonly &&
      ${(t)PLANVEYOR_SOURCE_DESCRIPTOR-} == scalar-local-readonly &&
      ${(t)PLANVEYOR_SOURCE_RUNTIME_PIN-} == scalar-local-readonly &&
      ${(t)PLANVEYOR_SOURCE_PYTHON-} == scalar-local-readonly &&
      ${(t)PLANVEYOR_SOURCE_BOOTSTRAP-} == scalar-local-readonly &&
      ${funcstack[(Ie)planveyor_source_runtime]} -gt 0 ]]; then
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED=1
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH="$PLANVEYOR_SOURCE_PATH"
else
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH="${${(%):-%N}:A}"
fi
_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_ROOT="${_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH:h:h}"
_PLANVEYOR_AUTHORITY_BOOTSTRAP_RUNTIME_ROOT="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_ROOT"
_PLANVEYOR_AUTHORITY_BOOTSTRAP_COMPATIBILITY_FACADE=0
if [[ "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH" != "${_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_ROOT}/scripts/planveyor.zsh" ]]; then
  print -u2 -r -- 'planveyor authority: source path is not the canonical facade path'
  return 1
fi

if [[ -z "${_PLANVEYOR_AUTHORITY_SOURCE_STATE+x}" && -n "${_PLANVEYOR_AUTHORITY_PYTHON_BIN+x}" ]]; then
  print -u2 -r -- 'planveyor authority: preseeded interpreter state is rejected'
  return 1
fi
if [[ -z "${_PLANVEYOR_AUTHORITY_SOURCE_STATE+x}" && -n "${_PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL+x}" ]]; then
  print -u2 -r -- 'planveyor authority: preseeded loader literal is rejected'
  return 1
fi
if [[ -z "${_PLANVEYOR_AUTHORITY_SOURCE_STATE+x}" && (
      -n "${_PLANVEYOR_AUTHORITY_SOURCE_PATH+x}" || -n "${_PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR+x}" ||
      -n "${_PLANVEYOR_AUTHORITY_RUNTIME_ROOT+x}" || -n "${_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY+x}" ) ]]; then
  print -u2 -r -- 'planveyor authority: preseeded source carrier is rejected'
  return 1
fi
_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON=""
if [[ -n "${_PLANVEYOR_AUTHORITY_SOURCE_STATE+x}" ]]; then
  if [[ ${(t)_PLANVEYOR_AUTHORITY_SOURCE_STATE-} != scalar-readonly ]]; then
    print -u2 -r -- 'planveyor authority: exported or mutable loaded source state is rejected'
    return 1
  fi
  if [[ ${(t)_PLANVEYOR_AUTHORITY_PYTHON_BIN-} != scalar-readonly || ! -x "${_PLANVEYOR_AUTHORITY_PYTHON_BIN:-}" ]]; then
    print -u2 -r -- 'planveyor authority: loaded interpreter state is invalid'
    return 1
  fi
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON="$_PLANVEYOR_AUTHORITY_PYTHON_BIN"
elif (( _PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED )); then
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON="$PLANVEYOR_SOURCE_PYTHON"
else
for _PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON_CANDIDATE in \
  "$(command -v python3 2>/dev/null || true)" \
  "$(command -v python 2>/dev/null || true)" \
  "$(command -v python3.12 2>/dev/null || true)" \
  "$(command -v python3.11 2>/dev/null || true)" \
  "$(command -v python3.10 2>/dev/null || true)"; do
  [[ -n "${_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON_CANDIDATE//[[:space:]]/}" && -x "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON_CANDIDATE" ]] || continue
  "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON_CANDIDATE" -B -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)' >/dev/null 2>&1 || continue
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON="${_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON_CANDIDATE:A}"
  break
done
fi
unset _PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON_CANDIDATE
if [[ -z "${_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON//[[:space:]]/}" ]]; then
  print -u2 -r -- 'planveyor authority: Python 3.10, 3.11, or 3.12 is required for source identity'
  return 1
fi

if [[ -n "${_PLANVEYOR_AUTHORITY_SOURCE_STATE+x}" ]]; then
  if [[ ${(t)_PLANVEYOR_AUTHORITY_SOURCE_STATE-} != scalar-readonly ]]; then
    print -u2 -r -- 'planveyor authority: exported or mutable loaded source state is rejected'
    return 1
  fi
  for _PLANVEYOR_AUTHORITY_BOOTSTRAP_STATE_NAME in \
    _PLANVEYOR_AUTHORITY_SOURCE_PATH \
    _PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR \
    _PLANVEYOR_AUTHORITY_RUNTIME_ROOT \
    _PLANVEYOR_AUTHORITY_PYTHON_BIN; do
    if [[ ${(tP)_PLANVEYOR_AUTHORITY_BOOTSTRAP_STATE_NAME-} != scalar-readonly ]]; then
      print -u2 -r -- 'planveyor authority: loaded source state is incomplete'
      return 1
    fi
  done
  unset _PLANVEYOR_AUTHORITY_BOOTSTRAP_STATE_NAME
  if [[ "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH" != "${_PLANVEYOR_AUTHORITY_SOURCE_PATH:-}" ]]; then
    print -u2 -r -- 'planveyor authority: a different source root or revision is already loaded'
    return 1
  fi
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE="${_PLANVEYOR_AUTHORITY_RUNTIME_ROOT}/scripts/contract_authority_bridge.py"
  if [[ ! -f "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE" || -L "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE" ]]; then
    print -u2 -r -- 'planveyor authority: loaded source bridge is unavailable'
    return 1
  fi
  if [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]] && (( ! _PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED )); then
    print -u2 -r -- 'planveyor authority: pinned re-source requires planveyor_source_runtime'
    return 1
  fi
  if (( _PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED )); then
    "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON" -I -B -c "$PLANVEYOR_SOURCE_BOOTSTRAP" "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE" source-verify \
      --path "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH" \
      --runtime-root "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT" \
      --descriptor "$_PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR" >/dev/null || return $?
  else
    "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON" -B "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE" source-verify \
    --path "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH" \
    --runtime-root "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT" \
    --descriptor "$_PLANVEYOR_AUTHORITY_SOURCE_DESCRIPTOR" >/dev/null || return $?
  fi
  case "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" in
    pinned)
      if [[ ${(t)_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY-} != scalar-readonly ]]; then
        print -u2 -r -- 'planveyor authority: loaded runtime pin is incomplete'
        return 1
      fi
      if [[ ${(t)_PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL-} != scalar-readonly ]]; then
        print -u2 -r -- 'planveyor authority: loaded source literal is incomplete'
        return 1
      fi
      [[ "$PLANVEYOR_SOURCE_RUNTIME_PIN" == "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" ]] || {
        print -u2 -r -- 'planveyor authority: re-source runtime pin differs'
        return 1
      }
      "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON" -I -B -c "$PLANVEYOR_SOURCE_BOOTSTRAP" "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE" runtime-verify \
        --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" >/dev/null || return $?
      ;;
    unattested_legacy) ;;
    *)
      print -u2 -r -- 'planveyor authority: loaded source state is invalid'
      return 1
      ;;
  esac
  unset _PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED _PLANVEYOR_AUTHORITY_BOOTSTRAP_RUNTIME_ROOT \
    _PLANVEYOR_AUTHORITY_BOOTSTRAP_COMPATIBILITY_FACADE \
    _PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH _PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_ROOT \
    _PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON _PLANVEYOR_AUTHORITY_BOOTSTRAP_DECLARATION \
    _PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE
  return 0
fi

_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE="${_PLANVEYOR_AUTHORITY_BOOTSTRAP_RUNTIME_ROOT}/scripts/contract_authority_bridge.py"
if [[ ! -f "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE" || -L "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE" ]]; then
  print -u2 -r -- 'planveyor authority: candidate bridge is unavailable'
  return 1
fi
if (( _PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED )); then
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_DESCRIPTOR="$PLANVEYOR_SOURCE_DESCRIPTOR"
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_PIN_SUMMARY="$PLANVEYOR_SOURCE_RUNTIME_PIN"
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_STATE='pinned'
else
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_DESCRIPTOR="$("$_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON" -B "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE" source-descriptor \
    --path "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH" \
    --runtime-root "$_PLANVEYOR_AUTHORITY_BOOTSTRAP_RUNTIME_ROOT")" || return $?
  # A path read after raw source began cannot attest already selected bytes.
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_STATE='unattested_legacy'
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_PIN_SUMMARY=''
fi
typeset +x _PLANVEYOR_AUTHORITY_BOOT_SOURCE_STATE _PLANVEYOR_AUTHORITY_BOOT_SOURCE_PATH \
  _PLANVEYOR_AUTHORITY_BOOT_SOURCE_DESCRIPTOR _PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT \
  _PLANVEYOR_AUTHORITY_BOOT_RUNTIME_PIN_SUMMARY _PLANVEYOR_AUTHORITY_BOOT_PYTHON_BIN 2>/dev/null || true
typeset -g _PLANVEYOR_AUTHORITY_BOOT_SOURCE_STATE="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_STATE"
typeset -g _PLANVEYOR_AUTHORITY_BOOT_SOURCE_PATH="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH"
typeset -g _PLANVEYOR_AUTHORITY_BOOT_SOURCE_DESCRIPTOR="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_DESCRIPTOR"
typeset -g _PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_RUNTIME_ROOT"
typeset -g _PLANVEYOR_AUTHORITY_BOOT_RUNTIME_PIN_SUMMARY="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_PIN_SUMMARY"
typeset -g _PLANVEYOR_AUTHORITY_BOOT_PYTHON_BIN="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON"
if (( _PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED )); then
  _planveyor_caller_source_buffer scripts/planveyor/contract_authority.zsh
else
  source "${_PLANVEYOR_AUTHORITY_BOOTSTRAP_RUNTIME_ROOT}/scripts/planveyor/contract_authority.zsh"
fi
if (( $? != 0 )); then
  unset _PLANVEYOR_AUTHORITY_BOOT_SOURCE_STATE _PLANVEYOR_AUTHORITY_BOOT_SOURCE_PATH \
    _PLANVEYOR_AUTHORITY_BOOT_SOURCE_DESCRIPTOR _PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT \
    _PLANVEYOR_AUTHORITY_BOOT_RUNTIME_PIN_SUMMARY _PLANVEYOR_AUTHORITY_BOOT_PYTHON_BIN
  return 1
fi
typeset -g _PLANVEYOR_THIS_SCRIPT_PATH="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH"
unset _PLANVEYOR_AUTHORITY_BOOTSTRAP_ANCHORED \
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_PATH _PLANVEYOR_AUTHORITY_BOOTSTRAP_CANDIDATE_ROOT \
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_RUNTIME_ROOT _PLANVEYOR_AUTHORITY_BOOTSTRAP_COMPATIBILITY_FACADE \
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_COMPATIBILITY_ROOT \
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_PYTHON _PLANVEYOR_AUTHORITY_BOOTSTRAP_DECLARATION \
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_BRIDGE _PLANVEYOR_AUTHORITY_BOOTSTRAP_DESCRIPTOR \
  _PLANVEYOR_AUTHORITY_BOOTSTRAP_PIN_SUMMARY _PLANVEYOR_AUTHORITY_BOOTSTRAP_STATE

_planveyor_main_root() {
  # Resolve the "main worktree" path for the current git repo.
  #
  # Priority:
  # 1) PLANVEYOR_MAIN_ROOT (explicit override)
  # 2) `git worktree list --porcelain` entry for branch refs/heads/main
  # 3) current worktree root
  local override="${PLANVEYOR_MAIN_ROOT:-}"
  if [[ -n "${override//[[:space:]]/}" ]]; then
    echo "${override}"
    return 0
  fi

  local root="$(_planveyor_project_root)" || return $?
  git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "$root"
    return 0
  }

  local out=""
  out="$(git -C "$root" worktree list --porcelain 2>/dev/null || true)"
  if [[ -z "${out//[[:space:]]/}" ]]; then
    echo "$root"
    return 0
  fi

  local wt_path=""
  local line=""
  for line in "${(@f)out}"; do
    if [[ "$line" == worktree\ * ]]; then
      wt_path="${line#worktree }"
      continue
    fi
    if [[ "$line" == branch\ refs/heads/main ]]; then
      [[ -n "${wt_path//[[:space:]]/}" ]] && echo "$wt_path" && return 0
    fi
  done

  echo "$root"
}
_planveyor_root() {
  # Runtime script/module resolution is anchored to the loaded facade. It is
  # never selected from an ambient product-root variable or a HOME fallback.
  if _planveyor_authority_source_state_internal 2>/dev/null && [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == pinned ]]; then
    print -r -- "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT"
    return 0
  fi
  if [[ -n "${_PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT:-}" && -d "$_PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT" && -f "$_PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT/scripts/planveyor.zsh" ]]; then
    print -r -- "${_PLANVEYOR_AUTHORITY_BOOT_RUNTIME_ROOT:A}"
    return 0
  fi

  local loaded_root=""
  loaded_root="$(_planveyor_root_from_loaded_script 2>/dev/null || true)"
  if [[ -n "${loaded_root//[[:space:]]/}" && -d "$loaded_root" && -f "$loaded_root/scripts/planveyor.zsh" ]]; then
    print -r -- "${loaded_root:A}"
    return 0
  fi
  return 1
}

_planveyor_project_root() {
  # The runtime root and the selected consumer project are separate values.
  # Do not read PLANVEYOR_PROJECT_ROOT here: child transport is deliberately
  # ambient-free, and every consumer artifact must remain bound to the
  # authority context captured for this invocation.
  local context_json="" context_tuple=""
  context_json="$(_planveyor_authority_context_for_reader _planveyor_project_root)" || return $?
  context_tuple="$(_planveyor_authority_context_bindings "$context_json")" || return $?
  local context_state="" context_root="" context_generation="" remainder=""
  IFS=$'\t' read -r context_state context_root context_generation remainder <<< "$context_tuple" || return 1
  [[ -z "${remainder:-}" && ( "$context_state" == legacy || "$context_state" == engaged ) && -n "${context_root//[[:space:]]/}" && "$context_root" == /* && -d "$context_root" && ${#context_generation} -eq 64 && "$context_generation" != *[^0-9A-Fa-f]* ]] || return 1
  print -r -- "$context_root"
}

_planveyor_loaded_script_path() {
  if [[ -n "${_PLANVEYOR_THIS_SCRIPT_PATH:-}" ]]; then
    echo "${_PLANVEYOR_THIS_SCRIPT_PATH}"
    return 0
  fi

  local source_path="${functions_source[_planveyor_root]:-${functions_source[planveyor_bare_entrypoints_install]:-}}"
  [[ -n "${source_path//[[:space:]]/}" ]] || return 1
  echo "${source_path:A}"
}
_planveyor_root_from_loaded_script() {
  local script_path=""
  script_path="$(_planveyor_loaded_script_path 2>/dev/null || true)"
  [[ -n "${script_path//[[:space:]]/}" ]] || return 1
  echo "${script_path:h:h}"
}
_planveyor_closeout_tooling_root() {
  local loaded_root=""
  loaded_root="$(_planveyor_root_from_loaded_script 2>/dev/null || true)"
  [[ -n "${loaded_root//[[:space:]]/}" ]] || return 1
  [[ -f "${loaded_root}/scripts/planveyor.zsh" ]] || return 1
  [[ -f "${loaded_root}/scripts/plan_lint.py" ]] || return 1
  [[ -f "${loaded_root}/scripts/plan_status_oracle.py" ]] || return 1
  [[ -f "${loaded_root}/scripts/fs_object_identity.py" ]] || return 1
  [[ -f "${loaded_root}/scripts/review_target_snapshot.py" ]] || return 1
  [[ -f "${loaded_root}/scripts/docs_closeout.py" ]] || return 1
  echo "$loaded_root"
}
_planveyor_module_root() {
  local script_path=""
  script_path="$(_planveyor_loaded_script_path 2>/dev/null || true)"
  [[ -n "${script_path//[[:space:]]/}" ]] || script_path="${_PLANVEYOR_THIS_SCRIPT_PATH:-}"
  local -a candidates
  candidates=()
  if [[ -n "${script_path//[[:space:]]/}" ]]; then
    candidates+=("${script_path:h}/planveyor")
  fi
  candidates+=("$(_planveyor_root)/scripts/planveyor")

  local candidate_dir=""
  local -A seen_dirs
  for candidate_dir in "${candidates[@]}"; do
    [[ -n "${candidate_dir//[[:space:]]/}" ]] || continue
    [[ -n "${seen_dirs[$candidate_dir]:-}" ]] && continue
    seen_dirs[$candidate_dir]=1
    [[ -d "${candidate_dir}" ]] || continue
    echo "${candidate_dir}"
    return 0
  done
  return 1
}
_planveyor_source_module() {
  local module_name="${1:-}"
  [[ -n "${module_name//[[:space:]]/}" ]] || return 1

  local module_root=""
  module_root="$(_planveyor_module_root 2>/dev/null || true)"
  [[ -n "${module_root//[[:space:]]/}" ]] || {
    echo "Missing planveyor module root for ${module_name}" >&2
    return 1
  }

  local module_path="${module_root}/${module_name}"
  [[ -f "${module_path}" ]] || {
    echo "Missing planveyor module: ${module_path}" >&2
    return 1
  }

  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-${_PLANVEYOR_AUTHORITY_BOOT_SOURCE_STATE:-}}" == pinned ]]; then
    _planveyor_caller_source_buffer "scripts/planveyor/${module_name}"
  else
    source "${module_path}"
  fi
}

_planveyor_private_family_load() {
  local family="${1:-}" context_json="" relative_path=""
  case "$family" in
    provider|provider-provenance) relative_path=scripts/planveyor/provider_runtime.zsh ;;
    *) _planveyor_authority_fail 'unknown private family'; return 1 ;;
  esac
  context_json="$(_planveyor_authority_context_for_reader _planveyor_private_family_load)" || return $?
  _planveyor_authority_before_effect_json "$context_json" >/dev/null || return $?
  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == pinned ]]; then
    _planveyor_caller_source_buffer "$relative_path"
  else
    local runtime_root=""
    runtime_root="$(_planveyor_authority_runtime_root_loaded)" || return $?
    source "${runtime_root}/${relative_path}"
  fi
}
_planveyor_prompts_root() { echo "$(_planveyor_root)/docs/tools/prompts"; }
_planveyor_playbooks_root() { echo "$(_planveyor_root)/docs/playbooks"; }
_planveyor_script() {
  local name="${1:-}"
  [[ -n "${name//[[:space:]]/}" ]] || return 1
  echo "$(_planveyor_root)/scripts/${name}"
}
_planveyor_docs_index_db_default() {
  local root="$(_planveyor_project_root)" || return $?
  echo "${root}/.tmp/planveyor_docs_index.sqlite"
}
_planveyor_docs_archive_db_default() {
  # Central, append-only docs archive DB (prefer keeping it in the main worktree).
  #
  # Override with PLANVEYOR_DOCS_ARCHIVE_DB for experiments/migration.
  if [[ -n "${PLANVEYOR_DOCS_ARCHIVE_DB:-}" ]]; then
    echo "${PLANVEYOR_DOCS_ARCHIVE_DB}"
    return 0
  fi
  local main_root="$(_planveyor_main_root)"
  echo "${main_root}/.tmp/planveyor_docs_archive.sqlite"
}
_planveyor_worktree_id() {
  # Returns worktree name if we're inside a git-worktree, else empty.
  local root="$(_planveyor_project_root)" || return $?
  local git_dir=""
  # In git worktrees, `--git-dir` often returns just ".git" (a file pointing to
  # the real dir). Use absolute git dir to reliably detect worktree id.
  git_dir="$(git -C "$root" rev-parse --absolute-git-dir 2>/dev/null || true)"
  [[ -n "${git_dir//[[:space:]]/}" ]] || return 1
  case "$git_dir" in
    */.git/worktrees/*) echo "${git_dir##*/}" ;;
    *) return 1 ;;
  esac
}

_planveyor_codex_home() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_codex_home)" || return $?
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
  _planveyor_source_module home_runtime.zsh || return $?
  _planveyor_private_home_codex_home "$@"
}

# Compatibility alias for callers outside this repository.
_planveyor_codex_config_ensure_multi_agent_v2_routing() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_codex_config_ensure_multi_agent_v2_routing)" || return $?
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
  _planveyor_source_module home_runtime.zsh || return $?
  _planveyor_private_home_codex_config_ensure_multi_agent_v2_routing "$@"
}

_planveyor_codex_home_ensure() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_codex_home_ensure)" || return $?
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
  _planveyor_source_module home_runtime.zsh || return $?
  _planveyor_private_home_codex_home_ensure "$@"
}

_planveyor_codex() {
  local -x PLANVEYOR_LEGACY_PROFILE="${PLANVEYOR_LEGACY_PROFILE:-}"
  # The clean child deliberately ignores inherited CODEX_HOME.  The neutral
  # adapter selects either explicit PLANVEYOR_CODEX_HOME or the consumer's
  # ordinary ~/.codex without creating or rewriting either location.
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_codex)" || return $?
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
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  local codex_home=""
  codex_home="$(_planveyor_codex_home 2>/dev/null || true)"
  if [[ -n "${codex_home//[[:space:]]/}" ]]; then
    _planveyor_codex_home_ensure "$codex_home" || return 1
    CODEX_HOME="$codex_home" command codex "$@"
    return $?
  fi
  command codex "$@"
}










# Stable neutral Claude readers are defined in the facade, not in the lazily
# loaded provider module.  Session and role code may read their configured
# values before the first provider launch; every such read therefore remains
# bound to the same authority context as the eventual direct-child execution.
_planveyor_claude_command() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_claude_command)" || return $?
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
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  _planveyor_private_family_load provider || return $?
  _planveyor_private_provider_claude_command "$@"
}

_planveyor_claude_configured_model() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_claude_configured_model)" || return $?
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
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  _planveyor_private_family_load provider || return $?
  _planveyor_private_provider_claude_configured_model "$@"
}

_planveyor_claude_configured_effort() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_claude_configured_effort)" || return $?
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
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  _planveyor_private_family_load provider || return $?
  _planveyor_private_provider_claude_configured_effort "$@"
}

_planveyor_provider_provenance() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_provider_provenance)" || return $?
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
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  _planveyor_private_family_load provider || return $?
  _planveyor_private_provider_provenance "$@"
}

# This public facade keeps direct Claude launches behind the same authority
# boundary as the other provider helpers.  The adapter is intentionally lazy:
# it reads only explicit consumer inputs and never loads a login shell.
_planveyor_claude_direct_run() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_claude_direct_run)" || return $?
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
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  _planveyor_private_family_load provider || return $?
  _planveyor_private_provider_claude_direct_run "$@"
}

_planveyor_is_repo_context() {
  # Guard: apply planveyor codex wrapper only inside planveyor repo/worktrees.
  local root=""
  root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "${root//[[:space:]]/}" ]] || return 1
  [[ -f "${root}/AGENTS.md" && -f "${root}/scripts/planveyor.zsh" ]]
}

codex() {
  # Manual escape hatch for one-off passthrough runs.
  if [[ "${PLANVEYOR_CODEX_PASSTHROUGH:-0}" == "1" ]]; then
    command codex "$@"
    return $?
  fi

  if _planveyor_is_repo_context; then
    _planveyor_codex "$@"
    return $?
  fi

  command codex "$@"
}

_planveyor_codex_home_effective() {
  local codex_home=""
  codex_home="$(_planveyor_codex_home 2>/dev/null || true)"
  if [[ -n "${codex_home//[[:space:]]/}" ]]; then
    print -r -- "${codex_home}"
    return 0
  fi
  return 1
}











_planveyor_current_branch() {
  # Returns the current branch name for this worktree (or "HEAD" if detached).
  local root="$(_planveyor_project_root)" || return 1
  git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || true
}
_planveyor_last_line() {
  # NOTE: do NOT use variable name `path` in zsh (it shadows $path/command lookup).
  local file_path="$1"
  [[ -f "$file_path" ]] || return 1
  local last=""
  local line=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -n "${line//[[:space:]]/}" ]] && last="$line"
  done < "$file_path"
  [[ -n "$last" ]] || return 1
  echo "$last"
}
_planveyor_read() {
  # NOTE: do NOT use variable name `path` in zsh (it shadows $path/command lookup).
  local file_path="$1"
  [[ -f "$file_path" ]] || { echo "Missing file: $file_path" >&2; return 1; }
  local v
  v="$(_planveyor_last_line "$file_path")" || { echo "Empty file: $file_path" >&2; return 1; }
  [[ -n "$v" ]] || { echo "Empty file: $file_path" >&2; return 1; }
  echo "$v"
}

planveyor_planpath() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_planpath)" || return $?
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
  local planpath_file="${root}/.planveyor.planpath"
  if [[ ! -e "$planpath_file" && ! -L "$planpath_file" ]]; then
    echo "No selected plan. Select an existing plan with:" >&2
    echo "planveyor_plan_set <PLAN_PATH>" >&2
    return 1
  fi
  _planveyor_read "$planpath_file"
}

planveyor_session() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_session)" || return $?
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
  _planveyor_read "$root/.planveyor.session.$1";
}

planveyor_pybin_file() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_pybin_file)" || return $?
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
  _planveyor_authority_python
}

planveyor_runner_file() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_runner_file)" || return $?
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
  _planveyor_read "$root/.planveyor.runner.$1";
}

planveyor_range_base() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_range_base)" || return $?
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
  _planveyor_read "$root/.planveyor.range.base";
}

planveyor_range_head() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_range_head)" || return $?
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
  _planveyor_read "$root/.planveyor.range.head";
}

planveyor_range_merge() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_range_merge)" || return $?
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
  _planveyor_read "$root/.planveyor.range.merge";
}

_planveyor_now() { date "+%d.%m.%Y %H:%M:%S %z"; }
_planveyor_dt_short() {
  # Best-effort short datetime formatter.
  # Numeric offsets, ISO8601 and legacy Moscow stamps -> local "DD.MM HH:MM".
  # Unmarked historical stamps retain the old writer's +03:00 meaning.
  # If format is unknown, returns input as-is.
  local v="$1"
  v="${v//$'\r'/}"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  [[ -n "${v//[[:space:]]/}" ]] || { echo ""; return 0; }

  # Normalize zone variants for BSD `date -f ... %z`.
  local iso="$v"
  [[ "$iso" == *" MSK" ]] && iso="${iso% MSK} +0300"
  [[ "$iso" == *" (Europe/Moscow)" ]] && iso="${iso% (Europe/Moscow)} +0300"
  [[ "$iso" == *"Z" ]] && iso="${iso%Z}+0000"
  iso="${iso/T/ }"
  iso="$(echo "$iso" | sed -E 's/([+-][0-9]{2}):([0-9]{2})$/\1\2/; s/([0-9])([+-][0-9]{4})$/\1 \2/')"
  if [[ "$iso" =~ '^([0-9]{2}\.[0-9]{2}\.[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})[[:space:]][0-9]{2}:[0-9]{2}(:[0-9]{2})?$' ]]; then
    iso="${iso} +0300"
  fi

  local out="" format=""
  for format in "%d.%m.%Y %H:%M:%S %z" "%d.%m.%Y %H:%M %z" "%Y-%m-%d %H:%M:%S %z" "%Y-%m-%d %H:%M %z"; do
    out="$(command date -j -f "$format" "$iso" "+%d.%m %H:%M" 2>/dev/null || true)"
    [[ -n "${out//[[:space:]]/}" ]] && { echo "$out"; return 0; }
  done

  echo "$v"
}
_planveyor_normalize_role_id() {
  local v="${1//[[:space:]]/}"
  v="${v:l}"
  case "$v" in
    architect|arch|a) echo "architect" ;;
    coder|code|c) echo "coder" ;;
    planner|plan|p) echo "planner" ;;
    reviewer|review|rev|r) echo "reviewer" ;;
    manager|mngr|mgr|m) echo "manager" ;;
    *) return 1 ;;
  esac
}

_planveyor_normalize_session_key() {
  # Like role_id, but also supports Architect track session keys.
  local v="${1//[[:space:]]/}"
  v="${v:l}"
  case "$v" in
    architect|arch|a) echo "architect" ;;
    coder|code|c) echo "coder" ;;
    planner|plan|p) echo "planner" ;;
    reviewer|review|rev|r) echo "reviewer" ;;
    reviewer_code_risk|reviewer-risk|reviewer_risk|review_risk|risk_reviewer|risk)
      echo "reviewer_code_risk"
      ;;
    reviewer_code_contracts|reviewer-contracts|reviewer_contracts|review_contracts|contracts_reviewer|contracts)
      echo "reviewer_code_contracts"
      ;;
    manager|mngr|mgr|m) echo "manager" ;;

    architect_process_roles|arch_process_roles|process_roles|roles)
      echo "architect_process_roles"
      ;;
    architect_process_collab|arch_process_collab|process_collab|collab)
      echo "architect_process_collab"
      ;;
    architect_innovations|arch_innovations|innovations|innovation|research)
      echo "architect_innovations"
      ;;

    *) return 1 ;;
  esac
}

_planveyor_bare_entrypoints_stage1_operator_commands() {
  print -l -- \
    planveyor_ai_gate \
    planveyor_ai_gate_smoke \
    planveyor_plan_set \
    planveyor_owner_answers_set \
    planveyor_manager_collab_cmd \
    planveyor_manager_custom_pipeline_cmd
}

_planveyor_bare_entrypoints_manager_tui_commands() {
  print -l -- \
    planveyor_manager_collab_tui \
    planveyor_manager_custom_pipeline_tui
}

_planveyor_bare_entrypoints_helper_commands() {
  print -l -- \
    planveyor_plan_bundle \
    planveyor_plan_closeout_preflight \
    planveyor_docs_closeout \
    planveyor_role_runner_preflight \
    planveyor_custom_role_step \
    planveyor_analysis_init \
    planveyor_docs_index_build \
    planveyor_collab_state_write_alive \
    planveyor_decomposition_seed_promote \
    planveyor_review_range_init \
    planveyor_review_target_snapshot \
    planveyor_range_set \
    planveyor_range_set_merge \
    planveyor_range_set_auto_merge \
    planveyor_range_base \
    planveyor_range_head \
    planveyor_range_merge \
    planveyor_role_run_probe \
    planveyor_merge_range_stats_json \
    planveyor_merge_tracker_ensure \
    planveyor_q_next_json \
    planveyor_q_append \
    planveyor_q_small_slice_json \
    planveyor_q_advance_json \
    planveyor_q_closeout_json \
    planveyor_q_stop_json \
    planveyor_q_planpath_override_json \
    planveyor_q_history_json \
    planveyor_q_final_report \
    planveyor_planqueue_metrics \
    planveyor_planqueue_metrics_json \
    planveyor_planning_wave_readback \
    planveyor_planning_wave_readback_json \
    planveyor_wave_telemetry_report \
    planveyor_wave_telemetry_report_json \
    planveyor_rollout_packet_create \
    planveyor_rollout_packet_show \
    planveyor_rollout_packet_import_instructions \
    planveyor_rollout_packet_lint \
    planveyor_rollout_packet_ack \
    planveyor_rollout_packet_query \
    planveyor_rollout_packet_reconcile \
    planveyor_rollout_packet_outcome_set \
    planveyor_post_merge_packetization_gate_recover \
    planveyor_upstream_request_show \
    planveyor_upstream_request_import \
    planveyor_upstream_request_ack \
    planveyor_upstream_request_query \
    planveyor_bare_entrypoints_install \
    planveyor_bare_entrypoints_doctor
}

_planveyor_bare_entrypoints_docs_hygiene_commands() {
  print -l -- \
    planveyor_docs_hygiene_list \
    planveyor_docs_hygiene_suggest \
    planveyor_docs_hygiene_archive \
    planveyor_followups_apply
}

_planveyor_bare_entrypoints_role_main_commands() {
  print -l -- \
    planveyor_arch \
    planveyor_planner \
    planveyor_coder \
    planveyor_reviewer \
    planveyor_reviewer_code_risk \
    planveyor_reviewer_code_contracts \
    planveyor_manager
}

_planveyor_bare_entrypoints_role_transition_commands() {
  print -l -- \
    planveyor_arch_initial \
    planveyor_arch_censor \
    planveyor_planner_censor \
    planveyor_coder_censor
}

_planveyor_bare_entrypoints_role_resume_commands() {
  print -l -- \
    planveyor_arch_resume \
    planveyor_planner_resume \
    planveyor_coder_resume \
    planveyor_reviewer_resume \
    planveyor_reviewer_code_risk_resume \
    planveyor_reviewer_code_contracts_resume \
    planveyor_manager_resume
}

_planveyor_bare_entrypoints_arch_track_commands() {
  print -l -- \
    planveyor_arch_process_roles_tui \
    planveyor_arch_process_collab_tui \
    planveyor_arch_innovations_tui \
    planveyor_arch_roles_resume \
    planveyor_arch_collab_resume \
    planveyor_arch_inno_resume
}

_planveyor_bare_entrypoints_managed_commands() {
  local -a managed_cmds
  managed_cmds=(
    "${(@f)$(_planveyor_bare_entrypoints_stage1_operator_commands)}"
    "${(@f)$(_planveyor_bare_entrypoints_manager_tui_commands)}"
    "${(@f)$(_planveyor_bare_entrypoints_helper_commands)}"
    "${(@f)$(_planveyor_bare_entrypoints_docs_hygiene_commands)}"
    "${(@f)$(_planveyor_bare_entrypoints_role_main_commands)}"
    "${(@f)$(_planveyor_bare_entrypoints_role_transition_commands)}"
    "${(@f)$(_planveyor_bare_entrypoints_role_resume_commands)}"
    "${(@f)$(_planveyor_bare_entrypoints_arch_track_commands)}"
  )
  print -l -- "${managed_cmds[@]}"
}

_planveyor_bare_entrypoints_summary_lines() {
  local -a stage1_cmds manager_tui_cmds helper_cmds docs_hygiene_cmds role_main_cmds role_transition_cmds role_resume_cmds arch_track_cmds
  stage1_cmds=("${(@f)$(_planveyor_bare_entrypoints_stage1_operator_commands)}")
  manager_tui_cmds=("${(@f)$(_planveyor_bare_entrypoints_manager_tui_commands)}")
  helper_cmds=("${(@f)$(_planveyor_bare_entrypoints_helper_commands)}")
  docs_hygiene_cmds=("${(@f)$(_planveyor_bare_entrypoints_docs_hygiene_commands)}")
  role_main_cmds=("${(@f)$(_planveyor_bare_entrypoints_role_main_commands)}")
  role_transition_cmds=("${(@f)$(_planveyor_bare_entrypoints_role_transition_commands)}")
  role_resume_cmds=("${(@f)$(_planveyor_bare_entrypoints_role_resume_commands)}")
  arch_track_cmds=("${(@f)$(_planveyor_bare_entrypoints_arch_track_commands)}")

  print -r -- "Managed shims (Stage 2 owner-facing subset):"
  print -r -- "  Stage 1 operator: ${stage1_cmds[*]}"
  print -r -- "  Manager TUI: ${manager_tui_cmds[*]}"
  print -r -- "  Helpers: ${helper_cmds[*]}"
  print -r -- "  Docs hygiene: ${docs_hygiene_cmds[*]}"
  print -r -- "  Role main: ${role_main_cmds[*]}"
  print -r -- "  Role transition/censor: ${role_transition_cmds[*]}"
  print -r -- "  Manual resume: ${role_resume_cmds[*]}"
  print -r -- "  Architect track TUI/resume: ${arch_track_cmds[*]}"
}

_planveyor_bare_entrypoints_fallback_hint() {
  local cmd="${1:-<CMD>}"
  echo "zsh -lc 'source \"\${PLANVEYOR_ROOT:-\$HOME/planveyor}/scripts/planveyor.zsh\" && ${cmd} ...'"
}

_planveyor_bare_entrypoints_is_ephemeral_dir() {
  local dir="${1:-}"
  [[ -n "${dir//[[:space:]]/}" && "$dir" == /* ]] || return 1

  local tmpdir="${TMPDIR:-/tmp}"
  case "$dir" in
    /tmp|/tmp/*|/private/tmp|/private/tmp/*|/var/tmp|/var/tmp/*|/private/var/tmp|/private/var/tmp/*|/var/folders/*|/private/var/folders/*)
      return 0
      ;;
  esac

  if [[ -n "${tmpdir//[[:space:]]/}" && "$tmpdir" == /* ]]; then
    case "$dir" in
      "$tmpdir"|"$tmpdir"/*) return 0 ;;
    esac
  fi

  return 1
}

_planveyor_bare_entrypoints_is_stable_autodetect_dir() {
  local dir="${1:-}"
  [[ -n "${dir//[[:space:]]/}" && "$dir" == /* ]] || return 1
  _planveyor_bare_entrypoints_is_ephemeral_dir "$dir" && return 1

  case "$dir" in
    /opt/homebrew/bin|/opt/homebrew/sbin|/usr/local/bin|/usr/local/sbin|"$HOME"/bin|"$HOME"/.local/bin|"$HOME"/.cargo/bin)
      return 0
      ;;
    "$HOME"/*)
      case "$dir" in
        "$HOME"/.Trash|"$HOME"/.Trash/*|"$HOME"/.cache|"$HOME"/.cache/*|"$HOME"/.tmp|"$HOME"/.tmp/*|"$HOME"/tmp|"$HOME"/tmp/*|"$HOME"/Library/Caches|"$HOME"/Library/Caches/*)
          return 1
          ;;
      esac
      local base="${dir:t}"
      [[ "$base" == "bin" || "$base" == "sbin" ]] && return 0
      ;;
  esac

  return 1
}

_planveyor_bare_entrypoints_render_shim() {
  local shim_cmd="${1:-}"
  local installer_root="${2:-}"
  [[ -n "${shim_cmd//[[:space:]]/}" && -n "${installer_root//[[:space:]]/}" ]] || return 1

  local shim_cmd_q="${shim_cmd//\'/\'\\\'\'}"
  local installer_root_q="${installer_root//\'/\'\\\'\'}"

  cat <<EOF
#!/bin/zsh
# Managed by planveyor_bare_entrypoints_install. Re-run the helper to update this shim.
# planveyor_bare_entrypoints_shim_format=v1
emulate -L zsh
shim_cmd='${shim_cmd_q}'
# installer_tooling_root='${installer_root_q}'
stable_tooling_root="\${HOME}/planveyor"
if [[ -n "\${PLANVEYOR_ROOT:-}" ]]; then
  planveyor_root="\${PLANVEYOR_ROOT}"
else
  planveyor_root="\$stable_tooling_root"
fi
script_path="\${planveyor_root%/}/scripts/planveyor.zsh"

if [[ ! -r "\$script_path" ]]; then
  echo "Missing tooling wrapper for \${shim_cmd}: \$script_path" >&2
  echo "Set PLANVEYOR_ROOT to the current tooling repo root or rerun planveyor_bare_entrypoints_install after moving the repo." >&2
  echo "Fallback: $(_planveyor_bare_entrypoints_fallback_hint "${shim_cmd}")" >&2
  exit 1
fi

source "\$script_path" || exit \$?
if ! whence -w "\$shim_cmd" >/dev/null 2>&1; then
  echo "Wrapper not loaded: \${shim_cmd} (from \$script_path)" >&2
  exit 1
fi

"\$shim_cmd" "\$@"
EOF
}

_planveyor_bare_entrypoints_write_shim() {
  local target_path="${1:-}"
  local shim_cmd="${2:-}"
  local baked_root="${3:-}"
  [[ -n "${target_path//[[:space:]]/}" && -n "${shim_cmd//[[:space:]]/}" && -n "${baked_root//[[:space:]]/}" ]] || return 1

  local target_dir="${target_path:h}"
  mkdir -p "$target_dir" 2>/dev/null || return 1

  local tmp_path="${target_path}.tmp.$$.$RANDOM"
  _planveyor_bare_entrypoints_render_shim "$shim_cmd" "$baked_root" > "$tmp_path" || {
    rm -f "$tmp_path" 2>/dev/null || true
    return 1
  }
  chmod 755 "$tmp_path" 2>/dev/null || true
  mv -f "$tmp_path" "$target_path" 2>/dev/null || {
    rm -f "$tmp_path" 2>/dev/null || true
    return 1
  }
  return 0
}

_planveyor_default_runner_for_role() {
  local role_id="$1"
  case "$role_id" in
    architect|coder|manager) echo "codex" ;;
    planner) echo "codex" ;;
    reviewer) echo "codex" ;;
    *) return 1 ;;
  esac
}

_planveyor_normalize_runner_id() {
  local v="${1//[[:space:]]/}"
  v="${v:l}"
  case "$v" in
    codex|openai) echo "codex" ;;
    claude|anthropic) echo "claude" ;;
    *) return 1 ;;
  esac
}

_planveyor_runner_selection_policy_path() {
  print -r -- "$(_planveyor_root)/docs/_meta/runner_selection_resolution.v1.json"
}

planveyor_runner_resolve_strict() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_runner_resolve_strict)" || return $?
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
  role_id="$(_planveyor_normalize_role_id "${1:-}")" || {
    echo "runner_selection_error=invalid_role" >&2
    return 1
  }
  local init_attempt_id="${2:-}"
  if (( $# != 2 )) || ! _planveyor_is_uuid "$init_attempt_id" || [[ "$init_attempt_id" != "${init_attempt_id:l}" ]]; then
    echo "runner_selection_error=invalid_init_attempt_id" >&2
    return 1
  fi

  local root="$(_planveyor_project_root)" || return 1
  local policy_path=""
  policy_path="$(_planveyor_runner_selection_policy_path)" || {
    echo "runner_selection_error=policy_host_missing" >&2
    return 1
  }

  _planveyor_py_any - "$policy_path" "$root" "$role_id" "$init_attempt_id" <<'PY'
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
root = Path(sys.argv[2])
role = sys.argv[3]
init_attempt_id = sys.argv[4]

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


def read_regular(path: Path, *, missing_reason: str, malformed_reason: str) -> bytes:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        fail(missing_reason)
    except OSError:
        fail(malformed_reason)
    if not stat.S_ISREG(info.st_mode):
        fail(malformed_reason)
    if not info.st_mode & (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH):
        fail("carrier_unreadable" if path.name.startswith(".planveyor.runner.") else malformed_reason)
    try:
        return path.read_bytes()
    except OSError:
        fail("carrier_unreadable" if path.name.startswith(".planveyor.runner.") else malformed_reason)


def load_policy() -> dict[str, object]:
    raw = read_regular(policy_path, missing_reason="policy_host_missing", malformed_reason="policy_host_invalid")
    try:
        policy = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
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


if not UUID_RE.fullmatch(init_attempt_id):
    fail("invalid_init_attempt_id")
policy = load_policy()
matrix = policy["role_runner_matrix"]
assert isinstance(matrix, dict)
if role not in matrix:
    fail("invalid_role")

carrier_path = root / f".planveyor.runner.{role}"
try:
    carrier_info = os.lstat(carrier_path)
except FileNotFoundError:
    carrier_state = "absent_default"
    runner = "codex"
else:
    if not stat.S_ISREG(carrier_info.st_mode):
        fail("carrier_non_regular")
    if not carrier_info.st_mode & (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH):
        fail("carrier_unreadable")
    try:
        raw = carrier_path.read_bytes()
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("carrier_malformed")
    except OSError:
        fail("carrier_unreadable")
    if "\x00" in text:
        fail("carrier_malformed")
    lines = text.splitlines()
    if len(lines) == 1:
        runner = lines[0]
    elif len(lines) == 2 and lines[0].startswith("# "):
        runner = lines[1]
    else:
        fail("carrier_malformed" if text.strip() else "carrier_blank")
    if not runner or runner != runner.strip():
        fail("carrier_blank" if not runner.strip() else "carrier_malformed")
    carrier_state = "present_valid"

if runner not in {item for runners in EXPECTED_MATRIX.values() for item in runners}:
    fail("carrier_unknown_runner")
allowed = matrix[role]
if not isinstance(allowed, list) or runner not in allowed:
    fail("carrier_role_invalid")

identity = {
    "carrier_state": carrier_state,
    "role": role,
    "runner": runner,
    "schema_version": "runner_selection_identity.v1",
}
canonical_identity = json.dumps(
    identity,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
canonical_identity = unicodedata.normalize("NFC", canonical_identity)
selection_digest = hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest()
resolution = {
    "carrier_state": carrier_state,
    "init_attempt_id": init_attempt_id,
    "role": role,
    "runner": runner,
    "schema_version": "runner_selection_resolution.v1",
    "selection_digest": selection_digest,
}
print(json.dumps(resolution, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
PY
}

_planveyor_runner_at_root() {
  # Usage: _planveyor_runner_at_root <project_root> <role_id>
  # Reads the runner carrier under a project root the caller has already
  # bound: the override file if present, otherwise the role default.
  local root="${1:-}" role_id="${2:-}"
  local file_path="$root/.planveyor.runner.${role_id}"
  if [[ -f "$file_path" ]]; then
    _planveyor_read "$file_path"
    return $?
  fi
  _planveyor_default_runner_for_role "$role_id"
}

planveyor_runner() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_runner)" || return $?
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
  role_id="$(_planveyor_normalize_role_id "$1")" || {
    echo "Usage: planveyor_runner <architect|coder|planner|reviewer|manager>" >&2
    return 1
  }
  local root="$(_planveyor_project_root)" || return 1
  _planveyor_runner_at_root "$root" "$role_id"
}

planveyor_runner_set() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_runner_set)" || return $?
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
  local scope="worktree"
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || {
    echo "Usage: planveyor_runner_set <architect|coder|planner|reviewer|manager> <codex|claude>" >&2
    return 1
  }
  local runner_id=""
  runner_id="$(_planveyor_normalize_runner_id "$2")" || {
    echo "Usage: planveyor_runner_set <architect|coder|planner|reviewer|manager> <codex|claude>" >&2
    return 1
  }

  case "${role_id}:${runner_id}" in
    architect:codex|coder:codex|manager:codex|planner:codex|planner:claude|reviewer:codex|reviewer:claude) ;;
    *)
      echo "Unsupported runner for role=${role_id}: ${runner_id}" >&2
      echo "Allowed:" >&2
      echo "  - architect/manager: codex" >&2
      echo "  - coder: codex" >&2
      echo "  - planner: codex | claude" >&2
      echo "  - reviewer: codex | claude" >&2
      return 1
      ;;
  esac

  local root=""
  root="$(_planveyor_project_root)" || return $?
  git -C "$root" rev-parse --show-toplevel >/dev/null 2>&1 || {
    echo "ERROR: planveyor_runner_set must be run inside a git worktree (cd into your planveyor checkout first)." >&2
    return 1
  }
  local wt="$(_planveyor_worktree_id 2>/dev/null || true)"
  [[ -n "${wt//[[:space:]]/}" ]] || wt="${root:t}"
  local now="$(_planveyor_now)"
  local file_path="$root/.planveyor.runner.${role_id}"
  local log_path="$root/.planveyor.runner.${role_id}.log"
  local tmp_path="${file_path}.tmp.$$.$RANDOM"
  (umask 077; printf "# %s\n%s\n" "$now" "$runner_id" > "$tmp_path") || {
    rm -f "$tmp_path" 2>/dev/null || true
    echo "ERROR: could not stage runner selection: ${file_path}" >&2
    return 1
  }
  mv -f "$tmp_path" "$file_path" 2>/dev/null || {
    rm -f "$tmp_path" 2>/dev/null || true
    echo "ERROR: could not publish runner selection atomically: ${file_path}" >&2
    return 1
  }
  printf "%s\t%s\n" "$now" "$runner_id" >> "$log_path"
  echo "Saved: ${file_path} (${now}; scope=${scope}; worktree=${wt})" >&2
}

_planveyor_role_runner_preflight_normalize() {
  local raw="${1:-}"
  local role_key="${raw//[[:space:]]/}"
  role_key="${role_key:l}"
  case "$role_key" in
    architect_initial|architect-initial|arch_initial|arch-initial)
      echo "role=architect_initial;session_key=architect;wrapper=planveyor_arch_initial;runner_role=architect"
      return 0
      ;;
    architect_censor|architect-censor|arch_censor|arch-censor)
      echo "role=architect_censor;session_key=architect;wrapper=planveyor_arch_censor;runner_role=architect"
      return 0
      ;;
    planner_censor|planner-censor)
      echo "role=planner_censor;session_key=planner;wrapper=planveyor_planner_censor;runner_role=planner"
      return 0
      ;;
    coder_censor|coder-censor)
      echo "role=coder_censor;session_key=coder;wrapper=planveyor_coder_censor;runner_role=coder"
      return 0
      ;;
  esac

  local session_key=""
  session_key="$(_planveyor_normalize_session_key "$raw")" || return 1

  case "$session_key" in
    architect)
      echo "role=architect;session_key=architect;wrapper=planveyor_arch;runner_role=architect"
      ;;
    planner)
      echo "role=planner;session_key=planner;wrapper=planveyor_planner;runner_role=planner"
      ;;
    coder)
      echo "role=coder;session_key=coder;wrapper=planveyor_coder;runner_role=coder"
      ;;
    reviewer)
      echo "role=reviewer;session_key=reviewer;wrapper=planveyor_reviewer;runner_role=reviewer"
      ;;
    reviewer_code_risk)
      echo "role=reviewer_code_risk;session_key=reviewer_code_risk;wrapper=planveyor_reviewer_code_risk;runner_role=reviewer"
      ;;
    reviewer_code_contracts)
      echo "role=reviewer_code_contracts;session_key=reviewer_code_contracts;wrapper=planveyor_reviewer_code_contracts;runner_role=reviewer"
      ;;
    manager)
      echo "role=${session_key};session_key=${session_key};wrapper=planveyor_${session_key};runner_role=${session_key};unsupported=1"
      ;;
    *)
      return 1
      ;;
  esac
}

_planveyor_role_runner_preflight_emit() {
  local format="${1:-plain}"
  shift
  if [[ "$format" == "json" ]]; then
    _planveyor_py_any - "$@" <<'PY'
from __future__ import annotations

import json
import sys

payload = {}
for item in sys.argv[1:]:
    key, value = item.split("=", 1)
    if value == "true":
        payload[key] = True
    elif value == "false":
        payload[key] = False
    elif key == "init_run_exit_code" and value.lstrip("-").isdigit():
        payload[key] = int(value)
    else:
        payload[key] = value
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
    return $?
  fi

  local item=""
  for item in "$@"; do
    print -r -- "$item"
  done
}

_planveyor_json_file_field() {
  local json_path="${1:-}"
  local field="${2:-}"
  [[ -f "$json_path" && -n "${field//[[:space:]]/}" ]] || return 1
  _planveyor_py_any - "$json_path" "$field" <<'PY'
from __future__ import annotations

import json
import sys

path, field = sys.argv[1:3]
try:
    payload = json.load(open(path, encoding="utf-8"))
except Exception:
    sys.exit(1)
value = payload.get(field, "")
if value is None:
    value = ""
print(str(value))
PY
}

_planveyor_model_identity_value() {
  local field="${1:-}"
  shift || true
  [[ -n "${field//[[:space:]]/}" ]] || return 1

  local item=""
  for item in "$@"; do
    case "$item" in
      ${field}=*)
        print -r -- "${item#${field}=}"
        return 0
        ;;
    esac
  done
  return 1
}

_planveyor_model_identity_meta() {
  local item=""
  for item in "$@"; do
    [[ -n "${item//[[:space:]]/}" ]] || continue
    printf '%s ' "$item"
  done | sed 's/[[:space:]]*$//'
}

_planveyor_role_execution_base_role() {
  case "${1:-}" in
    architect_initial|architect_censor) echo "architect" ;;
    planner_censor) echo "planner" ;;
    coder_censor) echo "coder" ;;
    reviewer_code_risk|reviewer_code_contracts) echo "reviewer" ;;
    *) echo "${1:-}" ;;
  esac
}

_planveyor_role_execution_profile_mode() {
  case "${1:-}" in
    architect_censor|planner_censor|coder_censor) echo "censor" ;;
    *) echo "main" ;;
  esac
}

_planveyor_model_identity_profile_for_runner() {
  local runner_id="${1:-}"
  local role="${2:-}"
  local base_role=""
  local profile_mode=""
  base_role="$(_planveyor_role_execution_base_role "$role")"
  profile_mode="$(_planveyor_role_execution_profile_mode "$role")"
  case "$runner_id" in
    codex)
      _planveyor_profile_for_role_mode "$base_role" "$profile_mode"
      ;;
    claude)
      echo "direct_child"
      ;;
    *)
      echo "N/A (why=runner profile not readable)"
      ;;
  esac
}

_planveyor_sha256_value() {
  local value="${1-}"
  _planveyor_py_any - "$value" <<'PY'
import hashlib
import sys

print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest())
PY
}

_planveyor_sha256_normalized_text() {
  local value="${1-}"
  _planveyor_py_any - "$value" <<'PY'
import hashlib
import sys

data = sys.argv[1].encode("utf-8").replace(b"\r\n", b"\n")
data = data.rstrip(b"\n") + b"\n"
print(hashlib.sha256(data).hexdigest())
PY
}

_planveyor_login_shell_launch_root() {
  emulate -L zsh
  local root=""
  root="$(_planveyor_root 2>/dev/null || true)"
  [[ -n "${root//[[:space:]]/}" ]] || return 1
  print -r -- "$root"
}














_planveyor_model_identity_payload_args() {
  local runner_id="${1:-}"
  local role="${2:-}"
  local runner_alias="${runner_id:-N/A (why=runner not readable)}"
  local profile=""
  profile="$(_planveyor_model_identity_profile_for_runner "$runner_id" "$role" 2>/dev/null || true)"
  [[ -n "${profile//[[:space:]]/}" ]] || profile="N/A (why=profile not readable)"

  local model="N/A (why=not observable)"
  local configured_model_id="N/A (why=not observable)"
  local observable_model_id="N/A (why=provider model metadata not exposed)"
  local model_id_state="unknown"

  case "$runner_id" in
    codex)
      model="$(_planveyor_codex_expected_model_for_profile "$profile" 2>/dev/null || echo "N/A (why=codex model not readable from profile)")"
      configured_model_id="N/A (why=codex model comes from profile/session stats)"
      ;;
    claude)
      _planveyor_private_family_load provider || return $?
      local claude_model=""
      claude_model="$(_planveyor_claude_configured_model 2>/dev/null || true)"
      if [[ -n "${claude_model//[[:space:]]/}" ]]; then
        model="$claude_model"
        configured_model_id="$claude_model"
        model_id_state="configured_explicit"
      else
        model="N/A (why=consumer default)"
        configured_model_id=""
        model_id_state="consumer_default"
      fi
      ;;
    ""|N/A*)
      runner_alias="N/A (why=runner not readable)"
      model="N/A (why=runner not readable)"
      configured_model_id="N/A (why=runner not readable)"
      observable_model_id="N/A (why=runner not readable)"
      model_id_state="unknown"
      ;;
    *)
      model="N/A (why=runner not supported by model readback)"
      configured_model_id="N/A (why=runner not supported by model readback)"
      observable_model_id="N/A (why=runner not supported by model readback)"
      model_id_state="unknown"
      ;;
  esac

  print -r -- "runner_alias=${runner_alias}"
  print -r -- "profile=${profile}"
  print -r -- "model=${model}"
  print -r -- "configured_model_id=${configured_model_id}"
  print -r -- "observable_model_id=${observable_model_id}"
  print -r -- "model_id_state=${model_id_state}"
}


_planveyor_role_runner_preflight_payload_args() {
  local role_arg="${1:-}"
  [[ -n "${role_arg//[[:space:]]/}" ]] || return 2

  local normalized=""
  normalized="$(_planveyor_role_runner_preflight_normalize "$role_arg" 2>/dev/null || true)"
  if [[ -z "${normalized//[[:space:]]/}" ]]; then
    print -r -- "role=${role_arg}"
    print -r -- "wrapper=N/A (why=unsupported role)"
    print -r -- "runner_id=N/A (why=unsupported role)"
    print -r -- "runner=N/A (why=unsupported role)"
    print -r -- "carrier_state=N/A (why=unsupported role)"
    print -r -- "init_attempt_id=N/A (why=unsupported role)"
    print -r -- "selection_digest=N/A (why=unsupported role)"
    print -r -- "selection_schema_version=N/A (why=unsupported role)"
    print -r -- "runner_alias=N/A (why=unsupported role)"
    print -r -- "profile=N/A (why=unsupported role)"
    print -r -- "provider_provenance=not_applicable"
    print -r -- "model=N/A (why=unsupported role)"
    print -r -- "configured_model_id=N/A (why=unsupported role)"
    print -r -- "observable_model_id=N/A (why=unsupported role)"
    print -r -- "model_id_state=unknown"
    print -r -- "configured_effort=N/A (why=unsupported role)"
    print -r -- "effort_state=unknown"
    print -r -- "launcher_state=not_applicable"
    print -r -- "launcher_installed_sha256=N/A (why=unsupported role)"
    print -r -- "launcher_canonical_sha256=N/A (why=unsupported role)"
    print -r -- "launcher_loaded_script_path=N/A (why=unsupported role)"
    print -r -- "launcher_expected_source_root=N/A (why=unsupported role)"
    print -r -- "launcher_loaded_source_root=N/A (why=unsupported role)"
    print -r -- "launcher_provenance_state=not_applicable"
    print -r -- "launcher_policy_state=not_applicable"
    print -r -- "launcher_policy_canonical_sha256=N/A (why=unsupported role)"
    print -r -- "launcher_policy_effective_sha256=N/A (why=unsupported role)"
    print -r -- "launcher_policy_mismatch_fields=none"
    print -r -- "session_key=N/A (why=unsupported role)"
    print -r -- "runner_role=N/A (why=unsupported role)"
    print -r -- "sid=N/A (why=unsupported role)"
    print -r -- "login_shell_visible=false"
    print -r -- "forbidden_flags_absent=false"
    print -r -- "execution_ready=false"
    print -r -- "reason=unsupported_role"
    print -r -- "remediation=none"
    print -r -- "init_run_exit_code=N/A (why=unsupported role)"
    print -r -- "init_run_outcome=not_applicable"
    return 1
  fi

  local role="" session_key="" wrapper="" runner_role="" unsupported=""
  local part=""
  for part in ${(s:;:)normalized}; do
    case "$part" in
      role=*) role="${part#role=}" ;;
      session_key=*) session_key="${part#session_key=}" ;;
      wrapper=*) wrapper="${part#wrapper=}" ;;
      runner_role=*) runner_role="${part#runner_role=}" ;;
      unsupported=*) unsupported="${part#unsupported=}" ;;
    esac
  done

  local runner_id="N/A (why=runner not readable)"
  local carrier_state="N/A (why=strict selection unavailable)"
  local init_attempt_id=""
  local selection_digest="N/A (why=strict selection unavailable)"
  local selection_schema_version="N/A (why=strict selection unavailable)"
  init_attempt_id="$(_planveyor_uuid4 2>/dev/null || true)"

  local selection_resolution_json="" selection_kv=""
  if _planveyor_is_uuid "$init_attempt_id" && [[ "$init_attempt_id" == "${init_attempt_id:l}" ]]; then
    selection_resolution_json="$(planveyor_runner_resolve_strict "$runner_role" "$init_attempt_id" 2>/dev/null || true)"
    if [[ -n "${selection_resolution_json//[[:space:]]/}" ]]; then
      selection_kv="$(_planveyor_py_any - "$selection_resolution_json" "$runner_role" "$init_attempt_id" <<'PY'
from __future__ import annotations

import json
import re
import sys

raw, expected_role, expected_attempt = sys.argv[1:]
expected_keys = {
    "carrier_state",
    "init_attempt_id",
    "role",
    "runner",
    "schema_version",
    "selection_digest",
}


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


try:
    payload = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("invalid_selection_shape")
    if payload.get("role") != expected_role:
        raise ValueError("selection_role_mismatch")
    if payload.get("init_attempt_id") != expected_attempt:
        raise ValueError("selection_attempt_mismatch")
    if payload.get("schema_version") != "runner_selection_resolution.v1":
        raise ValueError("selection_schema_mismatch")
    if payload.get("carrier_state") not in {"absent_default", "present_valid"}:
        raise ValueError("selection_carrier_state_invalid")
    runner = payload.get("runner")
    digest = payload.get("selection_digest")
    if not isinstance(runner, str) or not runner:
        raise ValueError("selection_runner_invalid")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("selection_digest_invalid")
except (TypeError, ValueError, json.JSONDecodeError):
    raise SystemExit(1)

print(f"runner={payload['runner']}")
print(f"carrier_state={payload['carrier_state']}")
print(f"init_attempt_id={payload['init_attempt_id']}")
print(f"selection_digest={payload['selection_digest']}")
print(f"selection_schema_version={payload['schema_version']}")
PY
)" || selection_kv=""
    fi
  fi
  local selection_item=""
  for selection_item in ${(f)selection_kv}; do
    case "$selection_item" in
      runner=*) runner_id="${selection_item#runner=}" ;;
      carrier_state=*) carrier_state="${selection_item#carrier_state=}" ;;
      init_attempt_id=*) init_attempt_id="${selection_item#init_attempt_id=}" ;;
      selection_digest=*) selection_digest="${selection_item#selection_digest=}" ;;
      selection_schema_version=*) selection_schema_version="${selection_item#selection_schema_version=}" ;;
    esac
  done
  if [[ -z "${selection_kv//[[:space:]]/}" ]]; then
    init_attempt_id="N/A (why=strict selection unavailable)"
  fi

  local -a model_identity_args
  model_identity_args=("${(@f)$(_planveyor_model_identity_payload_args "$runner_id" "$role")}")
  local configured_model_id=""
  local model_id_state=""
  configured_model_id="$(_planveyor_model_identity_value configured_model_id "${model_identity_args[@]}" 2>/dev/null || true)"
  model_id_state="$(_planveyor_model_identity_value model_id_state "${model_identity_args[@]}" 2>/dev/null || true)"

  local configured_effort=""
  local effort_state="not_applicable"
  local launcher_state="not_applicable"
  local launcher_installed_sha256="N/A (why=runner does not use a login-shell launcher)"
  local launcher_canonical_sha256="N/A (why=runner does not use a login-shell launcher)"
  local launcher_loaded_script_path="N/A (why=runner does not use a login-shell launcher)"
  local launcher_expected_source_root="N/A (why=runner does not use a login-shell launcher)"
  local launcher_loaded_source_root="N/A (why=runner does not use a login-shell launcher)"
  local launcher_provenance_state="not_applicable"
  local launcher_policy_state="not_applicable"
  local launcher_policy_canonical_sha256="N/A (why=runner does not use a login-shell launcher policy)"
  local launcher_policy_effective_sha256="N/A (why=runner does not use a login-shell launcher policy)"
  local launcher_policy_mismatch_fields="none"
  local provider_provenance="not_applicable"
  if [[ "$runner_id" == "claude" ]]; then
    if _planveyor_private_family_load provider; then
      provider_provenance="$(_planveyor_provider_provenance 2>/dev/null || true)"
      configured_effort="$(_planveyor_claude_configured_effort 2>/dev/null || true)"
    else
      provider_provenance="unavailable"
    fi
    [[ -n "${provider_provenance//[[:space:]]/}" ]] || provider_provenance="unavailable"
    launcher_provenance_state="$provider_provenance"
    if [[ -n "${configured_effort//[[:space:]]/}" ]]; then
      effort_state="configured_explicit"
    else
      configured_effort=""
      effort_state="consumer_default"
    fi
  fi

  local root="$(_planveyor_project_root)" || return $?
  local sid=""
  sid="$(planveyor_session "$session_key" 2>/dev/null || true)"
  [[ "$sid" == "<SESSION_ID>" ]] && sid=""

  local session_file_state="missing"
  [[ -n "${sid//[[:space:]]/}" ]] && session_file_state="present"

  local init_run_path=""
  local init_run_state="N/A (why=no prior session required)"
  if [[ -n "${sid//[[:space:]]/}" ]]; then
    init_run_path="${root}/.planveyor.init_runs/by_sid/${sid}/meta.json"
    if [[ -f "$init_run_path" ]]; then
      init_run_state="present"
    else
      init_run_state="missing"
    fi
  fi
  local init_run_runner=""
  local init_run_session_key=""
  local init_run_configured_model_id=""
  local init_run_observable_model_id=""
  local init_run_model_id_state=""
  local init_run_role=""
  local init_run_configured_effort=""
  local init_run_effort_state=""
  local init_run_exit_code="N/A (why=init-run meta unavailable)"
  local init_run_exit_code_state="missing"
  local init_run_outcome="not_applicable"
  if [[ "$init_run_state" == "present" ]]; then
    init_run_role="$(_planveyor_json_file_field "$init_run_path" role 2>/dev/null || true)"
    init_run_runner="$(_planveyor_json_file_field "$init_run_path" runner 2>/dev/null || true)"
    init_run_session_key="$(_planveyor_json_file_field "$init_run_path" session_key 2>/dev/null || true)"
    init_run_configured_model_id="$(_planveyor_json_file_field "$init_run_path" configured_model_id 2>/dev/null || true)"
    init_run_observable_model_id="$(_planveyor_json_file_field "$init_run_path" observable_model_id 2>/dev/null || true)"
    init_run_model_id_state="$(_planveyor_json_file_field "$init_run_path" model_id_state 2>/dev/null || true)"
    init_run_configured_effort="$(_planveyor_json_file_field "$init_run_path" configured_effort 2>/dev/null || true)"
    init_run_effort_state="$(_planveyor_json_file_field "$init_run_path" effort_state 2>/dev/null || true)"
    init_run_exit_code="$(_planveyor_json_file_field "$init_run_path" exit_code 2>/dev/null || true)"
    if [[ "$init_run_exit_code" == <-> || "$init_run_exit_code" == -<-> ]]; then
      init_run_exit_code_state="valid"
      if (( init_run_exit_code == 0 )); then
        init_run_outcome="success"
      else
        init_run_outcome="failed"
      fi
    else
      init_run_exit_code_state="invalid"
      init_run_exit_code="N/A (why=init-run exit_code missing or malformed)"
      init_run_outcome="invalid"
    fi
    if [[ "$runner_id" == "claude" ]]; then
      if [[ "$init_run_outcome" == "success" ]] && {
        [[ "$init_run_role" != "$runner_role" ]] ||
        [[ "$init_run_runner" != "$runner_id" ]] ||
        [[ "$init_run_session_key" != "$session_key" ]] ||
        [[ "$init_run_model_id_state" != "$model_id_state" ]] ||
        [[ "$init_run_configured_model_id" != "$configured_model_id" ]] ||
        [[ "$init_run_effort_state" != "$effort_state" ]] ||
        [[ "$init_run_configured_effort" != "$configured_effort" ]]
      }; then
        init_run_outcome="invalid"
      fi
    elif [[ "$init_run_outcome" == "success" ]] && {
      [[ "$init_run_role" != "$runner_role" ]] ||
      [[ "$init_run_runner" != "$runner_id" ]] ||
      [[ "$init_run_session_key" != "$session_key" ]]
    }; then
      init_run_outcome="invalid"
    fi
    # Codex init captures do not attest optional model/effort identity. Their
    # outcome describes the captured exit status and role/session binding;
    # identity readback remains unknown rather than being inferred as verified.
  elif [[ "$runner_id" == "claude" ]]; then
    init_run_outcome="missing"
  fi

  local login_shell_visible="N/A (why=runner does not require a login-shell probe)"

  local forbidden_flags_absent="true"
  local execution_ready="true"
  local reason="ok"
  local remediation="none"

  if [[ -n "${unsupported//[[:space:]]/}" ]]; then
    execution_ready="false"
    reason="unsupported_role_for_runner_preflight"
  elif [[ "$runner_id" == "N/A"* ]]; then
    execution_ready="false"
    reason="runner_not_readable"
  elif [[ "$runner_id" != "codex" && "$runner_id" != "claude" ]]; then
    execution_ready="false"
    reason="unsupported_runner"
  elif [[ "$runner_id" == "claude" && "$provider_provenance" != "direct_child" ]]; then
    execution_ready="false"
    reason="provider_provenance_invalid"
  elif [[ "$runner_id" == "claude" && "$model_id_state" != "configured_explicit" && "$model_id_state" != "consumer_default" ]]; then
    execution_ready="false"
    reason="configured_model_mismatch"
  elif [[ "$runner_id" == "claude" && "$effort_state" != "configured_explicit" && "$effort_state" != "consumer_default" ]]; then
    execution_ready="false"
    reason="configured_effort_mismatch"
  elif [[ -z "${sid//[[:space:]]/}" ]]; then
    execution_ready="false"
    reason="missing_session_sid"
  elif [[ "$runner_id" == "claude" && "$init_run_state" == "missing" ]]; then
    execution_ready="false"
    reason="missing_init_run_capture"
  elif [[ "$runner_id" == "claude" && "$init_run_exit_code_state" == "invalid" ]]; then
    execution_ready="false"
    reason="init_run_exit_code_invalid"
  elif [[ "$runner_id" == "claude" && "$init_run_outcome" == "failed" ]]; then
    execution_ready="false"
    reason="init_run_nonzero"
  elif [[ "$runner_id" == "claude" && "$init_run_role" != "$runner_role" ]]; then
    execution_ready="false"
    reason="init_run_role_mismatch"
  elif [[ "$runner_id" == "claude" && "$init_run_runner" != "$runner_id" ]]; then
    execution_ready="false"
    reason="init_run_runner_mismatch"
  elif [[ "$runner_id" == "claude" && "$init_run_session_key" != "$session_key" ]]; then
    execution_ready="false"
    reason="init_run_session_key_mismatch"
  elif [[ "$runner_id" == "claude" && ( "$init_run_model_id_state" != "$model_id_state" || "$init_run_configured_model_id" != "$configured_model_id" ) ]]; then
    execution_ready="false"
    reason="init_run_configured_model_mismatch"
  elif [[ "$runner_id" == "claude" && ( "$init_run_effort_state" != "$effort_state" || "$init_run_configured_effort" != "$configured_effort" ) ]]; then
    execution_ready="false"
    reason="init_run_configured_effort_mismatch"
  fi

  case "$reason" in
    ok) remediation="none" ;;
    provider_provenance_invalid) remediation="use_consumer_claude_cli" ;;
    configured_model_mismatch) remediation="set_or_clear_PLANVEYOR_CLAUDE_MODEL" ;;
    configured_effort_mismatch) remediation="set_or_clear_PLANVEYOR_CLAUDE_EFFORT" ;;
    init_run_nonzero) remediation="rerun_role_init_after_fix" ;;
    missing_session_sid|missing_init_run_capture|init_run_*) remediation="inspect_init_meta_then_rerun_init" ;;
    *) remediation="none" ;;
  esac

  print -r -- "role=${role}"
  print -r -- "wrapper=${wrapper}"
  print -r -- "runner_id=${runner_id}"
  print -r -- "runner=${runner_id}"
  print -r -- "carrier_state=${carrier_state}"
  print -r -- "init_attempt_id=${init_attempt_id}"
  print -r -- "selection_digest=${selection_digest}"
  print -r -- "selection_schema_version=${selection_schema_version}"
  local model_identity_item=""
  for model_identity_item in "${model_identity_args[@]}"; do
    print -r -- "$model_identity_item"
  done
  print -r -- "provider_provenance=${provider_provenance}"
  print -r -- "configured_effort=${configured_effort}"
  print -r -- "effort_state=${effort_state}"
  print -r -- "launcher_state=${launcher_state}"
  print -r -- "launcher_installed_sha256=${launcher_installed_sha256}"
  print -r -- "launcher_canonical_sha256=${launcher_canonical_sha256}"
  print -r -- "launcher_loaded_script_path=${launcher_loaded_script_path}"
  print -r -- "launcher_expected_source_root=${launcher_expected_source_root}"
  print -r -- "launcher_loaded_source_root=${launcher_loaded_source_root}"
  print -r -- "launcher_provenance_state=${launcher_provenance_state}"
  print -r -- "launcher_policy_state=${launcher_policy_state}"
  print -r -- "launcher_policy_canonical_sha256=${launcher_policy_canonical_sha256}"
  print -r -- "launcher_policy_effective_sha256=${launcher_policy_effective_sha256}"
  print -r -- "launcher_policy_mismatch_fields=${launcher_policy_mismatch_fields}"
  print -r -- "session_key=${session_key}"
  print -r -- "runner_role=${runner_role}"
  print -r -- "sid=${sid:-N/A (why=.planveyor.session.${session_key} is missing)}"
  print -r -- "login_shell_visible=${login_shell_visible}"
  print -r -- "forbidden_flags_absent=${forbidden_flags_absent}"
  print -r -- "execution_ready=${execution_ready}"
  print -r -- "reason=${reason}"
  print -r -- "remediation=${remediation}"
  print -r -- "session_file_state=${session_file_state}"
  print -r -- "init_run_state=${init_run_state}"
  print -r -- "init_run_runner=${init_run_runner:-N/A (why=init-run meta unavailable)}"
  print -r -- "init_run_session_key=${init_run_session_key:-N/A (why=init-run meta unavailable)}"
  print -r -- "init_run_configured_model_id=${init_run_configured_model_id:-N/A (why=init-run meta unavailable)}"
  print -r -- "init_run_observable_model_id=${init_run_observable_model_id:-N/A (why=init-run meta unavailable)}"
  print -r -- "init_run_model_id_state=${init_run_model_id_state:-N/A (why=init-run meta unavailable)}"
  print -r -- "init_run_configured_effort=${init_run_configured_effort:-N/A (why=init-run meta unavailable)}"
  print -r -- "init_run_effort_state=${init_run_effort_state:-N/A (why=init-run meta unavailable)}"
  print -r -- "init_run_exit_code=${init_run_exit_code}"
  print -r -- "init_run_outcome=${init_run_outcome}"
  print -r -- "init_run_meta=${init_run_path:-N/A (why=no prior session required)}"

  [[ "$execution_ready" == "true" ]]
}

planveyor_role_runner_preflight() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_role_runner_preflight)" || return $?
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
  local json=0
  local role_arg=""
  local usage="Usage: planveyor_role_runner_preflight <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> [--json]"
  while (( $# > 0 )); do
    case "${1:-}" in
      --json) json=1 ;;
      --help|-h)
        echo "$usage" >&2
        return 0
        ;;
      *)
        if [[ -z "${role_arg//[[:space:]]/}" ]]; then
          role_arg="${1:-}"
        else
          echo "$usage" >&2
          return 2
        fi
        ;;
    esac
    shift
  done

  [[ -n "${role_arg//[[:space:]]/}" ]] || {
    echo "$usage" >&2
    return 2
  }

  local -a payload_args
  payload_args=("${(@f)$(_planveyor_role_runner_preflight_payload_args "$role_arg")}")
  local payload_rc=$?
  if (( json )); then
    _planveyor_role_runner_preflight_emit json "${payload_args[@]}"
  else
    _planveyor_role_runner_preflight_emit plain "${payload_args[@]}"
  fi
  return $payload_rc
}

_planveyor_role_runner_execution_ready_table() {
  local tab=$'\t'
  local -a rows
  rows=("role${tab}runner${tab}execution_ready${tab}reason")
  local role=""
  for role in architect architect_initial architect_censor planner planner_censor coder coder_censor reviewer reviewer_code_risk reviewer_code_contracts; do
    local json=""
    json="$(planveyor_role_runner_preflight "$role" --json 2>/dev/null || true)"
    local row=""
    row="$(_planveyor_py_any - "$json" "$role" <<'PY'
from __future__ import annotations

import json
import sys

try:
    payload = json.loads(sys.argv[1])
except Exception:
    payload = {"role": sys.argv[2], "runner_id": "", "execution_ready": False, "reason": "preflight_readback_error"}
print(
    "\t".join(
        [
            str(payload.get("role") or sys.argv[2]),
            str(payload.get("runner_id") or ""),
            "true" if payload.get("execution_ready") is True else "false",
            str(payload.get("reason") or ""),
        ]
    )
)
PY
)"
    rows+=("$row")
  done

  if command -v column >/dev/null 2>&1; then
    printf '%s\n' "${rows[@]}" | column -t -s $'\t'
  else
    printf '%s\n' "${rows[@]}"
  fi
}

planveyor_runner_matrix() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_runner_matrix)" || return $?
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
  # Shows runner overrides across git worktrees.
  #
  # Usage:
  #   planveyor_runner_matrix
  #   planveyor_runner_matrix planner
  #   planveyor_runner_matrix planner reviewer
  local -a roles
  roles=()
  if (( $# > 0 )); then
    roles=("$@")
  else
    roles=(architect planner coder reviewer manager)
  fi

  local root="$(_planveyor_project_root)" || return $?
  local -a worktrees
  worktrees=("${(@f)$(git -C "$root" worktree list --porcelain 2>/dev/null | rg '^worktree ' | sed 's/^worktree //' || true)}")
  worktrees=("${(@)worktrees:#}")
  (( ${#worktrees} > 0 )) || worktrees=("$root")

  local tab=$'\t'
  local -a rows
  rows=()
  local header="worktree"
  local r
  for r in "${roles[@]}"; do
    local role_id=""
    role_id="$(_planveyor_normalize_role_id "$r" 2>/dev/null || true)"
    [[ -n "${role_id//[[:space:]]/}" ]] || role_id="$r"
    header+="${tab}${role_id}"
  done
  rows+=("$header")

  local wt_path
  for wt_path in "${worktrees[@]}"; do
    [[ -n "${wt_path//[[:space:]]/}" ]] || continue
    local wt_name="${wt_path:t}"
    local row="${wt_name}"
    for r in "${roles[@]}"; do
      local role_id=""
      role_id="$(_planveyor_normalize_role_id "$r" 2>/dev/null || true)"
      if [[ -z "${role_id//[[:space:]]/}" ]]; then
        row+="${tab}-"
        continue
      fi
      local fp="${wt_path}/.planveyor.runner.${role_id}"
      local v="-"
      if [[ -f "$fp" ]]; then
        v="$(_planveyor_read "$fp" 2>/dev/null || true)"
        [[ -n "${v//[[:space:]]/}" ]] || v="-"
      fi
      row+="${tab}${v}"
    done
    rows+=("$row")
  done

  if command -v column >/dev/null 2>&1; then
    printf '%s\n' "${rows[@]}" | column -t -s $'\t'
  else
    printf '%s\n' "${rows[@]}"
  fi
}

planveyor_runner_clear() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_runner_clear)" || return $?
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
  # Clears runner override for a role in the current worktree.
  #
  # Usage:
  #   planveyor_runner_clear planner
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || {
    echo "Usage: planveyor_runner_clear <architect|coder|planner|reviewer|manager>" >&2
    return 1
  }
  local root=""
  root="$(_planveyor_project_root)" || return $?
  root="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "${root//[[:space:]]/}" ]] || {
    echo "ERROR: planveyor_runner_clear must be run inside a git worktree (cd into your planveyor checkout first)." >&2
    return 1
  }
  local wt="$(_planveyor_worktree_id 2>/dev/null || true)"
  [[ -n "${wt//[[:space:]]/}" ]] || wt="${root:t}"

  local file_path="$root/.planveyor.runner.${role_id}"
  local log_path="$root/.planveyor.runner.${role_id}.log"
  if [[ -f "$file_path" ]]; then
    rm -f "$file_path" 2>/dev/null || true
    echo "Cleared: ${file_path} (worktree=${wt})" >&2
  else
    echo "No runner override: ${file_path} (worktree=${wt})" >&2
  fi
  if [[ -f "$log_path" ]]; then
    echo "Note: history kept in ${log_path}" >&2
  fi
}

_planveyor_normalize_profile_mode() {
  # main   = role init/status/resume
  # censor = same-session censor pass
  local v="${1:-main}"
  v="${v//[[:space:]]/}"
  v="${v:l}"
  case "$v" in
    ""|main|run|status|resume|init|default|primary) echo "main" ;;
    censor|check|verify|guard) echo "censor" ;;
    *) return 1 ;;
  esac
}

_planveyor_profile_override_file() {
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || return 1
  local mode_id=""
  mode_id="$(_planveyor_normalize_profile_mode "$2")" || return 1

  local root="$(_planveyor_project_root)" || return $?
  if [[ "$mode_id" == "censor" ]]; then
    echo "$root/.planveyor.profile.${role_id}.censor"
  else
    echo "$root/.planveyor.profile.${role_id}"
  fi
}

_planveyor_profile_role_is_configurable() {
  # Profile overrides are supported only for roles with explicit main/censor wrappers.
  case "${1:-}" in
    architect|coder|planner) return 0 ;;
    *) return 1 ;;
  esac
}

_planveyor_default_codex_profile_for_role_mode() {
  local role_id="" mode_id="" content_profile_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || return 1
  mode_id="$(_planveyor_normalize_profile_mode "$2")" || return 1
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  case "$content_profile_id" in
    planveyor)
      _planveyor_source_module home_runtime.zsh || return $?
      _planveyor_private_home_default_codex_profile_for_role_mode "$role_id" "$mode_id"
      ;;
    *) return 0 ;;
  esac
}

_planveyor_profile_for_role_mode() {
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || return 1
  local mode_id=""
  mode_id="$(_planveyor_normalize_profile_mode "$2")" || return 1

  _planveyor_content_profile_id >/dev/null || return $?
  local file_path=""
  file_path="$(_planveyor_profile_override_file "$role_id" "$mode_id")" || return 1
  if [[ -f "$file_path" ]]; then
    local v=""
    v="$(_planveyor_read "$file_path" 2>/dev/null || true)"
    v="${v//$'\r'/}"
    v="${v//$'\n'/}"
    v="${v//$'\t'/}"
    v="${v//[[:space:]]/}"
    if [[ -n "${v//[[:space:]]/}" ]]; then
      echo "$v"
      return 0
    fi
  fi

  _planveyor_default_codex_profile_for_role_mode "$role_id" "$mode_id"
}

planveyor_profile() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_profile)" || return $?
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
  # Prints effective Codex profile for role/mode in current worktree.
  # Usage:
  #   planveyor_profile planner
  #   planveyor_profile planner censor
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || {
    echo "Usage: planveyor_profile <architect|coder|planner> [main|censor]" >&2
    return 1
  }
  _planveyor_profile_role_is_configurable "$role_id" || {
    echo "Unsupported role for profile overrides: ${role_id} (allowed: architect|coder|planner)" >&2
    return 1
  }
  local mode_id=""
  mode_id="$(_planveyor_normalize_profile_mode "${2:-main}")" || {
    echo "Usage: planveyor_profile <architect|coder|planner> [main|censor]" >&2
    return 1
  }

  _planveyor_profile_for_role_mode "$role_id" "$mode_id"
}

planveyor_profile_set() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_profile_set)" || return $?
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
  # Stores Codex profile override for role/mode in current worktree.
  # Usage:
  #   planveyor_profile_set planner sol-ultra
  #   planveyor_profile_set planner sol-ultra censor
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || {
    echo "Usage: planveyor_profile_set <architect|coder|planner> <PROFILE> [main|censor]" >&2
    return 1
  }
  _planveyor_profile_role_is_configurable "$role_id" || {
    echo "Unsupported role for profile overrides: ${role_id} (allowed: architect|coder|planner)" >&2
    return 1
  }
  local profile_id="${2:-}"
  profile_id="${profile_id//$'\r'/}"
  profile_id="${profile_id//$'\n'/}"
  profile_id="${profile_id//$'\t'/}"
  profile_id="${profile_id//[[:space:]]/}"
  [[ -n "${profile_id//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_profile_set <architect|coder|planner> <PROFILE> [main|censor]" >&2
    return 1
  }
  [[ "$profile_id" =~ '^[A-Za-z0-9._-]+$' ]] || {
    echo "Invalid PROFILE: ${profile_id} (allowed chars: A-Z a-z 0-9 . _ -)" >&2
    return 1
  }
  local mode_id=""
  mode_id="$(_planveyor_normalize_profile_mode "${3:-main}")" || {
    echo "Usage: planveyor_profile_set <architect|coder|planner> <PROFILE> [main|censor]" >&2
    return 1
  }

  local root=""
  root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "${root//[[:space:]]/}" ]] || {
    echo "ERROR: planveyor_profile_set must be run inside a git worktree (cd into your planveyor checkout first)." >&2
    return 1
  }
  local wt="$(_planveyor_worktree_id 2>/dev/null || true)"
  [[ -n "${wt//[[:space:]]/}" ]] || wt="${root:t}"

  local now="$(_planveyor_now)"
  local file_path=""
  file_path="$(_planveyor_profile_override_file "$role_id" "$mode_id")" || return 1
  local log_path="${file_path}.log"
  printf "# %s\n%s\n" "$now" "$profile_id" > "$file_path"
  printf "%s\t%s\t%s\n" "$now" "$mode_id" "$profile_id" >> "$log_path"
  echo "Saved: ${file_path} (${now}; mode=${mode_id}; worktree=${wt})" >&2
}

planveyor_profile_clear() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_profile_clear)" || return $?
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
  # Clears Codex profile override for role/mode in current worktree.
  # Usage:
  #   planveyor_profile_clear planner
  #   planveyor_profile_clear planner censor
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || {
    echo "Usage: planveyor_profile_clear <architect|coder|planner> [main|censor]" >&2
    return 1
  }
  _planveyor_profile_role_is_configurable "$role_id" || {
    echo "Unsupported role for profile overrides: ${role_id} (allowed: architect|coder|planner)" >&2
    return 1
  }
  local mode_id=""
  mode_id="$(_planveyor_normalize_profile_mode "${2:-main}")" || {
    echo "Usage: planveyor_profile_clear <architect|coder|planner> [main|censor]" >&2
    return 1
  }

  local root=""
  root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "${root//[[:space:]]/}" ]] || {
    echo "ERROR: planveyor_profile_clear must be run inside a git worktree (cd into your planveyor checkout first)." >&2
    return 1
  }
  local wt="$(_planveyor_worktree_id 2>/dev/null || true)"
  [[ -n "${wt//[[:space:]]/}" ]] || wt="${root:t}"

  local file_path=""
  file_path="$(_planveyor_profile_override_file "$role_id" "$mode_id")" || return 1
  local log_path="${file_path}.log"
  if [[ -f "$file_path" ]]; then
    rm -f "$file_path" 2>/dev/null || true
    echo "Cleared: ${file_path} (mode=${mode_id}; worktree=${wt})" >&2
  else
    echo "No profile override: ${file_path} (mode=${mode_id}; worktree=${wt})" >&2
  fi
  if [[ -f "$log_path" ]]; then
    echo "Note: history kept in ${log_path}" >&2
  fi
}

_planveyor_repo_profile_id() {
  # A content identity belongs to the selected consumer root.  A pinned child
  # resolves `_planveyor_root` to the physical runtime, so callers that already
  # captured a consumer context pass it explicitly.
  local root="${1:-}"
  [[ -n "${root//[[:space:]]/}" ]] || root="${PLANVEYOR_CTX_ROOT:-}"
  [[ -n "${root//[[:space:]]/}" ]] || root="$(_planveyor_project_root)"
  [[ -d "$root" ]] || return 1

  local consumer_common_dir=""
  consumer_common_dir="$(git -C "$root" rev-parse --git-common-dir 2>/dev/null || true)"
  [[ -n "${consumer_common_dir//[[:space:]]/}" ]] || {
    print -r -- default
    return 0
  }
  [[ "$consumer_common_dir" == /* ]] || consumer_common_dir="${root}/${consumer_common_dir}"
  consumer_common_dir="${consumer_common_dir:A}"

  local runtime_root=""
  runtime_root="$(_planveyor_root 2>/dev/null || true)"
  [[ -n "${runtime_root//[[:space:]]/}" && -d "$runtime_root" ]] || {
    print -r -- default
    return 0
  }
  local runtime_common_dir=""
  runtime_common_dir="$(git -C "$runtime_root" rev-parse --git-common-dir 2>/dev/null || true)"
  [[ -n "${runtime_common_dir//[[:space:]]/}" ]] || {
    print -r -- default
    return 0
  }
  [[ "$runtime_common_dir" == /* ]] || runtime_common_dir="${runtime_root}/${runtime_common_dir}"
  runtime_common_dir="${runtime_common_dir:A}"

  if [[ "$consumer_common_dir" == "$runtime_common_dir" ]]; then
    print -r -- planveyor
  else
    print -r -- default
  fi
}
_planveyor_content_profile_id() {
  local context_json="" context_tuple=""
  context_json="$(_planveyor_authority_context_for_reader _planveyor_content_profile_id)" || return $?
  context_tuple="$(_planveyor_authority_context_bindings "$context_json")" || return $?
  local context_state="" context_root="" context_generation="" remainder=""
  IFS=$'\t' read -r context_state context_root context_generation remainder <<< "$context_tuple" || return 1
  [[ -z "$remainder" && ( "$context_state" == legacy || "$context_state" == engaged ) ]] || return 1
  if [[ "$context_state" == engaged ]]; then
    # Consumer-owned content is selected only through an engaged contract.
    # The corresponding readers use declared contract carriers and never
    # guess a profile tree beneath either the consumer or this runtime.
    print -r -- target-local
    return 0
  fi

  local physical_profile=""
  physical_profile="$(_planveyor_repo_profile_id "$context_root")" || return $?
  case "$physical_profile" in
    planveyor) print -r -- planveyor ;;
    # Router is a behavior restriction, not a second public content corpus.
    *) print -r -- default ;;
  esac
}


_planveyor_prompt_filename_for_role_phase() {
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || return 1
  local phase_id="${2:-}"
  phase_id="${phase_id:l}"
  phase_id="${phase_id//-/_}"
  phase_id="${phase_id// /_}"

  case "${role_id}:${phase_id}" in
    architect:init) echo "architect_init.md" ;;
    architect:draft_discussion) echo "architect_draft_discussion.md" ;;
    architect:status_driven) echo "architect_status_driven.md" ;;
    architect:censor) echo "architect_censor.md" ;;
    architect:merge_notes) echo "architect_merge_notes.md" ;;
    architect:plan_harvest) echo "architect_plan_harvest.md" ;;
    architect:post_merge_audit) echo "architect_post_merge_audit.md" ;;
    architect:canon_sweep) echo "architect_canon_sweep.md" ;;
    architect:docs_finalize_general) echo "architect_docs_finalize_general.md" ;;
    architect:docs_finalize_followups) echo "architect_docs_finalize_followups.md" ;;
    architect:track_process_roles) echo "architect_track_process_roles.md" ;;
    architect:track_process_collab) echo "architect_track_process_collab.md" ;;
    architect:track_innovations) echo "architect_track_innovations.md" ;;
    planner:init) echo "planner_init.md" ;;
    planner:status_driven) echo "planner_status_driven.md" ;;
    planner:censor) echo "planner_censor.md" ;;
    planner:docs_finalize_general) echo "planner_docs_finalize_general.md" ;;
    planner:docs_finalize_followups) echo "planner_docs_finalize_followups.md" ;;
    coder:init) echo "coder_init.md" ;;
    coder:status_driven) echo "coder_status_driven.md" ;;
    coder:censor) echo "coder_censor.md" ;;
    coder:docs_finalize_general) echo "coder_docs_finalize_general.md" ;;
    coder:docs_finalize_followups) echo "coder_docs_finalize_followups.md" ;;
    coder:migrations_gate) echo "coder_migrations_gate.md" ;;
    coder:merge_conflicts) echo "coder_merge_conflicts.md" ;;
    reviewer:init) echo "reviewer_init.md" ;;
    reviewer:status_driven) echo "reviewer_status_driven.md" ;;
    reviewer:docs_finalize_general) echo "reviewer_docs_finalize_general.md" ;;
    reviewer:docs_finalize_followups) echo "reviewer_docs_finalize_followups.md" ;;
    manager:init) echo "manager_init.md" ;;
    manager:router) echo "manager_router.md" ;;
    manager:collab_pipeline) echo "manager_collab_pipeline.md" ;;
    manager:custom_pipeline) echo "manager_custom_pipeline.md" ;;
    manager:merge_pipeline|manager:collab_merge_pipeline) echo "manager_collab_merge_pipeline.md" ;;
    *) return 1 ;;
  esac
}

_planveyor_prompt_file_for_role_phase() {
  local filename=""
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_prompt_file_for_role_phase)" || return $?
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
  filename="$(_planveyor_prompt_filename_for_role_phase "$1" "$2")" || return 1

  # A direct prompt lookup is a content-reader boundary too.  Bind its own
  # local copy so profile fallbacks cannot select tooling bytes after a target
  # marker has engaged authority.
  _planveyor_content_profile_id >/dev/null || return $?
  if [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
    local role_id=""
    role_id="$(_planveyor_normalize_role_id "$1")" || return 1
    _planveyor_contract_path "docs/roles/${role_id}.md" role_prompt_role >/dev/null || return $?
    _planveyor_contract_path 'docs/playbooks/docs_architecture.md' role_prompt_architecture >/dev/null || return $?
    _planveyor_contract_path "docs/tools/prompts/${filename}" role_prompt
    return $?
  fi

  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  case "$content_profile_id" in
    default|planveyor)
      # Both source-local public identities deliberately share the root corpus.
      # There is no Planveyor profile subtree to recreate or silently fall back
      # to after an OSS extraction.
      local role_id="" required_source="" prompt_path=""
      role_id="$(_planveyor_normalize_role_id "$1")" || return 1
      for required_source in \
        "$(_planveyor_root)/docs/roles/${role_id}.md" \
        "$(_planveyor_root)/docs/playbooks/docs_architecture.md"; do
        [[ -f "$required_source" ]] || {
          print -u2 -r -- "planveyor: missing required public source: ${required_source}"
          return 1
        }
      done
      prompt_path="$(_planveyor_prompts_root)/${filename}"
      [[ -f "$prompt_path" ]] || {
        print -u2 -r -- "planveyor: missing required public prompt: ${prompt_path}"
        return 1
      }
      print -r -- "$prompt_path"
      return 0
      ;;
    target-local)
      # An engaged context returned above is the only legal target-local read.
      print -u2 -r -- 'planveyor: target-local prompts require an engaged consumer contract'
      return 1
      ;;
    *)
      print -u2 -r -- "planveyor: unsupported public content profile: ${content_profile_id}"
      return 1
      ;;
  esac
}

_planveyor_role_prompt_body() {
  local role_id=""
  local phase_id="${2:-}"
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_role_prompt_body)" || return $?
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
  # Current sibling authority is a readonly local from the actual adapter
  # call stack. Ambient/exported selectors never select commit policy.
  local commit_policy=native_existing
  if (( ${funcstack[(Ie)planveyor_sibling]} > 0 )); then
    if [[ ${(t)PLANVEYOR_SIBLING_COMMIT_POLICY-} != scalar-local-readonly ||
          "${PLANVEYOR_SIBLING_COMMIT_POLICY:-}" != (human_explicit|native_existing) ]]; then
      print -u2 -r -- 'planveyor sibling: invalid invocation commit policy'
      return 3
    fi
    commit_policy="$PLANVEYOR_SIBLING_COMMIT_POLICY"
  fi
  role_id="$(_planveyor_normalize_role_id "${1:-}")" || return 1
  [[ -n "${phase_id//[[:space:]]/}" ]] || return 1


  local prompt_file=""
  prompt_file="$(_planveyor_prompt_file_for_role_phase "$role_id" "$phase_id")" || return 1
  local runtime_root=""
  runtime_root="$(_planveyor_root)" || return 1
  print -r -- "COMMIT_POLICY=${commit_policy}"
  print -r -- "PLANVEYOR_RUNTIME_ROOT=${runtime_root}"
  if [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
    _planveyor_contract_read "docs/tools/prompts/${prompt_file:t}" role_prompt_body
  else
    cat -- "$prompt_file"
  fi
}

_planveyor_manager_prompt_body_still_current() {
  emulate -L zsh
  local phase="${1:-}" prepared="${2:-}" current=""
  [[ -n "${phase//[[:space:]]/}" && -n "${prepared//[[:space:]]/}" ]] || return 1
  current="$(_planveyor_role_prompt_body manager "$phase")" || return $?
  [[ "$current" == "$prepared" ]] || {
    print -u2 -r -- "planveyor: Manager prompt changed before native dispatch"
    return 1
  }
}

_planveyor_review_template_source_path() {
  # Shared defaults and optional profile overrides for review/report templates
  # live in planveyor. Repo-local copies in sibling repos are mirrors, not
  # a second canon.
  local family="${1:-}"
  local filename="${2:-}"
  [[ -n "${family//[[:space:]]/}" && -n "${filename//[[:space:]]/}" ]] || return 1
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_review_template_source_path)" || return $?
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

  case "$family" in
    reviews|code_reviews|doc_reviews) ;;
    *)
      echo "Unsupported review template family: ${family}" >&2
      return 1
      ;;
  esac

  if [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
    _planveyor_contract_path "docs/${family}/${filename}" review_template
    return $?
  fi

  local base_dir="$(_planveyor_root)/docs/${family}"
  local profile_id=""
  profile_id="$(_planveyor_content_profile_id)"
  if [[ -n "${profile_id//[[:space:]]/}" && "$profile_id" != "default" ]]; then
    local override_path="${base_dir}/profiles/${profile_id}/${filename}"
    if [[ -f "$override_path" ]]; then
      echo "$override_path"
      return 0
    fi
  fi

  local shared_path="${base_dir}/${filename}"
  [[ -f "$shared_path" ]] || {
    echo "Missing shared default template: ${shared_path}" >&2
    return 1
  }
  echo "$shared_path"
}

_planveyor_copy_review_template_if_missing() {
  local output_path="${1:-}"
  local family="${2:-}"
  local filename="${3:-}"
  [[ -n "${output_path//[[:space:]]/}" ]] || return 1
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_copy_review_template_if_missing)" || return $?
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
  [[ -f "$output_path" ]] && return 0

  local source_path=""
  source_path="$(_planveyor_review_template_source_path "$family" "$filename")" || return 1
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  cp "$source_path" "$output_path"
}

_planveyor_doc_template_source_path() {
  local family="${1:-}"
  local filename="${2:-}"
  [[ -n "${family//[[:space:]]/}" && -n "${filename//[[:space:]]/}" ]] || return 1

  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_doc_template_source_path)" || return $?
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
  if [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
    _planveyor_contract_path "docs/${family}/${filename}" doc_template
    return $?
  fi

  local root="$(_planveyor_root)"
  local repo_path="${root}/docs/${family}/${filename}"
  local shared_path="$(_planveyor_root)/docs/${family}/${filename}"

  case "${family}/${filename}" in
    plans/_template.md|code_drafts/_template.md)
      [[ -f "$shared_path" ]] || {
        echo "Missing shared doc template: ${shared_path} (repo mirror is not source authority for ${family}/${filename})" >&2
        return 1
      }
      echo "$shared_path"
      return 0
      ;;
  esac

  if [[ -f "$repo_path" ]]; then
    echo "$repo_path"
    return 0
  fi

  [[ -f "$shared_path" ]] || {
    echo "Missing doc template: repo=${repo_path} shared=${shared_path}" >&2
    return 1
  }
  echo "$shared_path"
}

_planveyor_copy_doc_template_if_missing() {
  local output_path="${1:-}"
  local family="${2:-}"
  local filename="${3:-}"
  [[ -n "${output_path//[[:space:]]/}" ]] || return 1
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_copy_doc_template_if_missing)" || return $?
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
  [[ -f "$output_path" ]] && return 0

  local source_path=""
  source_path="$(_planveyor_doc_template_source_path "$family" "$filename")" || return 1
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  cp "$source_path" "$output_path"
}

planveyor_role_bundle_prompt_manifest() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_role_bundle_prompt_manifest)" || return $?
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
  local roles=("$@")
  if (( ${#roles[@]} == 0 )); then
    roles=(architect planner coder reviewer)
  fi

  local profile_id=""
  profile_id="$(_planveyor_repo_profile_id 2>/dev/null || true)"
  [[ -n "${profile_id//[[:space:]]/}" ]] || profile_id="default"
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  printf 'repo_profile_id\t%s\n' "$profile_id"
  printf 'content_profile_id\t%s\n' "$content_profile_id"

  local role_id=""
  local prompt_file=""
  local raw_role=""
  for raw_role in "${roles[@]}"; do
    role_id="$(_planveyor_normalize_role_id "$raw_role")" || return 1
    prompt_file="$(_planveyor_prompt_file_for_role_phase "$role_id" init)" || return 1
    printf '%s\t%s\n' "$role_id" "$prompt_file"
  done
}

_planveyor_pybin_requirement_for_role() {
  _planveyor_normalize_role_id "$1" >/dev/null || return 1
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  case "$content_profile_id" in
    planveyor) print -r -- required ;;
    *) print -r -- optional ;;
  esac
}

_planveyor_resolve_pybin_for_role() {
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || return 1
  local requirement=""
  requirement="$(_planveyor_pybin_requirement_for_role "$role_id")" || return 1
  if [[ "$requirement" == "required" ]]; then
    _planveyor_get_pybin
    return $?
  fi
  _planveyor_get_pybin 2>/dev/null || true
}

_planveyor_role_bundle_output_dir() {
  # Generated bundles are consumer-project artifacts.  `_planveyor_root`
  # resolves the physical runtime once loaded by the child launcher, so it
  # must not choose where a consumer project's diagnostics are written.
  local consumer_root="${PLANVEYOR_CTX_ROOT:-}"
  if [[ -z "${consumer_root//[[:space:]]/}" || "$consumer_root" != /* || ! -d "$consumer_root" ]]; then
    local context_json="" context_tuple="" context_state="" context_generation="" context_remainder=""
    context_json="$(_planveyor_authority_context_for_reader _planveyor_role_bundle_output_dir 2>/dev/null || true)"
    if [[ -n "${context_json//[[:space:]]/}" ]]; then
      context_tuple="$(_planveyor_authority_context_bindings "$context_json" 2>/dev/null || true)"
      IFS=$'\t' read -r context_state consumer_root context_generation context_remainder <<< "$context_tuple" || consumer_root=""
      [[ -z "${context_remainder:-}" && ( "$context_state" == legacy || "$context_state" == engaged ) && -n "${consumer_root//[[:space:]]/}" && "$consumer_root" == /* && ${#context_generation} -eq 64 && "$context_generation" != *[^0-9A-Fa-f]* ]] || consumer_root=""
    fi
  fi
  [[ -n "${consumer_root//[[:space:]]/}" ]] || consumer_root="$(_planveyor_project_root)" || return $?
  print -r -- "${consumer_root}/.tmp/role_bundles"
}

_planveyor_role_bundle_output_path() {
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "$1")" || return 1
  echo "$(_planveyor_role_bundle_output_dir)/${role_id}.xml"
}

_planveyor_role_bundle_diagnostic_excerpt() {
  local file="${1:-}"
  [[ -s "$file" ]] || return 0

  # Builder output may name both the consumer repository and the physical
  # runtime.  A pinned child makes `_planveyor_root` the runtime, so obtain the
  # consumer path from the same authority context used for the output folder.
  local repo_root="${PLANVEYOR_CTX_ROOT:-}"
  if [[ -z "${repo_root//[[:space:]]/}" || "$repo_root" != /* || ! -d "$repo_root" ]]; then
    local context_json="" context_tuple="" context_state="" context_generation="" context_remainder=""
    context_json="$(_planveyor_authority_context_for_reader _planveyor_role_bundle_diagnostic_excerpt 2>/dev/null || true)"
    if [[ -n "${context_json//[[:space:]]/}" ]]; then
      context_tuple="$(_planveyor_authority_context_bindings "$context_json" 2>/dev/null || true)"
      IFS=$'\t' read -r context_state repo_root context_generation context_remainder <<< "$context_tuple" || repo_root=""
      [[ -z "${context_remainder:-}" && ( "$context_state" == legacy || "$context_state" == engaged ) && -n "${repo_root//[[:space:]]/}" && "$repo_root" == /* && ${#context_generation} -eq 64 && "$context_generation" != *[^0-9A-Fa-f]* ]] || repo_root=""
    fi
  fi
  [[ -n "${repo_root//[[:space:]]/}" ]] || repo_root="$(_planveyor_root 2>/dev/null || true)"
  local tooling_root=""
  tooling_root="$(_planveyor_authority_runtime_root_loaded 2>/dev/null || _planveyor_root 2>/dev/null || true)"
  local home_root="${HOME:-}"
  local line=""

  sed -n '1,20p' "$file" | while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -n "${tooling_root//[[:space:]]/}" ]] && line="${line//$tooling_root/tooling:}"
    [[ -n "${repo_root//[[:space:]]/}" ]] && line="${line//$repo_root/repo:}"
    [[ -n "${home_root//[[:space:]]/}" ]] && line="${line//$home_root/~}"
    print -r -- "$line"
  done
}

_planveyor_prepare_role_bundle() {
  local role_id=""
  local authority_context=""
  authority_context="$(_planveyor_authority_context_for_reader _planveyor_prepare_role_bundle)" || return $?
  local authority_tuple=""
  authority_tuple="$(_planveyor_authority_context_bindings "$authority_context")" || return $?
  local authority_state="" authority_root="" authority_generation="" authority_remainder=""
  IFS=$'\t' read -r authority_state authority_root authority_generation authority_remainder <<< "$authority_tuple" || return 1
  [[ -z "${authority_remainder:-}" && ( "$authority_state" == legacy || "$authority_state" == engaged ) && -n "${authority_root//[[:space:]]/}" && ${#authority_generation} -eq 64 && "$authority_generation" != *[^0-9A-Fa-f]* ]] || return 1
  local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
  local -r PLANVEYOR_CTX_ROOT="$authority_root"
  local -r PLANVEYOR_CTX_GENERATION="$authority_generation"
  local -r PLANVEYOR_CTX_JSON="$authority_context"
  local -r PLANVEYOR_CTX_STATE="$authority_state"
  local pybin="${2:-}"
  local build_py="${pybin:-python3}"
  role_id="$(_planveyor_normalize_role_id "$1")" || return 1
  local _PLANVEYOR_AUTHORITY_CONTEXT_V1
  [[ "$authority_state" == engaged ]] && typeset -x _PLANVEYOR_AUTHORITY_CONTEXT_V1="$authority_context"
  local builder=""
  builder="$(_planveyor_script build_role_bundles.py)"
  local out_dir=""
  out_dir="$(_planveyor_role_bundle_output_dir)"
  local bundle_path=""
  bundle_path="$(_planveyor_role_bundle_output_path "$role_id")" || return 1

  unset ROLE_BUNDLE_PATH
  if [[ ! -f "$builder" ]]; then
    [[ "$authority_state" == engaged ]] && {
      echo "ERROR: missing required role bundle builder: ${builder}" >&2
      return 1
    }
    return 0
  fi

  _planveyor_authority_before_effect_json "$authority_context" >/dev/null || return $?
  mkdir -p "$out_dir" 2>/dev/null || true
  local diagnostic_path="${out_dir}/${role_id}.refresh.log"
  local diagnostic_ref=".tmp/role_bundles/${role_id}.refresh.log"
  local bundle_ref=".tmp/role_bundles/${role_id}.xml"
  local tmp_stdout="${out_dir}/${role_id}.refresh.stdout.tmp"
  local tmp_stderr="${out_dir}/${role_id}.refresh.stderr.tmp"
  rm -f "$diagnostic_path" "$tmp_stdout" "$tmp_stderr" 2>/dev/null || true

  local build_rc=""
  if _planveyor_python_dispatch "$build_py" "$builder" --role "$role_id" --out-dir "$out_dir" >"$tmp_stdout" 2>"$tmp_stderr"; then
    if [[ -f "$bundle_path" ]]; then
      export ROLE_BUNDLE_PATH="$bundle_path"
      rm -f "$tmp_stdout" "$tmp_stderr" 2>/dev/null || true
      return 0
    fi
    {
      print -r -- "status=no_bundle"
      print -r -- "role=${role_id}"
      print -r -- "message=builder exited successfully but expected XML bundle was not written"
      print -r -- "expected=${bundle_ref}"
      if [[ -s "$tmp_stdout" ]]; then
        print -r -- "stdout_excerpt:"
        _planveyor_role_bundle_diagnostic_excerpt "$tmp_stdout"
      fi
      if [[ -s "$tmp_stderr" ]]; then
        print -r -- "stderr_excerpt:"
        _planveyor_role_bundle_diagnostic_excerpt "$tmp_stderr"
      fi
    } >"$diagnostic_path" 2>/dev/null || true
    rm -f "$tmp_stdout" "$tmp_stderr" 2>/dev/null || true
    if [[ "$authority_state" == engaged ]]; then
      echo "ERROR: required role bundle XML was not written for role=${role_id}. Diagnostic: ${diagnostic_ref}" >&2
      return 1
    fi
    echo "⚠️ Runtime bundle refresh produced no XML for role=${role_id}; continuing with raw-doc bootstrap. Diagnostic: ${diagnostic_ref}" >&2
    return 0
  else
    build_rc=$?
  fi

  {
    print -r -- "status=failed"
    print -r -- "role=${role_id}"
    print -r -- "exit_code=${build_rc}"
    print -r -- "message=builder failed; raw-doc bootstrap remains active"
    if [[ -s "$tmp_stderr" ]]; then
      print -r -- "stderr_excerpt:"
      _planveyor_role_bundle_diagnostic_excerpt "$tmp_stderr"
    fi
    if [[ -s "$tmp_stdout" ]]; then
      print -r -- "stdout_excerpt:"
      _planveyor_role_bundle_diagnostic_excerpt "$tmp_stdout"
    fi
  } >"$diagnostic_path" 2>/dev/null || true
  rm -f "$tmp_stdout" "$tmp_stderr" 2>/dev/null || true
  if [[ "$authority_state" == engaged ]]; then
    echo "ERROR: required role bundle refresh failed for role=${role_id}. Diagnostic: ${diagnostic_ref}" >&2
    return 1
  fi
  echo "⚠️ Runtime bundle refresh failed for role=${role_id}; continuing with raw-doc bootstrap. Diagnostic: ${diagnostic_ref}" >&2
  return 0
}

_planveyor_with_role_env() {
  local role_id=""
  role_id="$(_planveyor_normalize_role_id "${1:-}")" || return $?
  local pybin="${2:-}"
  shift 2
  if [[ -n "${pybin//[[:space:]]/}" ]]; then
    PYBIN="$pybin" "$@"
    return $?
  fi
  "$@"
}
_planveyor_manager_merge_payload() {
  local pybin="${1:-}"
  local cmd_line="${2:-}"
  [[ -n "${cmd_line//[[:space:]]/}" ]] || return 1

  local prompt_body="${3:-}"
  if [[ -z "${prompt_body//[[:space:]]/}" ]]; then
    prompt_body="$(_planveyor_role_prompt_body manager collab_merge_pipeline)" || return $?
  fi
  {
    echo "ROLE=Manager"
    echo "MERGE_MODE=1"
    [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"
    printf '%s\n' "$prompt_body"
    echo ""
    echo "${cmd_line}"
  }
}

_planveyor_extract_session_id() {
  # Best-effort extraction of a UUID from tool output.
  # Codex prints `session id: <uuid>` in its banner; prefer that line, because
  # the banner's workdir or the prompt may carry another UUID first. Without it,
  # take the first UUID, which usually matches Claude Code resume ids.
  local text="$1"
  local uuid_re="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
  local sid=""
  sid="$(printf '%s\n' "$text" | rg -o -r '$1' "^[[:space:]]*session id:[[:space:]]*(${uuid_re})" | head -n 1 || true)"
  if [[ -z "${sid//[[:space:]]/}" ]]; then
    sid="$(printf '%s' "$text" | rg -o "$uuid_re" | head -n 1 || true)"
  fi
  [[ -n "${sid//[[:space:]]/}" ]] && echo "$sid"
}

_planveyor_uuid4() {
  if command -v uuidgen >/dev/null 2>&1; then
    uuidgen | tr '[:upper:]' '[:lower:]'
    return 0
  fi

  _planveyor_py - <<'PY'
import uuid
print(uuid.uuid4())
PY
}

_planveyor_is_uuid() {
  local v="${1//[[:space:]]/}"
  [[ "$v" =~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' ]]
}

_planveyor_get_range_base() {
  local root="$(_planveyor_project_root)" || return 1
  local file_path="$root/.planveyor.range.base"
  [[ -f "$file_path" ]] || {
    echo "Missing BASE sha. Set range first: planveyor_range_set <BASE_SHA> <HEAD_SHA> [MERGE_SHA]" >&2
    return 1
  }
  _planveyor_read "$file_path"
}

_planveyor_get_range_head() {
  local root="$(_planveyor_project_root)" || return 1
  local file_path="$root/.planveyor.range.head"
  [[ -f "$file_path" ]] || {
    echo "Missing HEAD sha. Set range first: planveyor_range_set <BASE_SHA> <HEAD_SHA> [MERGE_SHA]" >&2
    return 1
  }
  _planveyor_read "$file_path"
}

planveyor_range_set() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_range_set)" || return $?
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
  # Usage: planveyor_range_set <BASE_SHA> <HEAD_SHA> [MERGE_SHA]
  local base="${1:-}"
  local head="${2:-}"
  local merge="${3:-}"
  [[ -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_range_set <BASE_SHA> <HEAD_SHA> [MERGE_SHA]" >&2
    return 1
  }

  local root="$(_planveyor_project_root)" || return 1
  local now="$(_planveyor_now)"
  local base_path="$root/.planveyor.range.base"
  local head_path="$root/.planveyor.range.head"
  local merge_path="$root/.planveyor.range.merge"
  local log_path="$root/.planveyor.range.log"

  printf "# %s\n%s\n" "$now" "$base" > "$base_path"
  printf "# %s\n%s\n" "$now" "$head" > "$head_path"
  if [[ -n "${merge//[[:space:]]/}" ]]; then
    printf "# %s\n%s\n" "$now" "$merge" > "$merge_path"
  else
    rm -f "$merge_path" 2>/dev/null || true
  fi

  printf "%s\t%s\t%s\t%s\n" "$now" "$base" "$head" "${merge:-}" >> "$log_path"
  echo "Saved range: ${base}..${head} (${now})" >&2
}

planveyor_range_set_merge() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_range_set_merge)" || return $?
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
  # Usage: planveyor_range_set_merge <MERGE_SHA> [HEAD_SHA]
  # Sets BASE from MERGE_SHA^1, HEAD defaults to MERGE_SHA, stores MERGE_SHA as merge anchor.
  local merge="${1:-}"
  local head="${2:-}"
  [[ -n "${merge//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_range_set_merge <MERGE_SHA> [HEAD_SHA]" >&2
    return 1
  }
  [[ -n "${head//[[:space:]]/}" ]] || head="$merge"

  local root="$(_planveyor_project_root)" || return 1
  pushd "$root" >/dev/null || return 1
  local base=""
  base="$(git rev-parse "${merge}^1" 2>/dev/null || true)"
  popd >/dev/null || return 1
  [[ -n "${base//[[:space:]]/}" ]] || {
    echo "Invalid MERGE_SHA (cannot resolve ${merge}^1). Use planveyor_range_set BASE HEAD [MERGE] instead." >&2
    return 1
  }

  planveyor_range_set "$base" "$head" "$merge"
}

planveyor_range_set_auto_merge() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_range_set_auto_merge)" || return $?
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
  # Best-effort auto-range for merge-tracker workflow.
  #
  # Usage:
  #   planveyor_range_set_auto_merge            # uses latest merge commit; BASE from previous HEAD if valid, else MERGE_SHA^1
  #   planveyor_range_set_auto_merge <MERGE_SHA>
  local merge="${1:-}"

  local root="$(_planveyor_project_root)" || return 1
  pushd "$root" >/dev/null || return 1

  if [[ -z "${merge//[[:space:]]/}" ]]; then
    local head_sha=""
    head_sha="$(git rev-parse HEAD 2>/dev/null || true)"
    if [[ -n "${head_sha//[[:space:]]/}" ]]; then
      local parents=""
      parents="$(git show -s --pretty=%P "$head_sha" 2>/dev/null || true)"
      if [[ -n "${parents//[[:space:]]/}" && "$(wc -w <<<"$parents" | tr -d ' ')" -ge 2 ]]; then
        merge="$head_sha"
      fi
    fi

    if [[ -z "${merge//[[:space:]]/}" ]]; then
      merge="$(git rev-list --merges -n 1 HEAD 2>/dev/null || true)"
    fi
  fi

  [[ -n "${merge//[[:space:]]/}" ]] || {
    echo "Cannot auto-detect MERGE_SHA (no merge commits found). Set manually: planveyor_range_set_merge <MERGE_SHA>" >&2
    popd >/dev/null || return 1
    return 1
  }

  local prev_head=""
  prev_head="$(planveyor_range_head 2>/dev/null || true)"
  [[ "$prev_head" == "<HEAD_SHA>" ]] && prev_head=""

  local base=""
  if [[ -n "${prev_head//[[:space:]]/}" ]]; then
    if git merge-base --is-ancestor "$prev_head" "$merge" 2>/dev/null; then
      base="$prev_head"
    fi
  fi

  if [[ -z "${base//[[:space:]]/}" ]]; then
    base="$(git rev-parse "${merge}^1" 2>/dev/null || true)"
  fi
  [[ -n "${base//[[:space:]]/}" ]] || {
    echo "Invalid MERGE_SHA (cannot resolve ${merge}^1). Set manually: planveyor_range_set_merge <MERGE_SHA>" >&2
    popd >/dev/null || return 1
    return 1
  }

  popd >/dev/null || return 1
  planveyor_range_set "$base" "$merge" "$merge"
}

planveyor_merge_range_stats_json() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_range_stats_json)" || return $?
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
  # Emits normalized helper-backed stats for a merge/review range.
  # Usage:
  #   planveyor_merge_range_stats_json
  #   planveyor_merge_range_stats_json BASE..HEAD
  #   planveyor_merge_range_stats_json BASE HEAD
  local base=""
  local head=""
  if [[ $# -eq 0 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
  elif [[ $# -eq 1 && "${1:-}" == *..* ]]; then
    local range_arg="${1:-}"
    base="${range_arg%%..*}"
    head="${range_arg#*..}"
  elif [[ $# -eq 2 ]]; then
    base="${1:-}"
    head="${2:-}"
  else
    echo "Usage: planveyor_merge_range_stats_json [BASE..HEAD | BASE HEAD]" >&2
    return 1
  fi
  [[ -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_merge_range_stats_json [BASE..HEAD | BASE HEAD]" >&2
    return 1
  }

  local root="$(_planveyor_project_root)" || return 1
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any - "$base" "$head" <<'PY'
from __future__ import annotations

import json
import re
import subprocess
import sys

base_ref, head_ref = sys.argv[1:3]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


base = git("rev-parse", base_ref)
head = git("rev-parse", head_ref)
range_ref = f"{base}..{head}"
total_commits = int(git("rev-list", "--count", range_ref) or "0")
first_parent_commits = int(git("rev-list", "--first-parent", "--count", range_ref) or "0")
changed_paths = [
    line
    for line in git("diff", "--name-only", range_ref).splitlines()
    if line.strip()
]
shortstat = git("diff", "--shortstat", range_ref)
if not shortstat:
    shortstat = "0 files changed, 0 insertions(+), 0 deletions(-)"


def _extract(pattern: str) -> int:
    match = re.search(pattern, shortstat)
    return int(match.group(1)) if match else 0


files_changed = _extract(r"(\d+)\s+files?\s+changed")
insertions = _extract(r"(\d+)\s+insertions?\(\+\)")
deletions = _extract(r"(\d+)\s+deletions?\(-\)")
payload = {
    "range": range_ref,
    "base": base,
    "head": head,
    "base_short": base[:7],
    "head_short": head[:7],
    "range_id": f"range_{base[:7]}_{head[:7]}",
    "total_commits": total_commits,
    "first_parent_commits": first_parent_commits,
    "changed_files": len(changed_paths),
    "diffstat_summary": shortstat,
    "diffstat": {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
    },
    "labels": {
        "total_commits": "total commits",
        "first_parent_commits": "first-parent commits",
        "changed_files": "changed files",
        "diffstat_summary": "diffstat summary",
    },
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

_planveyor_merge_range_stats_json() { planveyor_merge_range_stats_json "$@"; }

_planveyor_merge_tracker_path() {
  local root=""
  root="$(_planveyor_project_root)" || return $?
  printf '%s/.planveyor.merge_tracker.md\n' "$root"
}
_planveyor_merge_policy_script() { _planveyor_script merge_gate_policy.py; }
_planveyor_merge_policy_mode() {
  local root="$1"
  _planveyor_py_any "$(_planveyor_merge_policy_script)" --root "$root" mode
}
_planveyor_merge_policy_metadata() {
  local root="$1"
  _planveyor_py_any "$(_planveyor_merge_policy_script)" --root "$root" metadata
}
_planveyor_merge_policy_step_keys() {
  local root="$1"
  _planveyor_py_any "$(_planveyor_merge_policy_script)" --root "$root" step-keys
}
_planveyor_merge_policy_render() {
  local root="$1" step="$2"
  _planveyor_py_any "$(_planveyor_merge_policy_script)" --root "$root" render --step "$step"
}
_planveyor_merge_policy_validate_tracker() {
  local root="$1" tracker_path="$2" validation_mode="${3:-validate}"
  _planveyor_py_any "$(_planveyor_merge_policy_script)" --root "$root" --tracker "$tracker_path" "$validation_mode"
}
_planveyor_merge_tracker_backup_path() {
  local root="$(_planveyor_project_root)" || return 1
  local ts; ts="$(date +%y%m%d_%H%M)"
  echo "${root}/.planveyor.merge_tracker.prev_${ts}.md"
}

_planveyor_tracker_is_checked() {
  local tracker_path="$1"
  local key="$2"
  [[ -f "$tracker_path" ]] || return 1
  rg -q "^[[:space:]]*- \\[[xX]\\] ${key}([[:space:]]|\$)" "$tracker_path" 2>/dev/null
}

_planveyor_tracker_first_unchecked_key() {
  local tracker_path="$1"
  [[ -f "$tracker_path" ]] || return 1
  local line=""
  line="$(rg -n "^[[:space:]]*- \\[ \\] step:" "$tracker_path" 2>/dev/null | head -n 1 || true)"
  [[ -n "${line//[[:space:]]/}" ]] || return 1
  line="${line#*:}"
  line="${line#"${line%%[![:space:]]*}"}"
  if [[ "${line[1,6]}" == "- [ ] " ]]; then
    line="${line[7,-1]}"
  fi
  line="${line%"${line##*[![:space:]]}"}"
  [[ -n "${line//[[:space:]]/}" ]] || return 1
  echo "$line"
}

_planveyor_tracker_header_value() {
  # Reads KEY=... lines from tracker header.
  local tracker_path="$1"
  local key="$2"
  [[ -f "$tracker_path" ]] || return 1
  local line=""
  line="$(rg -n "^${key}=" "$tracker_path" 2>/dev/null | head -n 1 || true)"
  [[ -n "${line//[[:space:]]/}" ]] || return 1
  line="${line#*:}"
  line="${line#${key}=}"
  line="${line//$'\r'/}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -n "${line//[[:space:]]/}" ]] || return 1
  echo "$line"
}

_planveyor_merge_tracker_step_keys() {
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  case "$content_profile_id" in
    default|planveyor)
      printf '%s\n' \
        "step:review_range" \
        "step:merge_notes" \
        "step:plan_harvest" \
        "step:canon_sweep" \
        "step:packetization_gate" \
        "step:docs_finalize" \
        "step:doc_lint" \
        "step:post_merge_audit" \
        "step:docs_hygiene_archive" \
        "step:docs_hygiene_suggest" \
        "step:ready_to_push"
      ;;
    *)
      printf '%s\n' \
        "step:review_range" \
        "step:merge_notes" \
        "step:plan_harvest" \
        "step:canon_sweep" \
        "step:packetization_gate" \
        "step:docs_finalize" \
        "step:doc_lint" \
        "step:post_merge_audit" \
        "step:docs_hygiene_archive" \
        "step:docs_hygiene_suggest" \
        "step:ready_to_push"
      ;;
  esac
}

_planveyor_merge_tracker_write_checklist() {
  local root="${1:-}" merge_policy_mode="${2:-legacy}" captured_steps="${3:-}"
  local step=""
  if [[ "$merge_policy_mode" == engaged && $# -ge 3 ]]; then
    while IFS= read -r step; do
      [[ -n "${step//[[:space:]]/}" ]] || continue
      printf -- '- [ ] %s\n' "$step"
    done <<< "$captured_steps"
    return 0
  fi
  while IFS= read -r step; do
    [[ -n "${step//[[:space:]]/}" ]] || continue
    printf -- '- [ ] %s\n' "$step"
  done < <(
    if [[ "$merge_policy_mode" == engaged ]]; then
      _planveyor_merge_policy_step_keys "$root"
    else
      _planveyor_merge_tracker_step_keys
    fi
  )
}

_planveyor_merge_tracker_matches_profile() {
  local tracker_path="$1" merge_policy_mode="${2:-legacy}" root="${3:-}"
  [[ -f "$tracker_path" ]] || return 1

  if [[ "$merge_policy_mode" == engaged ]]; then
    # Binding headers prove carrier identity, not checklist completeness. Read
    # the declared finite list and require every declared row before accepting
    # an engaged tracker; optional rows come only from that declared list.
    [[ -n "${root//[[:space:]]/}" ]] || return 1
    local declared_steps=""
    declared_steps="$(_planveyor_merge_policy_step_keys "$root")" || return $?
    [[ -n "${declared_steps//[[:space:]]/}" ]] || return 1
    local step=""
    while IFS= read -r step; do
      [[ -n "${step//[[:space:]]/}" ]] || continue
      rg -q "^[[:space:]]*- \[[ xX]\] ${step}([[:space:]]|\$)" "$tracker_path" 2>/dev/null || return 1
    done <<< "$declared_steps"
    return 0
  fi

  # A legacy tracker cannot invent a selected-consumer schema gate. Any old
  # migration row is stale and requires re-init from an engaged declaration.
  if rg -q '^[[:space:]]*- \[[ xX]\] step:migrations_gate([[:space:]]|$)' "$tracker_path" 2>/dev/null; then
    return 1
  fi
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  case "$content_profile_id" in
    default|planveyor)
      rg -q '^[[:space:]]*- \[[ xX]\] step:ledger_lint([[:space:]]|$)' "$tracker_path" 2>/dev/null && return 1
      ;;
  esac
  local step=""
  while IFS= read -r step; do
    [[ -n "${step//[[:space:]]/}" ]] || continue
    rg -q "^[[:space:]]*- \[[ xX]\] ${step}([[:space:]]|\$)" "$tracker_path" 2>/dev/null || return 1
  done < <(_planveyor_merge_tracker_step_keys)
  return 0
}

_planveyor_merge_doc_lint_command() {
  # The lint implementation belongs to the pinned runtime, while the selected
  # consumer supplies the content root.  A consumer is not required to carry a
  # copy of the Planveyor shell scripts.
  echo "planveyor_doc_lint"
}

planveyor_merge_tracker_init() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_tracker_init)" || return $?
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
  # Creates/overwrites local merge tracker for current BASE..HEAD.
  # Usage: planveyor_merge_tracker_init
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tracker_path=""
  tracker_path="$(_planveyor_merge_tracker_path)" || return $?

  local base="" head="" merge=""
  base="$(_planveyor_get_range_base)" || return 1
  head="$(_planveyor_get_range_head)" || return 1
  merge="$(planveyor_range_merge 2>/dev/null || true)"

  local merge_policy_mode=""
  merge_policy_mode="$(_planveyor_merge_policy_mode "$root")" || return $?
  [[ "$merge_policy_mode" == legacy || "$merge_policy_mode" == engaged ]] || return 1
  local merge_policy_headers=""
  local merge_policy_steps="" merge_policy_checklist=""
  if [[ "$merge_policy_mode" == engaged ]]; then
    merge_policy_headers="$(_planveyor_merge_policy_metadata "$root" | rg '^(POLICY_SCHEMA|POLICY_SHA256|AUTHORITY_GENERATION)=')" || return $?
    [[ "$(print -r -- "$merge_policy_headers" | wc -l | tr -d '[:space:]')" == 3 ]] || return 1
    merge_policy_steps="$(_planveyor_merge_policy_step_keys "$root")" || return $?
    [[ -n "${merge_policy_steps//[[:space:]]/}" ]] || return 1
    merge_policy_checklist="$(_planveyor_merge_tracker_write_checklist "$root" "$merge_policy_mode" "$merge_policy_steps")" || return $?
    [[ -n "${merge_policy_checklist//[[:space:]]/}" ]] || return 1
  fi
  local backup_path; backup_path="$(_planveyor_merge_tracker_backup_path)"
  local now; now="$(_planveyor_now)"
  local profile_id; profile_id="$(_planveyor_repo_profile_id 2>/dev/null || true)"
  local b7; b7="$(_planveyor_sha7 "$base" 2>/dev/null || true)"
  local h7; h7="$(_planveyor_sha7 "$head" 2>/dev/null || true)"
  local range="${base}..${head}"
  local range_id="range_${b7}_${h7}"

  if [[ "$merge_policy_mode" == engaged ]]; then
    # Re-init may replace stale headers, but never a nonregular destination.
    # Prepare everything before revalidating the same frozen context at cp.
    _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" validate-init >/dev/null || return $?
    _planveyor_merge_policy_validate_tracker "$root" "$backup_path" validate-init >/dev/null || return $?
    _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  fi
  if [[ -f "$tracker_path" ]]; then
    cp "$tracker_path" "$backup_path" || return $?
    echo "Backed up previous tracker: ${backup_path}" >&2
  fi

  if [[ "$merge_policy_mode" == engaged ]]; then
    _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" validate-init >/dev/null || return $?
    _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  fi
  {
    cat <<EOF
# Merge tracker (LOCAL; not committed)

Created: ${now}

PROFILE_ID=${profile_id}
BASE=${base}
HEAD=${head}
MERGE_SHA=${merge}
RANGE=${range}
RANGE_ID=${range_id}
EOF
    [[ -z "$merge_policy_headers" ]] || print -r -- "$merge_policy_headers"
    cat <<'EOF'

## Checklist (tick manually; order matters)
EOF
    if [[ "$merge_policy_mode" == engaged ]]; then
      print -r -- "$merge_policy_checklist"
    else
      _planveyor_merge_tracker_write_checklist "$root" "$merge_policy_mode"
    fi
    cat <<'EOF'
## Notes
- Anything confusing? write it here.
EOF
  } > "$tracker_path" || return $?
  echo "Saved: ${tracker_path}" >&2
}

# Back-compat alias (muscle memory).
planveyor_merge_init() { planveyor_merge_tracker_init "$@"; }

planveyor_merge_tracker_show() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_tracker_show)" || return $?
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
  local tracker_path=""
  tracker_path="$(_planveyor_merge_tracker_path)" || return $?
  _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" >/dev/null || return $?
  [[ -f "$tracker_path" ]] || { echo "Missing merge tracker. Create one: planveyor_merge_tracker_init" >&2; return 1; }
  echo "merge_tracker: ${tracker_path}"
  sed -n '1,120p' "$tracker_path"
}

planveyor_merge_tracker_ensure() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_tracker_ensure)" || return $?
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
  # Ensures `.planveyor.range.*` (best-effort) and `.planveyor.merge_tracker.md` are present and consistent.
  # Usage:
  #   planveyor_merge_tracker_ensure
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tracker_path=""
  tracker_path="$(_planveyor_merge_tracker_path)" || return $?
  local merge_policy_mode=""
  merge_policy_mode="$(_planveyor_merge_policy_mode "$root")" || return $?
  [[ "$merge_policy_mode" == legacy || "$merge_policy_mode" == engaged ]] || return 1
  pushd "$root" >/dev/null || return 1

  local base="" head=""
  base="$(planveyor_range_base 2>/dev/null || true)"
  head="$(planveyor_range_head 2>/dev/null || true)"
  [[ "$base" == "<BASE_SHA>" ]] && base=""
  [[ "$head" == "<HEAD_SHA>" ]] && head=""
  if [[ -z "${base//[[:space:]]/}" || -z "${head//[[:space:]]/}" ]]; then
    echo "[planveyor] range missing -> auto-detect merge range" >&2
    planveyor_range_set_auto_merge || { popd >/dev/null; return 1; }
    base="$(_planveyor_get_range_base)" || { popd >/dev/null; return 1; }
    head="$(_planveyor_get_range_head)" || { popd >/dev/null; return 1; }
  fi

  local range="${base}..${head}"
  local merge="" b7="" h7="" range_id=""
  merge="$(planveyor_range_merge 2>/dev/null || true)"
  b7="$(_planveyor_sha7 "$base" 2>/dev/null || true)"
  h7="$(_planveyor_sha7 "$head" 2>/dev/null || true)"
  range_id="range_${b7}_${h7}"
  if [[ ! -f "$tracker_path" ]]; then
    planveyor_merge_tracker_init || { popd >/dev/null; return 1; }
  else
    if [[ "$merge_policy_mode" == engaged ]]; then
      _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" >/dev/null || {
        echo "[planveyor] engaged tracker binding mismatch -> explicit re-init required" >&2
        popd >/dev/null
        return 1
      }
    fi
    local t_base="" t_head="" t_merge="" t_range="" t_range_id="" header_mismatch=0
    t_base="$(_planveyor_tracker_header_value "$tracker_path" "BASE" 2>/dev/null || true)"
    t_head="$(_planveyor_tracker_header_value "$tracker_path" "HEAD" 2>/dev/null || true)"
    t_merge="$(_planveyor_tracker_header_value "$tracker_path" "MERGE_SHA" 2>/dev/null || true)"
    t_range="$(_planveyor_tracker_header_value "$tracker_path" "RANGE" 2>/dev/null || true)"
    t_range_id="$(_planveyor_tracker_header_value "$tracker_path" "RANGE_ID" 2>/dev/null || true)"
    [[ "$t_base" == "$base" ]] || header_mismatch=1
    [[ "$t_head" == "$head" ]] || header_mismatch=1
    [[ "$t_range" == "$range" ]] || header_mismatch=1
    [[ "$t_range_id" == "$range_id" ]] || header_mismatch=1
    if [[ -n "${merge//[[:space:]]/}" && "$t_merge" != "$merge" ]]; then header_mismatch=1; fi
    if (( header_mismatch )); then
      echo "[planveyor] tracker header mismatch (BASE/HEAD/MERGE_SHA/RANGE/RANGE_ID) -> re-init" >&2
      planveyor_merge_tracker_init || { popd >/dev/null; return 1; }
    elif ! _planveyor_merge_tracker_matches_profile "$tracker_path" "$merge_policy_mode" "$root"; then
      echo "[planveyor] tracker step-set mismatch for repo profile -> re-init" >&2
      planveyor_merge_tracker_init || { popd >/dev/null; return 1; }
    fi
  fi

  popd >/dev/null || return 1
  echo "$tracker_path"
}

planveyor_merge_tracker_next_step() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_tracker_next_step)" || return $?
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
  # Prints the next unchecked `step:*` from `.planveyor.merge_tracker.md` (empty if done).
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tracker_path=""
  tracker_path="$(_planveyor_merge_tracker_path)" || return $?
  _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" >/dev/null || return $?
  [[ -f "$tracker_path" ]] || { echo "Missing merge tracker. Create one: planveyor_merge_tracker_init" >&2; return 1; }
  _planveyor_tracker_first_unchecked_key "$tracker_path" 2>/dev/null || true
}

planveyor_merge_tracker_tick() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_tracker_tick)" || return $?
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
  # Ticks a `step:*` checkbox in `.planveyor.merge_tracker.md` deterministically (no manual edits).
  # Usage:
  #   planveyor_merge_tracker_tick step:review_range
  local key="${1:-}"
  [[ -n "${key//[[:space:]]/}" ]] || { echo "Usage: planveyor_merge_tracker_tick step:<name>" >&2; return 1; }
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tracker_path=""
  tracker_path="$(_planveyor_merge_tracker_path)" || return $?
  _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" >/dev/null || return $?
  [[ -f "$tracker_path" ]] || { echo "Missing merge tracker. Create one: planveyor_merge_tracker_init" >&2; return 1; }
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$(_planveyor_script merge_tracker_oracle.py)" --tracker "$tracker_path" tick "$key"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

_planveyor_find_latest_range_artifact() {
  # Finds latest (by filename sort) matching file within DIR by regex.
  local dir="$1"
  local regex="$2"
  local root="$(_planveyor_project_root)" || return $?
  pushd "$root" >/dev/null || return 1
  local found=""
  found="$(rg --files "$dir" 2>/dev/null | rg "$regex" | sort | tail -n 1 || true)"
  popd >/dev/null || return 1
  [[ -n "${found//[[:space:]]/}" ]] || return 1
  echo "$found"
}

planveyor_merge_next() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_next)" || return $?
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
  # Suggests next post-merge step based on tracker + artifacts for current BASE..HEAD.
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tracker_path=""
  tracker_path="$(_planveyor_merge_tracker_path)" || return $?
  local merge_policy_mode=""
  merge_policy_mode="$(_planveyor_merge_policy_mode "$root")" || return $?
  [[ "$merge_policy_mode" == legacy || "$merge_policy_mode" == engaged ]] || return 1
  _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" >/dev/null || return $?
  if [[ ! -f "$tracker_path" ]]; then
    echo "Missing merge tracker: ${tracker_path}" >&2
    echo "Next: planveyor_merge_tracker_init" >&2
    return 1
  fi

  local base="" head="" merge=""
  base="$(_planveyor_get_range_base)" || return 1
  head="$(_planveyor_get_range_head)" || return 1
  merge="$(planveyor_range_merge 2>/dev/null || true)"
  local range="${base}..${head}"
  local b7; b7="$(_planveyor_sha7 "$base" 2>/dev/null || true)"
  local h7; h7="$(_planveyor_sha7 "$head" 2>/dev/null || true)"
  local range_id="range_${b7}_${h7}"

  local t_base="" t_head="" t_merge="" t_range="" t_range_id=""
  t_base="$(_planveyor_tracker_header_value "$tracker_path" "BASE" 2>/dev/null || true)"
  t_head="$(_planveyor_tracker_header_value "$tracker_path" "HEAD" 2>/dev/null || true)"
  t_merge="$(_planveyor_tracker_header_value "$tracker_path" "MERGE_SHA" 2>/dev/null || true)"
  t_range="$(_planveyor_tracker_header_value "$tracker_path" "RANGE" 2>/dev/null || true)"
  t_range_id="$(_planveyor_tracker_header_value "$tracker_path" "RANGE_ID" 2>/dev/null || true)"

  echo "Range: ${range} (merge=${merge:-})"
  echo "Tracker: ${tracker_path}"
  if [[ "$t_base" != "$base" ]]; then
    echo "⚠️ Tracker BASE != current BASE (tracker=${t_base:-missing}, current=${base}). Consider: planveyor_merge_tracker_init" >&2
  fi
  if [[ "$t_head" != "$head" ]]; then
    echo "⚠️ Tracker HEAD != current HEAD (tracker=${t_head:-missing}, current=${head}). Consider: planveyor_merge_tracker_init" >&2
  fi
  if [[ -n "${merge//[[:space:]]/}" && "$t_merge" != "$merge" ]]; then
    echo "⚠️ Tracker MERGE_SHA != current MERGE_SHA (tracker=${t_merge:-missing}, current=${merge}). Consider: planveyor_merge_tracker_init" >&2
  fi
  if [[ "$t_range" != "$range" ]]; then
    echo "⚠️ Tracker RANGE != current RANGE (tracker=${t_range:-missing}, current=${range}). Consider: planveyor_merge_tracker_init" >&2
  fi
  if [[ "$t_range_id" != "$range_id" ]]; then
    echo "⚠️ Tracker RANGE_ID != current RANGE_ID (tracker=${t_range_id:-missing}, current=${range_id}). Consider: planveyor_merge_tracker_init" >&2
  fi

  local review_plan="" merge_notes="" plan_harvest="" followups_backlog="" packetization_report="" audit_report="" operational_receipt="" canon_snapshot="" canon_receipt=""
  review_plan="$(_planveyor_find_latest_range_artifact "docs/plans" "_reviewer_range_${b7}_${h7}\\.md\$" 2>/dev/null || true)"
  merge_notes="$(_planveyor_find_latest_range_artifact "docs/reviews" "_merge_notes_range_${b7}_${h7}\\.md\$" 2>/dev/null || true)"
  plan_harvest="$(_planveyor_find_latest_range_artifact "docs/reviews" "_plan_harvest_range_${b7}_${h7}\\.md\$" 2>/dev/null || true)"
  followups_backlog="$(_planveyor_find_latest_range_artifact "docs/followups" "_followups_range_${b7}_${h7}\\.md\$" 2>/dev/null || true)"
  packetization_report="$(_planveyor_find_latest_range_artifact "docs/reviews" "_packetization_gate_range_${b7}_${h7}\\.md\$" 2>/dev/null || true)"
  audit_report="$(_planveyor_find_latest_range_artifact "docs/reviews" "_post_merge_audit_range_${b7}_${h7}\\.md\$" 2>/dev/null || true)"
  operational_receipt="$(_planveyor_find_latest_range_artifact "docs/reviews" "_post_merge_operational_receipt_range_${b7}_${h7}\\.md\$" 2>/dev/null || true)"
  canon_snapshot="$(_planveyor_find_latest_range_artifact "docs/snapshots" "range_${b7}_${h7}" 2>/dev/null || true)"
  canon_receipt="$(_planveyor_find_latest_range_artifact "docs/reviews" "_canon_sweep_receipt_range_${b7}_${h7}\\.md\$" 2>/dev/null || true)"

  if [[ -n "${review_plan//[[:space:]]/}" ]]; then echo "artifact: review_plan=${review_plan}"; else echo "artifact: review_plan=(none)"; fi
  if [[ -n "${merge_notes//[[:space:]]/}" ]]; then echo "artifact: merge_notes=${merge_notes}"; else echo "artifact: merge_notes=(none)"; fi
  if [[ -n "${plan_harvest//[[:space:]]/}" ]]; then echo "artifact: plan_harvest=${plan_harvest}"; else echo "artifact: plan_harvest=(none)"; fi
  if [[ -n "${followups_backlog//[[:space:]]/}" ]]; then echo "artifact: followups_backlog=${followups_backlog}"; else echo "artifact: followups_backlog=(none)"; fi
  if [[ -n "${packetization_report//[[:space:]]/}" ]]; then echo "artifact: packetization_gate=${packetization_report}"; else echo "artifact: packetization_gate=(none)"; fi
  if [[ -n "${audit_report//[[:space:]]/}" ]]; then echo "artifact: post_merge_audit=${audit_report}"; else echo "artifact: post_merge_audit=(none)"; fi
  if [[ -n "${operational_receipt//[[:space:]]/}" ]]; then echo "artifact: post_merge_operational_receipt=${operational_receipt}"; else echo "artifact: post_merge_operational_receipt=(none)"; fi
  if [[ -n "${canon_snapshot//[[:space:]]/}" ]]; then echo "artifact: canon_snapshot=${canon_snapshot}"; else echo "artifact: canon_snapshot=(none)"; fi
  if [[ -n "${canon_receipt//[[:space:]]/}" ]]; then echo "artifact: canon_sweep_receipt=${canon_receipt}"; else echo "artifact: canon_sweep_receipt=(none)"; fi

  local review_done_inferred=0
  local review_status_line="" review_status_value="" review_runner=""
  local merge_notes_done_inferred=0
  local merge_notes_status_line="" merge_notes_status_value=""
  local plan_harvest_done_inferred=0
  local plan_harvest_status_line="" plan_harvest_status_value=""
  local canon_receipt_done_inferred=0
  local canon_receipt_status_line="" canon_receipt_status_value=""
  local packetization_done_inferred=0
  local packetization_status_line="" packetization_status_value="" packetization_blocked=0
  local packetization_blocker_summary="" packetization_parse_rc=0
  local audit_done_inferred=0
  local audit_status_line="" audit_status_value=""
  if [[ -n "${review_plan//[[:space:]]/}" && -f "$root/$review_plan" ]]; then
    review_status_line="$(_planveyor_plan_status_line_lenient "$root/$review_plan" 2>/dev/null || true)"
    review_status_value="$(_planveyor_extract_status_value "$review_status_line" 2>/dev/null || true)"
    local s_l="${review_status_value:l}"
    if [[ "$s_l" == done* || "$s_l" == superseded* ]]; then
      review_done_inferred=1
    fi
    review_runner="$(_planveyor_suggest_runner_from_status "$review_status_value" 2>/dev/null || true)"
  fi
  if [[ -n "${merge_notes//[[:space:]]/}" && -f "$root/$merge_notes" ]]; then
    merge_notes_status_line="$(_planveyor_plan_status_line_lenient "$root/$merge_notes" 2>/dev/null || true)"
    merge_notes_status_value="$(_planveyor_extract_status_value "$merge_notes_status_line" 2>/dev/null || true)"
    if _planveyor_status_value_is_done_like "$merge_notes_status_value"; then
      merge_notes_done_inferred=1
    fi
  fi
  if [[ -n "${plan_harvest//[[:space:]]/}" && -f "$root/$plan_harvest" ]]; then
    plan_harvest_status_line="$(_planveyor_plan_status_line_lenient "$root/$plan_harvest" 2>/dev/null || true)"
    plan_harvest_status_value="$(_planveyor_extract_status_value "$plan_harvest_status_line" 2>/dev/null || true)"
    if _planveyor_status_value_is_done_like "$plan_harvest_status_value"; then
      plan_harvest_done_inferred=1
    fi
  fi
  if [[ -n "${canon_receipt//[[:space:]]/}" && -f "$root/$canon_receipt" ]]; then
    canon_receipt_status_line="$(_planveyor_plan_status_line_lenient "$root/$canon_receipt" 2>/dev/null || true)"
    canon_receipt_status_value="$(_planveyor_extract_status_value "$canon_receipt_status_line" 2>/dev/null || true)"
    if _planveyor_status_value_is_done_like "$canon_receipt_status_value"; then
      canon_receipt_done_inferred=1
    fi
  fi
  if [[ -n "${packetization_report//[[:space:]]/}" && -f "$root/$packetization_report" ]]; then
    packetization_status_line="$(_planveyor_plan_status_line_lenient "$root/$packetization_report" 2>/dev/null || true)"
    packetization_status_value="$(_planveyor_extract_status_value "$packetization_status_line" 2>/dev/null || true)"
    packetization_blocker_summary="$(
      _planveyor_py_any -c '
import json
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
blocks = [json.loads(body) for body in re.findall(r"```json\s*(.*?)```", text, re.S)]
payload = next(
    (
        block["packetization_gate"]
        for block in blocks
        if isinstance(block, dict) and isinstance(block.get("packetization_gate"), dict)
    ),
    None,
)
if payload is None or not isinstance(payload.get("rows"), list):
    raise ValueError("packetization_gate.v1 rows missing")
raw_blocking_coverages = payload.get("blocking_coverages", [])
if not isinstance(raw_blocking_coverages, list) or not all(
    isinstance(coverage, str) and coverage.strip() for coverage in raw_blocking_coverages
):
    raise ValueError("packetization_gate.v1 blocking_coverages is invalid")
declared_blocking_coverages = {coverage.strip() for coverage in raw_blocking_coverages}
counts = {}
blocking_counts = {}
for row in payload["rows"]:
    if not isinstance(row, dict):
        raise ValueError("packetization_gate.v1 row is not an object")
    coverage = row.get("coverage")
    if not isinstance(coverage, str) or not coverage.strip():
        raise ValueError("packetization_gate.v1 row coverage is missing")
    coverage = coverage.strip()
    counts[coverage] = counts.get(coverage, 0) + 1
    if "blocking" in row:
        blocking = row["blocking"]
        if not isinstance(blocking, bool):
            raise ValueError("packetization_gate.v1 row blocking must be boolean")
    else:
        # Legacy report compatibility derives from its own declared payload,
        # never from a wrapper-owned coverage-label allowlist.
        blocking = coverage in declared_blocking_coverages
    if blocking:
        blocking_counts[coverage] = blocking_counts.get(coverage, 0) + 1
declared_blocking_rows = payload.get("blocking_rows_count", payload.get("blocking_count"))
if declared_blocking_rows is not None:
    if isinstance(declared_blocking_rows, bool) or not isinstance(declared_blocking_rows, int):
        raise ValueError("packetization_gate.v1 blocking_rows_count is invalid")
    if declared_blocking_rows != sum(blocking_counts.values()):
        raise ValueError("packetization_gate.v1 blocking_rows_count does not match rows")
if "blocking_coverage_counts" in payload:
    declared = payload["blocking_coverage_counts"]
    if not isinstance(declared, dict):
        raise ValueError("packetization_gate.v1 blocking_coverage_counts is not an object")
    normalized = {}
    for coverage, count in declared.items():
        if (
            not isinstance(coverage, str)
            or not coverage.strip()
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise ValueError("packetization_gate.v1 blocking_coverage_counts is invalid")
        normalized[coverage.strip()] = count
    expected = dict(counts)
    for coverage in normalized:
        expected.setdefault(coverage, 0)
    if normalized != expected:
        raise ValueError("packetization_gate.v1 blocking_coverage_counts does not match rows")
for coverage, count in sorted(blocking_counts.items()):
    if count:
        print(f"{coverage}={count}")
' "$root/$packetization_report" 2>/dev/null
    )"
    packetization_parse_rc=$?
    if (( packetization_parse_rc != 0 )); then
      packetization_blocked=1
      packetization_blocker_summary="malformed structural packetization JSON"
    elif [[ -n "${packetization_blocker_summary//[[:space:]]/}" ]]; then
      packetization_blocked=1
    fi
    if _planveyor_status_value_is_done_like "$packetization_status_value" && (( !packetization_blocked )); then
      packetization_done_inferred=1
    fi
  fi
  if [[ -n "${audit_report//[[:space:]]/}" && -f "$root/$audit_report" ]]; then
    audit_status_line="$(_planveyor_plan_status_line_lenient "$root/$audit_report" 2>/dev/null || true)"
    audit_status_value="$(_planveyor_extract_status_value "$audit_status_line" 2>/dev/null || true)"
    if _planveyor_status_value_is_done_like "$audit_status_value"; then
      audit_done_inferred=1
    fi
  fi

  # Step order must match tracker file section. `step:docs_hygiene_list` stays here
  # only for backward-compat with legacy trackers; new trackers omit it and the
  # loop below skips missing steps.
  local -a steps
  if [[ "$merge_policy_mode" == engaged ]]; then
    steps=("${(@f)$(_planveyor_merge_policy_step_keys "$root")}") || return $?
  else
    steps=("${(@f)$(_planveyor_merge_tracker_step_keys)}")
  fi
  steps+=("step:docs_hygiene_list")

  local auto_next="" manual_next=""
  manual_next="$(_planveyor_tracker_first_unchecked_key "$tracker_path" 2>/dev/null || true)"

  local mismatch=0
  local key
  for key in "${steps[@]}"; do
    # Backward-compat: if tracker doesn't include the step (older tracker), skip it.
    rg -q "^[[:space:]]*- \\[[ xX]\\] ${key}([[:space:]]|\$)" "$tracker_path" 2>/dev/null || continue
    local checked=0 inferred=0
    _planveyor_tracker_is_checked "$tracker_path" "$key" && checked=1 || true
    case "$key" in
      "step:review_range")
        inferred="$review_done_inferred"
        if [[ -n "${review_plan//[[:space:]]/}" ]] && (( !checked )) && (( inferred )); then
          echo "⚠️ Tracker not ticked but review_range looks done (status=${review_status_value:-?})" >&2
          mismatch=1
        fi
        if (( checked )) && (( !inferred )) && [[ -n "${review_plan//[[:space:]]/}" ]]; then
          echo "⚠️ Tracker ticked but review_range not done (status=${review_status_value:-?})" >&2
          mismatch=1
        fi
        ;;
      "step:merge_notes")
        inferred="$merge_notes_done_inferred"
        if (( inferred )) && (( !checked )); then echo "⚠️ Tracker not ticked but merge_notes is Done: ${merge_notes}" >&2; mismatch=1; fi
        if [[ -n "${merge_notes//[[:space:]]/}" ]] && (( !inferred )); then echo "⚠️ merge_notes exists but status is not Done yet: ${merge_notes} (status=${merge_notes_status_value:-?})" >&2; mismatch=1; fi
        if (( checked )) && (( !inferred )); then echo "⚠️ Tracker ticked but merge_notes missing/undone for range ${b7}..${h7} (status=${merge_notes_status_value:-missing})" >&2; mismatch=1; fi
        ;;
      "step:plan_harvest")
        inferred="$plan_harvest_done_inferred"
        if (( inferred )) && (( !checked )); then echo "⚠️ Tracker not ticked but plan_harvest is Done: ${plan_harvest}" >&2; mismatch=1; fi
        if [[ -n "${plan_harvest//[[:space:]]/}" ]] && (( !inferred )); then echo "⚠️ plan_harvest exists but status is not Done yet: ${plan_harvest} (status=${plan_harvest_status_value:-?})" >&2; mismatch=1; fi
        if (( checked )) && (( !inferred )); then echo "⚠️ Tracker ticked but plan_harvest missing/undone for range ${b7}..${h7} (status=${plan_harvest_status_value:-missing})" >&2; mismatch=1; fi
        ;;
      "step:canon_sweep")
        if [[ -n "${canon_snapshot//[[:space:]]/}" ]] || (( canon_receipt_done_inferred )); then inferred=1; else inferred=0; fi
        if (( inferred )) && (( !checked )); then echo "⚠️ Tracker not ticked but canon sweep proof exists: ${canon_snapshot:-${canon_receipt}}" >&2; mismatch=1; fi
        if [[ -n "${canon_receipt//[[:space:]]/}" ]] && (( !canon_receipt_done_inferred )); then echo "⚠️ canon_sweep receipt exists but status is not Done yet: ${canon_receipt} (status=${canon_receipt_status_value:-?})" >&2; mismatch=1; fi
        if (( checked )) && (( !inferred )); then echo "⚠️ Tracker ticked but canon_sweep proof missing for range ${b7}..${h7}; expected docs/snapshots/*range_${b7}_${h7}* or docs/reviews/*_canon_sweep_receipt_range_${b7}_${h7}.md" >&2; mismatch=1; fi
        ;;
      "step:packetization_gate")
        inferred="$packetization_done_inferred"
        if (( inferred )) && (( !checked )); then echo "⚠️ Tracker not ticked but packetization_gate is Done: ${packetization_report}" >&2; mismatch=1; fi
        if [[ -n "${packetization_report//[[:space:]]/}" ]] && (( packetization_blocked )); then echo "⚠️ packetization_gate report has structural blocker(s): ${packetization_blocker_summary:-unknown} (${packetization_report})" >&2; mismatch=1; fi
        if [[ -n "${packetization_report//[[:space:]]/}" ]] && (( !inferred )) && (( !packetization_blocked )); then echo "⚠️ packetization_gate exists but status is not Done yet: ${packetization_report} (status=${packetization_status_value:-?})" >&2; mismatch=1; fi
        if (( checked )) && (( !inferred )); then echo "⚠️ Tracker ticked but packetization_gate missing/blocked/undone for range ${b7}..${h7} (status=${packetization_status_value:-missing})" >&2; mismatch=1; fi
        ;;
      "step:post_merge_audit")
        inferred="$audit_done_inferred"
        if (( inferred )) && (( !checked )); then echo "⚠️ Tracker not ticked but post-merge audit is Done: ${audit_report}" >&2; mismatch=1; fi
        if [[ -n "${audit_report//[[:space:]]/}" ]] && (( !inferred )); then echo "⚠️ post-merge audit exists but status is not Done yet: ${audit_report} (status=${audit_status_value:-?})" >&2; mismatch=1; fi
        if (( checked )) && (( !inferred )); then echo "⚠️ Tracker ticked but post-merge audit missing/undone for range ${b7}..${h7} (status=${audit_status_value:-missing})" >&2; mismatch=1; fi
        ;;
    esac

    local done=0
    if (( checked )) || (( inferred )); then
      done=1
    fi
    if (( !done )) && [[ -z "${auto_next//[[:space:]]/}" ]]; then
      auto_next="$key"
    fi
  done

  [[ -n "${auto_next//[[:space:]]/}" ]] || auto_next="(none)"
  [[ -n "${manual_next//[[:space:]]/}" ]] || manual_next="(none)"

  echo "manual_next: ${manual_next}"
  echo "auto_next:   ${auto_next}"
  if [[ "$manual_next" != "$auto_next" ]]; then
    echo "⚠️ Next-step mismatch (manual vs auto). Open tracker and reconcile: ${tracker_path}" >&2
  fi

  echo ""
  echo "Suggested command(s):"
  case "$auto_next" in
    "step:migrations_gate")
      if [[ "$merge_policy_mode" != engaged ]]; then
        echo "[planveyor] declared consumer schema/migration gate required -> re-init from an engaged selected consumer" >&2
        return 1
      fi
      echo "# Declared consumer schema gate: follow the tracker-linked selected-consumer contract before commands."
      _planveyor_merge_policy_render "$root" "$auto_next" || return $?
      ;;
    "step:review_range")
      if [[ -z "${review_plan//[[:space:]]/}" ]]; then
        echo "# A) Review single pass (включая docs + post-merge visual sanity для runtime UI; EXCLUDE_DOCS=0)"
        echo "planveyor_review_range_start 0"
        echo "# B) После завершения прохода — снова: planveyor_merge_next"
      else
        local runner="${review_runner:-}"
        echo "# A) Открыть review-only plan"
        echo "planveyor_plan_set \"${review_plan}\""
        echo "# B) Запустить следующую роль по Status"
        if [[ -z "${runner//[[:space:]]/}" || "$runner" == "(unknown)" ]]; then
          echo "# (unknown) — посмотри status в плане и запусти нужную роль вручную"
        else
          echo "${runner}"
        fi
        echo "# C) Повторять до Architect triage: Done = merge-range accepted для текущего flow (deferred follow-up допустим); Superseded = blocking follow-up и stop-the-line, потом новый merge review после fix merge"
      fi
      ;;
    "step:merge_notes")
      echo "# A) Сгенерировать/обновить merge notes (human-readable; не финальные релиз-ноты) и довести файл до **Status:** ✅ Done"
      echo "planveyor_arch_merge_notes_start"
      echo "# B) Если merge notes всё ещё в Draft — шаг не закрыт; добей статус до ✅ Done или зафиксируй blocker"
      echo "# C) Если после этого появились новые doc-коммиты — обнови HEAD в range (и опц. переинициализируй tracker)"
      echo 'planveyor_range_set "$(planveyor_range_base)" "$(git rev-parse HEAD)" "$(planveyor_range_merge 2>/dev/null || true)"'
      echo "planveyor_merge_tracker_init"
      ;;
    "step:plan_harvest")
      echo "# A) Plan harvest (follow-ups + canon updates) — довести harvest report до **Status:** ✅ Done"
      echo "planveyor_arch_plan_harvest_start"
      echo "# B) Если harvest report всё ещё в Draft — шаг не закрыт; добей статус до ✅ Done или зафиксируй blocker"
      echo "# C) Если после harvest появились новые doc-коммиты — обнови HEAD в range (и опц. переинициализируй tracker)"
      echo 'planveyor_range_set "$(planveyor_range_base)" "$(git rev-parse HEAD)" "$(planveyor_range_merge 2>/dev/null || true)"'
      echo "planveyor_merge_tracker_init"
      ;;
    "step:canon_sweep")
      echo "# A) Canon sweep (осушение канонов) — пишет в docs/** и durable proof carrier"
      echo "planveyor_arch_canon_sweep_start"
      echo "# B) Перед тиком нужен proof: docs/snapshots/*range_${b7}_${h7}* или docs/reviews/*_canon_sweep_receipt_range_${b7}_${h7}.md с **Status:** ✅ Done"
      echo "# C) Если после этого появились новые doc-коммиты — обнови HEAD в range (и опц. переинициализируй tracker)"
      echo 'planveyor_range_set "$(planveyor_range_base)" "$(git rev-parse HEAD)" "$(planveyor_range_merge 2>/dev/null || true)"'
      echo "planveyor_merge_tracker_init"
      ;;
    "step:packetization_gate")
      echo "# A) Packetization gate: full-OID range identity является authority; --source-plan — только optional packet-local provenance. Default receipt-reuse-only не меняет packet bytes/index."
      echo 'planveyor_post_merge_packetization_gate_recover --range "$(planveyor_range_base)..$(planveyor_range_head)"'
      echo "# B) Если report red — Owner создаёт packet через positional public API, заполняет truthful target_kind/target_writable_carriers, затем запускает explicit discovery-or-seed."
      echo 'planveyor_rollout_packet_create <target_repo> <topic_slug> [--source-plan docs/plans/<provenance-plan>.md] --target-kind <target-kind>'
      echo 'planveyor_post_merge_packetization_gate_recover --range "$(planveyor_range_base)..$(planveyor_range_head)" --packet docs/rollout_packets/<packet>.md --stage-packets'
      echo "# C) Wrapper не читает sibling repo и не импортирует/adopt'ит target; второй report создавай только явным --out."
      echo "# D) Owner readback: planveyor_merge_bundle_report --format json показывает active_packetization_report, report_accepted_packet_paths и superseded history отдельно."
      echo 'planveyor_range_set "$(planveyor_range_base)" "$(git rev-parse HEAD)" "$(planveyor_range_merge 2>/dev/null || true)"'
      echo "planveyor_merge_tracker_init"
      ;;
    "step:docs_finalize")
      # Ordinary memory-finalize remains a separate lane; without roadmap/todo its outcome = NO PROGRESS UPDATES.
      local docs_finalize_stamp="" docs_finalize_receipt_path=""
      docs_finalize_stamp="$(date +%y%m%d_%H%M)"
      docs_finalize_receipt_path="docs/reviews/${docs_finalize_stamp}_docs_finalize_receipt_range_${b7}_${h7}.md"
      echo "# A) Merge docs finalize: единственный proof — Architect general по exact receipt path."
      echo "DOCS_FINALIZE_RECEIPT_PATH=${docs_finalize_receipt_path}"
      echo "planveyor_post_merge_receipt_skeleton docs_finalize_receipt --out \"${docs_finalize_receipt_path}\""
      echo "planveyor_arch_docs_general --receipt-path \"${docs_finalize_receipt_path}\""
      echo "# B) Убедись, что Architect вернул ровно docs_finalize_receipt_path=${docs_finalize_receipt_path}."
      echo "planveyor_post_merge_docs_finalize_tick --role Architect --range \"${base}..${head}\" --path \"${docs_finalize_receipt_path}\""
      ;;
    "step:doc_lint")
      if [[ "$merge_policy_mode" == engaged ]]; then
        _planveyor_merge_policy_render "$root" "$auto_next" || return $?
      else
        echo "# A) Gate: doc-lint"
        echo "$(_planveyor_merge_doc_lint_command)"
      fi
      ;;
    "step:ledger_lint")
      if [[ "$merge_policy_mode" == engaged ]]; then
        _planveyor_merge_policy_render "$root" "$auto_next" || return $?
      else
        echo "Legacy ledger step requires a target-declared merge policy; re-init the tracker." >&2
        return 1
      fi
      ;;
    "step:post_merge_audit")
      echo "# A) Post-merge audit (multi-plan): report + follow-ups + cleanup list + cross-check visual sanity; audit-report должен дойти до **Status:** ✅ Done"
      echo "planveyor_arch_post_merge_audit_start"
      echo "# B) Если audit-report всё ещё в Draft — шаг не закрыт; добей статус до ✅ Done или зафиксируй blocker"
      echo "# C) Если audit создал новые doc-коммиты — обнови HEAD в range (и опц. переинициализируй tracker)"
      echo 'planveyor_range_set "$(planveyor_range_base)" "$(git rev-parse HEAD)" "$(planveyor_range_merge 2>/dev/null || true)"'
      echo "planveyor_merge_tracker_init"
      ;;
    "step:docs_hygiene_archive")
      echo "# A) Обязательный archive temp docs в central SQLite FTS; в normal merge flow это должно происходить до owner cleanup handoff"
      echo 'planveyor_docs_hygiene_archive --range "$(planveyor_range_base)..$(planveyor_range_head)" --apply'
      echo "# B) После успешного archive следующий шаг — automated report-only suggest gate"
      ;;
    "step:docs_hygiene_list")
      echo "# LEGACY optional inventory helper; новые tracker'ы не должны содержать этот шаг"
      echo "planveyor_docs_hygiene_list"
      echo "# Затем — report-only cleanup handoff через planveyor_docs_hygiene_suggest"
      ;;
    "step:docs_hygiene_suggest")
      echo "# A) Automated report-only suggest gate: run helper, require parse markers, tick only step:docs_hygiene_suggest"
      echo "planveyor_post_merge_docs_hygiene_suggest_gate"
      echo "# B) Suggested git rm is never executed here; deletion remains later Owner-only cleanup after fresh archive/suggest"
      ;;
    "step:ready_to_push")
      echo "# A) Перед receipt обнови portable archive snapshot после docs_hygiene_archive: fresh git_text_export + validate + restore/readback; default carrier docs/_meta/archive_snapshots/current/manifest.json"
      echo "planveyor_docs_archive_snapshot_export --backend git_text_export --output-dir docs/_meta/archive_snapshots/current --force"
      echo "planveyor_docs_archive_snapshot_validate --manifest docs/_meta/archive_snapshots/current/manifest.json --verify-artifact"
      echo 'planveyor_docs_archive_snapshot_restore --manifest docs/_meta/archive_snapshots/current/manifest.json --dest-db .tmp/planveyor_docs_archive_ready_to_push.sqlite --replace --query "post merge archive snapshot" --expect-min-hits 1'
      echo "# B) Создай helper-backed operational receipt: repeated --record-json rows обязательны для docs_finalize/doc_lint/docs_hygiene_archive/docs_hygiene_suggest/docs_index_context/retrieval_metrics/canon_sweep/planveyor_merge_bundle_report + --archive-snapshot-json с export/source_db fields"
      echo "planveyor_post_merge_operational_receipt --help"
      echo "# C) После записи committed receipt: docs/reviews/*_post_merge_operational_receipt_range_${b7}_${h7}.md"
      echo "# D) Финальный read-only receipt/bundle gate: до terminal closeout missing companion proof = pre_terminal_missing_allowed; после tick/current terminal readback missing/malformed proof блокирует"
      echo "planveyor_merge_bundle_report"
      echo "# E) Fail-closed local closeout helper; ticks step:ready_to_push before terminal proof, rolls tick back if receipt staging/commit fails, materializes/stages only docs/reviews/*_ready_to_push_closeout_range_${b7}_${h7}.md companion proof plus already-staged report-accepted paths, blocks with why_blocked + aggregate staging diagnostics (staging_diagnostics) + safe staging_command/pathspec_file for dirty report-accepted paths only, never pushes"
      echo "planveyor_post_merge_ready_to_push_closeout"
      echo "# F) Final owner digest: read-only verdict over bundle report, risk packet, active packetization report, closeout proof, and pending_owner_gate=git push"
      echo "planveyor_merge_range_verdict_digest"
      echo "# G) Push remains Owner-owned after local closeout and green digest"
      echo "git push"
      ;;
    "(none)") echo "# Nothing pending (auto). If everything looks good: git push" ;;
    *) echo "# Unknown next step: ${auto_next} (check tracker)" ;;
  esac
}

planveyor_post_merge_packetization_gate() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_post_merge_packetization_gate)" || return $?
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
  # Generates source-local rollout-packet coverage report for current merge range.
  # Usage:
  #   planveyor_post_merge_packetization_gate [--range BASE..HEAD] [--out PATH] [--create-drafts] [--json]
  local root="$(_planveyor_project_root)" || return $?
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  local helper="$(_planveyor_script post_merge_packetization_gate.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --repo-root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_post_merge_packetization_gate_recover() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_post_merge_packetization_gate_recover)" || return $?
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
  # Bounded source-local recovery: --range is mandatory; --source-plan is optional provenance.
  # Usage:
  #   planveyor_post_merge_packetization_gate_recover --range BASE..HEAD [--source-plan docs/plans/<provenance-plan>.md] [--packet docs/rollout_packets/<packet>.md ...] [--stage-packets] [--format plain|json]
  local root="$(_planveyor_project_root)" || return $?
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  local helper="$(_planveyor_script post_merge_packetization_gate.py)"
  local arg=""
  local next_value=""
  local have_range=0
  local i=1
  while (( i <= $# )); do
    arg="${@[$i]}"
    case "$arg" in
      --range|--source-plan)
        (( i++ ))
        next_value="${@[$i]-}"
        [[ -n "${next_value//[[:space:]]/}" && "$next_value" != --* ]] || {
          echo "ERROR: planveyor_post_merge_packetization_gate_recover requires a value after $arg" >&2
          return 2
        }
        [[ "$arg" == "--range" ]] && have_range=1
        ;;
      --range=*) have_range=1 ;;
    esac
    (( i++ ))
  done
  (( have_range )) || {
    echo "ERROR: usage: planveyor_post_merge_packetization_gate_recover --range BASE..HEAD [--source-plan docs/plans/<provenance-plan>.md] [--packet ...] [--stage-packets]" >&2
    return 2
  }
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --repo-root "$root" --recover "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_post_merge_receipt_skeleton() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_post_merge_receipt_skeleton)" || return $?
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
  # Emits deterministic parser-valid skeleton frames for post-merge receipt families.
  # Usage:
  #   planveyor_post_merge_receipt_skeleton <family> [--out PATH]
  local root="$(_planveyor_project_root)" || return $?
  local helper="$(_planveyor_script post_merge_receipt_skeleton.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_post_merge_receipt_preflight() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_post_merge_receipt_preflight)" || return $?
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
  # Runs step-local schema preflight for freshly materialized post-merge receipts.
  # Usage:
  #   planveyor_post_merge_receipt_preflight <plan_harvest|canon_sweep|post_merge_audit|packetization_gate|docs_finalize> --path PATH [--format plain|json]
  local root="$(_planveyor_project_root)" || return $?
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  local helper="$(_planveyor_script post_merge_receipt_preflight.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --repo-root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_post_merge_docs_finalize_tick() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_post_merge_docs_finalize_tick)" || return $?
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
  # Runs the strict merge docs-finalize preflight before its one allowed tracker tick.
  # Usage:
  #   planveyor_post_merge_docs_finalize_tick --role Architect --range BASE..HEAD --path docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md
  local role="" range="" receipt_path=""
  while (( $# > 0 )); do
    case "$1" in
      --role|--range|--path)
        [[ $# -ge 2 && -n "${2:-}" ]] || {
          echo "Usage: planveyor_post_merge_docs_finalize_tick --role Architect --range BASE..HEAD --path docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md" >&2
          return 2
        }
        case "$1" in
          --role) [[ -z "$role" ]] || { echo "planveyor_post_merge_docs_finalize_tick: duplicate --role" >&2; return 2; }; role="$2" ;;
          --range) [[ -z "$range" ]] || { echo "planveyor_post_merge_docs_finalize_tick: duplicate --range" >&2; return 2; }; range="$2" ;;
          --path) [[ -z "$receipt_path" ]] || { echo "planveyor_post_merge_docs_finalize_tick: duplicate --path" >&2; return 2; }; receipt_path="$2" ;;
        esac
        shift 2
        ;;
      *)
        echo "planveyor_post_merge_docs_finalize_tick: unknown argument $1" >&2
        return 2
        ;;
    esac
  done

  [[ "$role" == "Architect" ]] || {
    echo "planveyor_post_merge_docs_finalize_tick: --role Architect is required" >&2
    return 2
  }
  [[ -n "$range" && -n "$receipt_path" ]] || {
    echo "Usage: planveyor_post_merge_docs_finalize_tick --role Architect --range BASE..HEAD --path docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md" >&2
    return 2
  }

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tracker_path=""
  tracker_path="$(_planveyor_merge_tracker_path)" || return $?

  local base="" head="" expected_range=""
  base="$(_planveyor_get_range_base)" || return 1
  head="$(_planveyor_get_range_head)" || return 1
  expected_range="${base}..${head}"
  [[ "$range" == "$expected_range" ]] || {
    echo "planveyor_post_merge_docs_finalize_tick: --range must equal current ${expected_range}" >&2
    return 2
  }

  _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" >/dev/null || return $?
  planveyor_post_merge_receipt_preflight docs_finalize --role "$role" --range "$range" --path "$receipt_path" || return $?
  planveyor_merge_tracker_tick step:docs_finalize
}

planveyor_post_merge_operational_receipt() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_post_merge_operational_receipt)" || return $?
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
  # Writes schema-backed post-merge operational receipt for current merge range.
  # Usage:
  #   planveyor_post_merge_operational_receipt [--out PATH] [--record-json JSON ...] --archive-snapshot-json JSON [--print-path]
  local root="$(_planveyor_project_root)" || return $?
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  local helper="$(_planveyor_script post_merge_operational_receipt.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --repo-root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_review_risk_packet() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_review_risk_packet)" || return $?
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
  # Generates a compact range review risk packet from exact truth hosts.
  # Usage:
  #   planveyor_review_risk_packet [--range BASE..HEAD] --review-artifact PATH --post-merge-audit PATH --operational-receipt PATH --ready-to-push-closeout PATH --packetization-report PATH [--out PATH] [--json]
  local root="$(_planveyor_project_root)" || return $?
  local helper="$(_planveyor_script range_review_risk_packet.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --repo-root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_post_merge_docs_hygiene_suggest_gate() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_post_merge_docs_hygiene_suggest_gate)" || return $?
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
  # Runs report-only docs hygiene suggest and ticks only its tracker step after parseable success.
  # Usage:
  #   planveyor_post_merge_docs_hygiene_suggest_gate
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tracker_path=""
  tracker_path="$(_planveyor_merge_tracker_path)" || return $?
  _planveyor_merge_policy_validate_tracker "$root" "$tracker_path" >/dev/null || return $?
  local base="" head="" range="" b7="" h7=""
  base="$(_planveyor_get_range_base)" || return 1
  head="$(_planveyor_get_range_head)" || return 1
  range="${base}..${head}"
  b7="$(_planveyor_sha7 "$base" 2>/dev/null || true)"
  h7="$(_planveyor_sha7 "$head" 2>/dev/null || true)"

  local outdir="$root/.tmp/post_merge"
  mkdir -p "$outdir" || return 1
  local stamp; stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  local stdout_path="$outdir/docs_hygiene_suggest_range_${b7}_${h7}_${stamp}.stdout"
  local stderr_path="$outdir/docs_hygiene_suggest_range_${b7}_${h7}_${stamp}.stderr"

  local before_status="" after_status=""
  before_status="$(git -C "$root" status --short --untracked-files=no 2>/dev/null || true)"
  pushd "$root" >/dev/null || return 1
  planveyor_docs_hygiene_suggest --range "$range" >"$stdout_path" 2>"$stderr_path"
  local rc=$?
  popd >/dev/null || return 1
  if (( rc != 0 )); then
    echo "docs_hygiene_suggest gate blocked: command exited ${rc}" >&2
    echo "stdout: ${stdout_path}" >&2
    echo "stderr: ${stderr_path}" >&2
    echo 'rerun: planveyor_docs_hygiene_suggest --range "$(planveyor_range_base)..$(planveyor_range_head)"' >&2
    return $rc
  fi

  local malformed=0
  rg -q '^\[planveyor\] Range:' "$stdout_path" || malformed=1
  rg -q '^\[planveyor\] Suggested \(Owner\) command:' "$stdout_path" || malformed=1
  if rg -q 'Traceback' "$stdout_path" "$stderr_path"; then
    malformed=1
  fi
  if (( malformed )); then
    echo "docs_hygiene_suggest gate blocked: missing parse markers or traceback detected" >&2
    echo "stdout: ${stdout_path}" >&2
    echo "stderr: ${stderr_path}" >&2
    echo 'rerun: planveyor_docs_hygiene_suggest --range "$(planveyor_range_base)..$(planveyor_range_head)"' >&2
    return 2
  fi

  after_status="$(git -C "$root" status --short --untracked-files=no 2>/dev/null || true)"
  if [[ "$before_status" != "$after_status" ]]; then
    echo "docs_hygiene_suggest gate blocked: report-only command changed tracked git status before tracker tick" >&2
    echo "stdout: ${stdout_path}" >&2
    echo "stderr: ${stderr_path}" >&2
    echo 'rerun: planveyor_docs_hygiene_suggest --range "$(planveyor_range_base)..$(planveyor_range_head)"' >&2
    return 2
  fi

  planveyor_merge_tracker_tick step:docs_hygiene_suggest || return $?
  echo "[planveyor] docs_hygiene_suggest gate: ticked step:docs_hygiene_suggest"
  echo "[planveyor] docs_hygiene_suggest gate: stdout=${stdout_path}"
  echo "[planveyor] docs_hygiene_suggest gate: stderr=${stderr_path}"
  echo "[planveyor] docs_hygiene_suggest gate: suggested git rm was not executed"
}

planveyor_merge_bundle_report() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_bundle_report)" || return $?
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
  # Read-only final merge bundle report for Architect/Owner handoff before push.
  # Usage:
  #   planveyor_merge_bundle_report [--format plain|json] [--tracker PATH]
  local root="$(_planveyor_project_root)" || return $?
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  local helper="$(_planveyor_script merge_bundle_report.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_verify() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_verify)" || return $?
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
  # Verifies workstream integrity (portability suite first) via a registry of
  # independent checks, emitting a summary report + responsibility interpretation.
  # Read-only: never ticks tracker steps or pushes. Mirrors the manual
  # verification matrix run across worktrees (e.g. DoD 1204 under --scope all,
  # corruption/allowlist sweeps); future modules register themselves.
  # Usage:
  #   planveyor_verify [--format plain|json] [--full | --module NAME] [--repo-root PATH]
  local root="$(_planveyor_project_root)" || return $?
  local helper="$(_planveyor_script verify_suite.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --repo-root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_post_merge_ready_to_push_closeout() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_post_merge_ready_to_push_closeout)" || return $?
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
  # Fail-closed local commit/tick helper for step:ready_to_push; writes terminal companion proof; on operational blockers prints why_blocked plus safe staging_command/pathspec_file; never pushes.
  # Usage:
  #   planveyor_post_merge_ready_to_push_closeout [--format plain|json] [--tracker PATH]
  local root="$(_planveyor_project_root)" || return $?
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  local helper="$(_planveyor_script post_merge_ready_to_push_closeout.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_merge_range_verdict_digest() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_merge_range_verdict_digest)" || return $?
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
  # Read-only final owner digest over bundle report, risk packet, and ready_to_push proof; never stages or pushes.
  # Usage:
  #   planveyor_merge_range_verdict_digest [--format plain|json] [--tracker PATH] [--range BASE..HEAD] [--risk-packet PATH]
  local root="$(_planveyor_project_root)" || return $?
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  local helper="$(_planveyor_script merge_range_verdict_digest.py)"
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" --content-profile-id "$content_profile_id" --repo-root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

_planveyor_get_pybin() {
  # The loaded runtime pinned this interpreter before any project content was
  # read.  A target-local .planveyor.pybin and ambient PYBIN are not authority.
  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == pinned ]]; then
    _planveyor_authority_python
    return $?
  fi
  if [[ -n "${PYBIN:-}" && "${PYBIN}" == /* && -x "${PYBIN}" ]]; then
    echo "$PYBIN"
    return 0
  fi
  if [[ -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
    echo "${CONDA_PREFIX}/bin/python"
    return 0
  fi
  command -v python3 2>/dev/null || {
    echo "Missing trusted Python: select the planveyor environment in PATH." >&2
    return 1
  }
}

_planveyor_python_dispatch() {
  local -x PLANVEYOR_LEGACY_PROFILE="${PLANVEYOR_LEGACY_PROFILE:-}"
  local pybin="$1"
  shift
  local -a entry_args=("$@")
  [[ "${entry_args[1]:-}" != -B ]] || entry_args=("${entry_args[@]:1}")
  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == pinned &&
        "${entry_args[1]:-}" == "${_PLANVEYOR_AUTHORITY_RUNTIME_ROOT}/scripts/"*.py ]]; then
    local entry_path="${entry_args[1]}"
    entry_args=("${entry_args[@]:1}")
    if _planveyor_authority_context_carrier_present; then
      local parent_context=""
      parent_context="$(_planveyor_authority_parent_context_json)" || return $?
      local -x _PLANVEYOR_AUTHORITY_CONTEXT_V1="$parent_context"
    fi
    _planveyor_authority_bridge python-entry --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" --path "$entry_path" -- "${entry_args[@]}"
    return $?
  fi
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$@"
}

_planveyor_py_authority_stdin() {
  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == pinned ]]; then
    if _planveyor_authority_context_carrier_present; then
      local parent_context=""
      parent_context="$(_planveyor_authority_parent_context_json)" || return $?
      local -x _PLANVEYOR_AUTHORITY_CONTEXT_V1="$parent_context"
    fi
    _planveyor_authority_bridge python-stdin --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" -- "$@"
  else
    _planveyor_py - "$@"
  fi
}

_planveyor_py_any_authority_stdin() {
  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == pinned ]]; then
    _planveyor_py_authority_stdin "$@"
  else
    _planveyor_py_any - "$@"
  fi
}

_planveyor_py() {
  local pybin
  pybin="$(_planveyor_get_pybin)" || return 1
  _planveyor_python_dispatch "$pybin" "$@"
}

_planveyor_py_any() {
  # Best-effort python runner:
  # - Prefer the loaded runtime interpreter; otherwise a caller-selected Python.
  # - Fallback to system python3/python for neutral utilities
  local pybin=""
  pybin="$(_planveyor_get_pybin 2>/dev/null || true)"
  if [[ -n "${pybin//[[:space:]]/}" && -x "$pybin" ]]; then
    _planveyor_python_dispatch "$pybin" "$@"
    return $?
  fi
  if command -v python3 >/dev/null 2>&1; then
    _planveyor_python_dispatch python3 "$@"
    return $?
  fi
  if command -v python >/dev/null 2>&1; then
    _planveyor_python_dispatch python "$@"
    return $?
  fi
  echo "Missing trusted Python: select the planveyor environment in the invoking PATH." >&2
  return 1
}

_planveyor_role_run_probe_reject() {
  local operation="${1:-}" reason_code="${2:-usage_error}" probe_id="${3:-}"
  _planveyor_py_any - "$operation" "$reason_code" "$probe_id" <<'PY'
import json
import sys

print(json.dumps({
    "schema_version": "role_run_probe_readback.v1",
    "ok": False,
    "operation": sys.argv[1],
    "probe_id": sys.argv[3] or None,
    "probe_state": "invalid",
    "reason_code": sys.argv[2],
    "mutation_performed": False,
    "manifest_path": None,
    "fixture_root": None,
    "lease_state": "absent",
    "target_plan": None,
}, sort_keys=True))
PY
}

planveyor_role_run_probe() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_role_run_probe)" || return $?
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
  local usage="Usage: planveyor_role_run_probe run --kind retention --target-plan docs/plans/<plan>.md --scenario <orphan_output|malformed_receipt|active_lease|terminal_recovery> --json | planveyor_role_run_probe <inspect|mark-interrupted|recover> --probe-id <probe_id> --json"
  local operation="${1:-}" probe_kind="" scenario="" target_plan="" probe_id="" json=0
  [[ -n "${operation//[[:space:]]/}" ]] || {
    echo "$usage" >&2
    _planveyor_role_run_probe_reject "" usage_error ""
    return 2
  }
  shift
  case "$operation" in
    --help|-h)
      echo "$usage" >&2
      return 0
      ;;
    run|inspect|mark-interrupted|recover) ;;
    *)
      echo "$usage" >&2
      _planveyor_role_run_probe_reject "$operation" usage_error ""
      return 2
      ;;
  esac
  local seen_kind=0 seen_scenario=0 seen_target=0 seen_probe=0 seen_json=0
  while (( $# > 0 )); do
    case "${1:-}" in
      --kind)
        (( seen_kind == 0 && $# >= 2 )) || {
          _planveyor_role_run_probe_reject "$operation" usage_error "$probe_id"
          return 2
        }
        seen_kind=1
        shift
        probe_kind="${1:-}"
        ;;
      --scenario)
        (( seen_scenario == 0 && $# >= 2 )) || {
          _planveyor_role_run_probe_reject "$operation" usage_error "$probe_id"
          return 2
        }
        seen_scenario=1
        shift
        scenario="${1:-}"
        ;;
      --target-plan)
        (( seen_target == 0 && $# >= 2 )) || {
          _planveyor_role_run_probe_reject "$operation" usage_error "$probe_id"
          return 2
        }
        seen_target=1
        shift
        target_plan="${1:-}"
        ;;
      --probe-id)
        (( seen_probe == 0 && $# >= 2 )) || {
          _planveyor_role_run_probe_reject "$operation" usage_error "$probe_id"
          return 2
        }
        seen_probe=1
        shift
        probe_id="${1:-}"
        ;;
      --json)
        (( seen_json == 0 )) || {
          _planveyor_role_run_probe_reject "$operation" usage_error "$probe_id"
          return 2
        }
        seen_json=1
        json=1
        ;;
      --help|-h)
        echo "$usage" >&2
        return 0
        ;;
      *)
        _planveyor_role_run_probe_reject "$operation" usage_error "$probe_id"
        return 2
        ;;
    esac
    shift
  done
  (( json == 1 )) || {
    echo "$usage" >&2
    _planveyor_role_run_probe_reject "$operation" usage_error "$probe_id"
    return 2
  }
  if [[ "$operation" == "run" ]]; then
    if [[ "$probe_kind" != "retention" ]]; then
      _planveyor_role_run_probe_reject "$operation" allowlist_rejected ""
      return 2
    fi
    case "$scenario" in
      orphan_output|malformed_receipt|active_lease|terminal_recovery) ;;
      *)
        _planveyor_role_run_probe_reject "$operation" allowlist_rejected ""
        return 2
        ;;
    esac
    if (( seen_target != 1 || seen_probe != 0 )); then
      _planveyor_role_run_probe_reject "$operation" usage_error ""
      return 2
    fi
  elif (( seen_probe != 1 || seen_kind != 0 || seen_scenario != 0 || seen_target != 0 )); then
    _planveyor_role_run_probe_reject "$operation" usage_error "$probe_id"
    return 2
  fi
  local root=""
  root="$(_planveyor_project_root)" || return $?
  _planveyor_role_run_probe_impl "$root" "$operation" "$probe_kind" "$scenario" "$target_plan" "$probe_id"
}

_planveyor_codex_session_stats_script() {
  # Prefer the canonical repo copy (keeps behavior consistent across git worktrees).
  local root="$(_planveyor_root)"
  local p="$(_planveyor_script codex_session_stats.py)"
  [[ -r "$p" ]] && { echo "$p"; return 0; }
  echo "$root/scripts/codex_session_stats.py"
}

_planveyor_session_missing_recovery() {
  local session_key="${1:-}"
  case "$session_key" in
    manager) echo "Missing session id. Initialize it first: planveyor_manager_init" >&2 ;;
    architect) echo "Missing session id. Initialize it first: planveyor_arch_init" >&2 ;;
    planner) echo "Missing session id. Initialize it first: planveyor_planner_init" >&2 ;;
    coder) echo "Missing session id. Initialize it first: planveyor_coder_init" >&2 ;;
    reviewer) echo "Missing session id. Initialize it first: planveyor_reviewer_init" >&2 ;;
    reviewer_code_risk) echo "Missing session id. Initialize it first: planveyor_reviewer_code_risk_init" >&2 ;;
    reviewer_code_contracts) echo "Missing session id. Initialize it first: planveyor_reviewer_code_contracts_init" >&2 ;;
    *) echo "Missing session id. Set it first: planveyor_session_set ${session_key:-<role>} <SESSION_ID>" >&2 ;;
  esac
  return 1
}

_planveyor_session_sid_ensure_in_effective_codex_home() {
  # Ensures that the session id stored in `.planveyor.session.<key>` exists under the
  # current effective CODEX_HOME. If it exists only under another home, clone the
  # rollout(s) into the effective home and update the session file.
  #
  # Echoes the sid to use.
  local session_key="${1:-}"
  local profile_hint="${2:-}"
  [[ -n "${session_key//[[:space:]]/}" ]] || return 1

  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_session_sid_ensure_in_effective_codex_home)" || return $?
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

  local root="$(_planveyor_root)"
  local sid=""
  sid="$(planveyor_session "$session_key" 2>/dev/null || true)"
  [[ -n "${sid//[[:space:]]/}" && "$sid" != "<SESSION_ID>" ]] || _planveyor_session_missing_recovery "$session_key"
  [[ -n "${sid//[[:space:]]/}" && "$sid" != "<SESSION_ID>" ]] || return $?

  # A persisted SID is an authority-bearing pointer.  Validate its matching
  # receipt before session discovery can clone a rollout or rewrite that
  # pointer in the effective CODEX_HOME.
  _planveyor_session_authority_resume_validate "$session_key" "$sid" || return $?

  local codex_home="$(_planveyor_codex_home_effective)"
  local stats_script="$(_planveyor_codex_session_stats_script)"

  if _planveyor_py_any "$stats_script" --sid "$sid" --codex-home "$codex_home" --mode quick --format kv >/dev/null 2>&1; then
    echo "$sid"
    return 0
  fi

  local meta_out=""
  meta_out="$(_planveyor_py_any "$stats_script" --sid "$sid" --codex-home "$codex_home" --search-all --mode quick --format kv 2>/dev/null || true)"
  local src_home=""
  src_home="$(printf '%s\n' "$meta_out" | awk -F= '$1=="codex_home" {print $2; exit}')"
  if [[ -z "${src_home//[[:space:]]/}" ]]; then
    echo "Session not found in effective CODEX_HOME: ${codex_home}" >&2
    echo "Hint: open Codex in that home, then update the stored sid:" >&2
    echo "  CODEX_HOME=\"${codex_home}\" codex resume" >&2
    echo "  planveyor_session_set ${session_key} <SESSION_ID>" >&2
    return 1
  fi

  if [[ "$src_home" == "$codex_home" ]]; then
    echo "Session exists in CODEX_HOME=${codex_home} but could not be read. Rerun with PLANVEYOR_CODEX_PASSTHROUGH=1 and debug." >&2
    return 1
  fi

  local clone_script="$(_planveyor_script codex_session_clone.py)"
  [[ -r "$clone_script" ]] || clone_script="$root/scripts/codex_session_clone.py"
  [[ -r "$clone_script" ]] || {
    echo "Missing clone script: ${clone_script}" >&2
    return 1
  }

  # The remaining clone and pointer update are writers.  Revalidate the same
  # frozen context immediately before the first of those effects.
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?

  echo "Migrating session '${session_key}' into effective CODEX_HOME: ${codex_home}" >&2
  echo "  src: ${src_home}" >&2
  echo "  sid: ${sid}" >&2

  local clone_json=""
  clone_json="$(_planveyor_py_any "$clone_script" --sid "$sid" --src-codex-home "$src_home" --dst-codex-home "$codex_home" --write 2>&1)" || {
    echo "$clone_json" >&2
    return 1
  }

  local new_sid=""
  new_sid="$(_planveyor_py_any -c 'import json,sys; print(json.loads(sys.stdin.read()).get("sid_new",""))' <<< "$clone_json" 2>/dev/null || true)"
  [[ -n "${new_sid//[[:space:]]/}" ]] || {
    echo "Failed to parse cloned sid. Output:" >&2
    echo "$clone_json" >&2
    return 1
  }

  local meta="runner=codex"
  [[ -n "${profile_hint//[[:space:]]/}" ]] && meta="${meta} profile=${profile_hint}"
  meta="${meta} codex_home=${codex_home} cloned_from=${src_home} sid_src=${sid}"
  planveyor_session_set "$session_key" "$new_sid" "$meta" || return 1

  echo "$new_sid"
  return 0
}

_planveyor_role_session_sid_ensure_local_or_init() {
  # Ensures a role session exists in the current effective CODEX_HOME.
  # If the stored sid cannot be resolved or migrated there, boot a fresh local session.
  #
  # Usage:
  #   _planveyor_role_session_sid_ensure_local_or_init <session_key> <profile_hint> <init_fn>
  #
  # Echoes the sid to use.
  local session_key="${1:-}"
  local profile_hint="${2:-}"
  local init_fn="${3:-}"
  [[ -n "${session_key//[[:space:]]/}" && -n "${init_fn//[[:space:]]/}" ]] || return 1

  # Do not turn an authority-unbound persisted SID into an implicit fresh
  # provider launch.  A missing or stale local rollout may initialize; an
  # invalid stored pointer must be rejected before any clone/write/provider.
  local stored_sid=""
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local session_file="${root}/.planveyor.session.${session_key}"
  if [[ -e "$session_file" || -L "$session_file" ]]; then
    [[ -f "$session_file" && ! -L "$session_file" ]] || {
      echo "Invalid session pointer (expected a regular file): ${session_file}" >&2
      return 1
    }
    stored_sid="$(planveyor_session "$session_key")" || return $?
  fi
  [[ "$stored_sid" == "<SESSION_ID>" ]] && stored_sid=""
  if [[ -n "${stored_sid//[[:space:]]/}" ]]; then
    _planveyor_session_authority_resume_validate "$session_key" "$stored_sid" || return $?
  fi

  local sid=""
  sid="$(_planveyor_session_sid_ensure_in_effective_codex_home "$session_key" "$profile_hint" 2>/dev/null || true)"
  if [[ -n "${sid//[[:space:]]/}" && "$sid" != "<SESSION_ID>" ]]; then
    echo "$sid"
    return 0
  fi

  typeset -f "$init_fn" >/dev/null 2>&1 || {
    echo "Missing init function for session '${session_key}': ${init_fn}" >&2
    return 1
  }

  echo "Session '${session_key}' is missing or stale for effective CODEX_HOME; starting a new local session via ${init_fn}." >&2
  local init_out=""
  local rc=0
  init_out="$($init_fn 2>&1)" || rc=$?
  [[ -n "${init_out//[[:space:]]/}" ]] && printf '%s\n' "$init_out" >&2
  (( rc == 0 )) || return $rc

  sid="$(planveyor_session "$session_key" 2>/dev/null || true)"
  [[ -n "${sid//[[:space:]]/}" && "$sid" != "<SESSION_ID>" ]] || {
    echo "Failed to capture sid after ${init_fn} for session '${session_key}'." >&2
    return 1
  }
  echo "$sid"
  return 0
}

_planveyor_architect_session_sid_ensure_local_or_init() {
  local profile=""
  profile="$(_planveyor_profile_for_role_mode architect main)" || return $?

  local sid=""
  sid="$(_planveyor_role_session_sid_ensure_local_or_init architect "$profile" planveyor_arch_init)" || return 1

  if [[ -z "${profile//[[:space:]]/}" ]]; then
    echo "$sid"
    return 0
  fi

  local codex_home="$(_planveyor_codex_home_effective)"
  if _planveyor_codex_session_model_matches_profile "$sid" "$profile" "$codex_home"; then
    echo "$sid"
    return 0
  fi

  local actual_model=""
  actual_model="$(_planveyor_codex_session_stat_value "$sid" model "$codex_home" 2>/dev/null || true)"
  local expected_model=""
  expected_model="$(_planveyor_codex_expected_model_for_profile "$profile")" || return $?
  echo "Stored architect session sid=${sid} uses stale model ${actual_model:-unknown}; starting a new local architect session on ${expected_model:-$profile}." >&2

  local init_out=""
  local rc=0
  init_out="$(planveyor_arch_init 2>&1)" || rc=$?
  [[ -n "${init_out//[[:space:]]/}" ]] && printf '%s\n' "$init_out" >&2
  (( rc == 0 )) || return $rc

  sid="$(planveyor_session architect 2>/dev/null || true)"
  [[ -n "${sid//[[:space:]]/}" && "$sid" != "<SESSION_ID>" ]] || {
    echo "Failed to capture architect sid after planveyor_arch_init." >&2
    return 1
  }
  echo "$sid"
  return 0
}

_planveyor_manager_session_sid_ensure_local_or_init() {
  local profile=""
  profile="$(_planveyor_profile_for_role_mode manager main)" || return $?
  _planveyor_role_session_sid_ensure_local_or_init manager "$profile" planveyor_manager_init
}

_planveyor_codex_expected_model_for_profile() {
  local profile="${1:-}" content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  case "$content_profile_id" in
    planveyor)
      _planveyor_source_module home_runtime.zsh || return $?
      _planveyor_private_home_expected_model_for_profile "$profile"
      ;;
    *) return 0 ;;
  esac
}

_planveyor_codex_session_stat_value() {
  local sid="${1:-}"
  local key="${2:-}"
  local codex_home="${3:-}"
  [[ -n "${sid//[[:space:]]/}" && -n "${key//[[:space:]]/}" ]] || return 1
  [[ -n "${codex_home//[[:space:]]/}" ]] || codex_home="$(_planveyor_codex_home_effective)"

  local stats_script="$(_planveyor_codex_session_stats_script)"
  local meta_out=""
  meta_out="$(_planveyor_py_any "$stats_script" --sid "$sid" --codex-home "$codex_home" --search-all --mode quick --format kv 2>/dev/null || true)"
  [[ -n "${meta_out//[[:space:]]/}" ]] || return 1

  local kv=""
  while IFS= read -r kv || [[ -n "$kv" ]]; do
    [[ "$kv" == *=* ]] || continue
    local k="${kv%%=*}"
    local v="${kv#*=}"
    [[ "$k" == "$key" ]] || continue
    echo "$v"
    return 0
  done <<< "$meta_out"
  return 1
}

_planveyor_codex_session_model_matches_profile() {
  local sid="${1:-}"
  local profile="${2:-}"
  local codex_home="${3:-}"
  [[ -n "${sid//[[:space:]]/}" ]] || return 1
  [[ -n "${profile//[[:space:]]/}" ]] || return 0

  local expected_model=""
  expected_model="$(_planveyor_codex_expected_model_for_profile "$profile")" || return 1
  [[ -n "${expected_model//[[:space:]]/}" ]] || return 0

  local actual_model=""
  actual_model="$(_planveyor_codex_session_stat_value "$sid" model "$codex_home" 2>/dev/null || true)"
  [[ -n "${actual_model//[[:space:]]/}" ]] || return 0
  [[ "$actual_model" == "$expected_model" ]]
}

_planveyor_extract_status_value() {
  # Input: "7:**Status:** Ready for Review" (from planveyor_status_line)
  local status_line="$1"
  [[ -n "${status_line//[[:space:]]/}" ]] || return 1
  local line="${status_line#*:}"
  local check="$line"
  check="${check#"${check%%[![:space:]]*}"}"
  if [[ "$check" == '>'* ]]; then
    check="${check#>}"
    check="${check#"${check%%[![:space:]]*}"}"
  fi
  if [[ "$check" == [\-\*\+][[:space:]]* ]]; then
    check="${check#?}"
    check="${check#"${check%%[![:space:]]*}"}"
  fi
  [[ "$check" == "**Status:**"* ]] || return 1
  local v="${check#\*\*Status:\*\*}"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  v="${v//$'\r'/}"
  [[ -n "${v//[[:space:]]/}" ]] || return 1
  echo "$v"
}

_planveyor_status_value_is_done_like() {
  local status_value="$1"
  [[ -n "${status_value//[[:space:]]/}" ]] || return 1
  local s="${status_value:l}"
  s="${s//$'
'/}"
  s="${s//$'	'/ }"
  while [[ "$s" == *"  "* ]]; do s="${s//  / }"; done
  while [[ "$s" == " "* ]]; do s="${s# }"; done
  while [[ "$s" == *" " ]]; do s="${s% }"; done
  [[ "$s" == done* || "$s" == "✅ done"* ]]
}

_planveyor_suggest_runner_from_status() {
  local status_value="$1"
  local s="${status_value:l}"
  # Normalize whitespace to avoid "Ready for Planner  " -> unknown.
  s="${s//$'\r'/}"
  s="${s//$'\t'/ }"
  while [[ "$s" == *"  "* ]]; do s="${s//  / }"; done
  while [[ "$s" == " "* ]]; do s="${s# }"; done
  while [[ "$s" == *" " ]]; do s="${s% }"; done
  case "$s" in
    draft*) echo "planveyor_arch" ;;
    "architect initial draft") echo "planveyor_arch_initial" ;;
    "architect draft"|"architect response"|"ready for architect response"|"ready for arch review"|"architect arch review") echo "planveyor_arch" ;;
    "ready for planner"|"planner intake"|"planner finalize") echo "planveyor_planner" ;;
    "ready for coder"|"coder intake"|"in progress") echo "planveyor_coder" ;;
    "ready for review"|"reviewer intake"|"reviewer code review"|"reviewer visual review") echo "planveyor_reviewer" ;;
    superseded|done) echo "(Owner)" ;;
    *) echo "(unknown)" ;;
  esac
}

_planveyor_plan_oracle_summary() {
  # Emits: runtime_class<TAB>queue_closeout_kind<TAB>queue_closeout_ready.
  # This is best-effort for owner-facing list helpers: if oracle fails, callers
  # keep legacy executable behavior instead of accidentally hiding a plan.
  local plan_path="$1"
  [[ -n "${plan_path//[[:space:]]/}" ]] || return 1

  local root="$(_planveyor_project_root)" || return $?
  local plan_fs="$plan_path"
  [[ "$plan_fs" == /* ]] || plan_fs="${root}/${plan_fs}"
  [[ -f "$plan_fs" ]] || return 1

  local oracle_py="$(_planveyor_script plan_status_oracle.py)"
  [[ -f "$oracle_py" ]] || return 1

  local payload=""
  payload="$(_planveyor_py_any "$oracle_py" "$plan_fs" --json 2>/dev/null || true)"
  [[ -n "${payload//[[:space:]]/}" ]] || return 1

  printf '%s\n' "$payload" | _planveyor_py_any -c '
import json
import sys

try:
    data = json.loads(sys.stdin.read())
except json.JSONDecodeError:
    sys.exit(1)

runtime_class = data.get("runtime_class") or "executable"
queue_kind = data.get("queue_closeout_kind") or "not_ready"
queue_ready = "true" if data.get("queue_closeout_ready") else "false"
print(f"{runtime_class}\t{queue_kind}\t{queue_ready}")
'
}

_planveyor_plan_status_line_lenient() {
  # For listing/overview only (older plans may contain extra status notes).
  # Returns the first header-like **Status:** line if present, tolerating
  # markdown bullets in report metadata ("- **Status:** ✅ Done").
  local plan_path="$1"
  [[ -f "$plan_path" ]] || return 1

  local -a non_quote
  non_quote=()
  local -a quote
  quote=()

  local line=""
  local line_no=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    ((line_no++))

    local trimmed="$line"
    trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}"
    [[ "$trimmed" == "##"* ]] && break

    local is_quote=0
    local check="$trimmed"
    if [[ "$check" == '>'* ]]; then
      is_quote=1
      check="${check#>}"
      check="${check#"${check%%[![:space:]]*}"}"
    fi
    if [[ "$check" == [\-\*\+][[:space:]]* ]]; then
      check="${check#?}"
      check="${check#"${check%%[![:space:]]*}"}"
    fi

    if [[ "$check" == "**Status:**"* ]]; then
      [[ "$check" == *'|'* ]] && continue
      if (( is_quote )); then
        quote+=("${line_no}:${line}")
      else
        non_quote+=("${line_no}:${line}")
      fi
    fi
  done < "$plan_path"

  if (( ${#non_quote} > 0 )); then
    echo "${non_quote[1]}"
    return 0
  fi
  if (( ${#quote} > 0 )); then
    echo "${quote[1]}"
    return 0
  fi
  return 1
}

_planveyor_table_cell() {
  # `column -t` collapses trailing empty columns. Use single-space placeholder for blank cells.
  local v="${1:-}"
  v="${v//$'\r'/}"
  [[ -n "${v//[[:space:]]/}" ]] || { echo " "; return 0; }
  echo "$v"
}

_planveyor_list_public_commands() {
  # Lists all public `planveyor_*` functions currently loaded (sorted).
  # Used by `planveyor_help` to avoid drift when new commands are added.
  local -a names
  names=(${(k)functions})
  names=(${(M)names:#planveyor_*})
  # Hide legacy aliases from help catalog to keep naming consistent.
  names=(${names:#planveyor_bare_entrypoints_install})
  names=(${(o)names})
  print -l -- "${names[@]}"
}

_planveyor_help_cmd_usage() {
  local cmd="${1:-}"
  [[ -n "${cmd//[[:space:]]/}" ]] || { echo " "; return 0; }
  case "$cmd" in
    planveyor_consumer_init) echo "planveyor_consumer_init /absolute/new/sibling --source-commit <full-40-hex> [--author-name <name> --author-email <email>] (without them the init commit author is Planveyor Initializer)" ;;
    planveyor_consumer_doctor) echo "planveyor_consumer_doctor (use --project /absolute/sibling before command)" ;;
    planveyor_sibling) echo "planveyor sibling <init|plan|architect|answer|run|close|ready|upgrade> (help: planveyor sibling --help)" ;;
    planveyor_plan_lint) echo "planveyor_plan_lint docs/plans/<plan>.md" ;;
    planveyor_runtime_py) echo "planveyor_runtime_py <approved-helper.py> [args...] (use --project /absolute/sibling)" ;;
    planveyor_contract_upgrade) echo "planveyor_contract_upgrade --source-commit <full-40-hex> [--accept-candidate] (use --project /absolute/sibling)" ;;
    planveyor_show) echo "planveyor_show [--all|--manual|--collab|--process] [--wide]" ;;
    planveyor_help) echo "planveyor_help [--all|--manual|--collab|--process|<command>]" ;;
    planveyor_show_manual) echo "planveyor_show_manual [--wide]" ;;
    planveyor_show_collab) echo "planveyor_show_collab [--wide|--compact]" ;;
    planveyor_show_process) echo "planveyor_show_process [--wide]" ;;

    planveyor_session) echo "planveyor_session <key>" ;;
    planveyor_session_set) echo "planveyor_session_set <key> <SID> [META]" ;;
    planveyor_rollout_packet_create) echo "planveyor_rollout_packet_create <target_repo> <topic_slug> [--source-plan docs/plans/<...>.md] [--target-kind plan_adoption|mirror_sync|checker_rollout|consumer_only] [--queue-after-import yes|no] [--dry-run]" ;;
    planveyor_rollout_packet_show) echo "planveyor_rollout_packet_show docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md [--raw]" ;;
    planveyor_rollout_packet_import_instructions) echo "planveyor_rollout_packet_import_instructions docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md [--print-target-plan-seed]" ;;
    planveyor_rollout_packet_lint) echo "planveyor_rollout_packet_lint (--all | docs/rollout_packets/<packet>.md|docs/rollout_packets) [--json]" ;;
    planveyor_rollout_packet_ack) echo "planveyor_rollout_packet_ack --packet docs/rollout_packets/<...>.md --status imported --target-plan docs/plans/<...>.md | --status superseded|cancelled --reason <reason>" ;;
    planveyor_rollout_packet_query) echo "planveyor_rollout_packet_query [--status open|imported|superseded|cancelled|all] [--json]" ;;
    planveyor_rollout_packet_reconcile) echo "planveyor_rollout_packet_reconcile --report [--older-than-days N] [--target-root PATH --target-repo planveyor] [--json]" ;;
    planveyor_rollout_packet_outcome_set) echo "planveyor_rollout_packet_outcome_set --target-plan docs/plans/<...>.md --packet-id <id> --packet-path docs/rollout_packets/<...>.md --outcome <canonical-or-alias>" ;;
    planveyor_shared_docs_mirror_drift) echo "planveyor_shared_docs_mirror_drift [--target-root PATH] [--source-root PATH] [--json] [--fail-on-drift]" ;;
    planveyor_mirror_strict_gate) echo "planveyor_mirror_strict_gate [--target-root PATH] [--source-root PATH] [--json]" ;;
    planveyor_upstream_request_show) echo "planveyor_upstream_request_show docs/upstream_packets/<YYMMDD_HHMM>_<origin_repo>_<topic>.md [--raw]" ;;
    planveyor_upstream_request_import) echo "planveyor_upstream_request_import --packet docs/upstream_packets/<...>.md [--owner Architect] [--promotion-class canon_update] [--dry-run]" ;;
    planveyor_upstream_request_ack) echo "planveyor_upstream_request_ack --packet docs/upstream_packets/<...>.md --source-decision-ref docs/plans/<...> [--source-execution-ref docs/plans/<...>] [--dry-run]" ;;
    planveyor_upstream_request_query) echo "planveyor_upstream_request_query [--status open|imported|decided|superseded|cancelled|all] [--origin-repo <sibling>] [--json]" ;;
    planveyor_bare_entrypoints_doctor) echo "planveyor_bare_entrypoints_doctor [--bin-dir DIR]" ;;
    planveyor_ai_gate) echo "planveyor_ai_gate --range BASE..HEAD --policy docs/tools/ai_gate_policy.example.json [--receipt-path docs/reviews/<...>_ai_gate_<range>.json]" ;;
    planveyor_ai_gate_smoke) echo "planveyor_ai_gate_smoke --receipt-path .tmp/planveyor_ai_gate_smoke.json" ;;

    planveyor_plan_set) echo "planveyor_plan_set <PLAN_PATH>" ;;
    planveyor_q_set) echo "planveyor_q_set <PLAN_PATH...> --for-manager-mode <manager-collab|manager-custom-pipeline> | planveyor_q_set --status <STATUS...> --for-manager-mode <manager-collab|manager-custom-pipeline> | planveyor_q_set --from-umbrella <PLAN_PATH> [--resume-parent <none|owner-restamp-required|run-parent-once>] --for-manager-mode <manager-collab|manager-custom-pipeline>" ;;
    planveyor_q_append) echo "planveyor_q_append [--json] <PLAN_PATH...> --for-manager-mode <manager-collab|manager-custom-pipeline>" ;;
    planveyor_q_show) echo "planveyor_q_show [--json]" ;;
    planveyor_q_history) echo "planveyor_q_history [--limit N|--json]" ;;
    planveyor_planqueue_metrics) echo "planveyor_planqueue_metrics [planqueue_metrics.py args...]" ;;
    planveyor_planqueue_metrics_json) echo "planveyor_planqueue_metrics_json [planqueue_metrics.py args...]" ;;
    planveyor_planning_wave_readback) echo "planveyor_planning_wave_readback [planning_wave_readback.py args...]" ;;
    planveyor_planning_wave_readback_json) echo "planveyor_planning_wave_readback_json [planning_wave_readback.py args...]" ;;
    planveyor_wave_telemetry_report) echo "planveyor_wave_telemetry_report [wave_telemetry_report.py args...]" ;;
    planveyor_wave_telemetry_report_json) echo "planveyor_wave_telemetry_report_json [wave_telemetry_report.py args...]" ;;
    planveyor_docs_closeout) echo "planveyor_docs_closeout <PLAN_PATH> [--followups-capture-cycle-id <UUIDv4>] [--json]" ;;
    planveyor_analysis_init) echo "planveyor_analysis_init [PLAN_PATH]" ;;
    planveyor_q_small_slice) echo "planveyor_q_small_slice <PLAN_PATH> [--json]" ;;
    planveyor_q_next_json) echo "planveyor_q_next_json --manager-mode <manager-collab|manager-custom-pipeline>" ;;
    planveyor_q_small_slice_json) echo "planveyor_q_small_slice_json <PLAN_PATH>" ;;
    planveyor_q_advance_json) echo "planveyor_q_advance_json <Done|Superseded> --manager-mode <manager-collab|manager-custom-pipeline>" ;;
    planveyor_q_closeout_json) echo "planveyor_q_closeout_json --manager-mode <manager-collab|manager-custom-pipeline>" ;;
    planveyor_q_stop_json) echo "planveyor_q_stop_json <REASON> [--source-plan <PLAN_PATH>]" ;;
    planveyor_q_planpath_override_json) echo "planveyor_q_planpath_override_json <PLAN_PATH> [REASON]" ;;
    planveyor_q_history_json) echo "planveyor_q_history_json [--limit N]" ;;
    planveyor_q_final_report) echo "planveyor_q_final_report [--format plain|json] [--repo-root PATH] [--state-path PATH] [--log-path PATH]" ;;
    planveyor_q_clear) echo "planveyor_q_clear [--json]" ;;
    planveyor_q_recover) echo "planveyor_q_recover [--json]" ;;
    planveyor_decomposition_init) echo "planveyor_decomposition_init [PLAN_PATH]" ;;
    planveyor_decomposition_seed_promote) echo "planveyor_decomposition_seed_promote <NEW_PLAN_PATH> [OLD_PLAN_PATH]" ;;
    planveyor_decomposition_collab) echo "planveyor_decomposition_collab [PLAN_PATH]" ;;
    planveyor_decomposition_collab_tui) echo "planveyor_decomposition_collab_tui [PLAN_PATH] [--no-alt-screen]" ;;
    planveyor_plan_bundle) echo "planveyor_plan_bundle [--print|--check|--preflight|--scope-check|--stage|--commit-ready|--commit-exact|--closeout-json|--capture-rejected|--verify-rejected|--cleanup-rejected] <PLAN_PATH>; --commit-exact --preflight-json <path|-> (--message-auto|--message-file <path>)" ;;
    planveyor_plan_closeout_preflight) echo "planveyor_plan_closeout_preflight [--docs-closeout-json <path|->] [--json] <PLAN_PATH>" ;;
    planveyor_plan_list) echo "planveyor_plan_list [--include-non-executable] [TERMS...]" ;;
    planveyor_plan_list_status) echo "planveyor_plan_list_status <STATUS_FILTER> [--include-non-executable] [TERMS...]" ;;
    planveyor_range_set) echo "planveyor_range_set <BASE_SHA> <HEAD_SHA> [MERGE_SHA]" ;;
    planveyor_range_set_merge) echo "planveyor_range_set_merge <MERGE_SHA> [HEAD_SHA]" ;;
    planveyor_status_line) echo "planveyor_status_line <PLAN_PATH>" ;;
    planveyor_merge_init) echo "planveyor_merge_init" ;;
    planveyor_merge_tracker_init) echo "planveyor_merge_tracker_init" ;;
    planveyor_merge_tracker_ensure) echo "planveyor_merge_tracker_ensure" ;;
    planveyor_merge_tracker_next_step) echo "planveyor_merge_tracker_next_step" ;;
    planveyor_merge_tracker_tick) echo "planveyor_merge_tracker_tick step:<name>" ;;
    planveyor_merge_tracker_show) echo "planveyor_merge_tracker_show" ;;
    planveyor_merge_range_stats_json) echo "planveyor_merge_range_stats_json [BASE..HEAD | BASE HEAD]" ;;
    planveyor_post_merge_packetization_gate) echo "planveyor_post_merge_packetization_gate [--range BASE..HEAD] [--out PATH] [--create-drafts] [--json]" ;;
    planveyor_post_merge_packetization_gate_recover) echo "planveyor_post_merge_packetization_gate_recover --range BASE..HEAD [--source-plan docs/plans/<provenance-plan>.md] [--packet docs/rollout_packets/<packet>.md ...] [--stage-packets] [--format plain|json]" ;;
    planveyor_post_merge_receipt_skeleton) echo "planveyor_post_merge_receipt_skeleton <canon_sweep_receipt|docs_finalize_receipt|plan_harvest|post_merge_audit|post_merge_operational_receipt> [--out PATH]" ;;
    planveyor_post_merge_receipt_preflight) echo "planveyor_post_merge_receipt_preflight <plan_harvest|canon_sweep|post_merge_audit|packetization_gate|docs_finalize> --path PATH [--format plain|json]" ;;
    planveyor_post_merge_docs_finalize_tick) echo "planveyor_post_merge_docs_finalize_tick --role Architect --range BASE..HEAD --path docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md" ;;
    planveyor_post_merge_operational_receipt) echo "planveyor_post_merge_operational_receipt [--out PATH] [--record-json JSON ...] --archive-snapshot-json JSON [--print-path]" ;;
    planveyor_post_merge_docs_hygiene_suggest_gate) echo "planveyor_post_merge_docs_hygiene_suggest_gate" ;;
    planveyor_merge_bundle_report) echo "planveyor_merge_bundle_report [--format plain|json] [--tracker PATH]" ;;
    planveyor_post_merge_ready_to_push_closeout) echo "planveyor_post_merge_ready_to_push_closeout [--format plain|json] [--tracker PATH]" ;;
    planveyor_merge_range_verdict_digest) echo "planveyor_merge_range_verdict_digest [--format plain|json] [--tracker PATH] [--range BASE..HEAD] [--risk-packet PATH]" ;;
    planveyor_verify) echo "planveyor_verify [--format plain|json] [--full | --module NAME] [--repo-root PATH]  # default fast integrity checks; --full adds canonical unittest discovery" ;;
    planveyor_merge_next) echo "planveyor_merge_next" ;;
    planveyor_review_risk_packet) echo "planveyor_review_risk_packet [--range BASE..HEAD] --review-artifact PATH --post-merge-audit PATH --operational-receipt PATH --ready-to-push-closeout PATH --packetization-report PATH [--out PATH] [--json]" ;;
    planveyor_review_range_init) echo "planveyor_review_range_init [--force-new] [EXCLUDE_DOCS=1|0] | planveyor_review_range_init [--force-new] <BASE_SHA> <HEAD_SHA> [EXCLUDE_DOCS=1|0]" ;;
    planveyor_review_range_start) echo "planveyor_review_range_start [--force-new] [EXCLUDE_DOCS=1|0] | planveyor_review_range_start [--force-new] <BASE_SHA> <HEAD_SHA> [EXCLUDE_DOCS=1|0]" ;;
    planveyor_review_target_snapshot) echo "planveyor_review_target_snapshot <PLAN_PATH> --current-bundle [--project-root PATH]" ;;

    planveyor_runner) echo "planveyor_runner <role>" ;;
    planveyor_runner_set) echo "planveyor_runner_set <role> <runner>" ;;
    planveyor_runner_clear) echo "planveyor_runner_clear <role>" ;;
    planveyor_runner_matrix) echo "planveyor_runner_matrix [ROLES...]" ;;
    planveyor_role_runner_preflight) echo "planveyor_role_runner_preflight <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> [--json]" ;;
    planveyor_custom_role_step) echo "planveyor_custom_role_step <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> --plan <PLAN_PATH> [--timeout SECONDS] --json" ;;
    planveyor_role_run) echo "planveyor_role_run <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> [--timeout SECONDS] [--json]" ;;
    planveyor_role_run_probe) echo "planveyor_role_run_probe run --kind retention --target-plan docs/plans/<plan>.md --scenario <orphan_output|malformed_receipt|active_lease|terminal_recovery> --json | planveyor_role_run_probe <inspect|mark-interrupted|recover> --probe-id <probe_id> --json" ;;
    planveyor_role_run_receipt_check) echo "planveyor_role_run_receipt_check <receipt.json> [--run-id ID] [--session-key KEY] [--target-plan PLAN] [--pre-status STATUS] [--json]" ;;
    planveyor_profile) echo "planveyor_profile <architect|coder|planner> [main|censor]" ;;
    planveyor_profile_set) echo "planveyor_profile_set <architect|coder|planner> <PROFILE> [main|censor]" ;;
    planveyor_profile_clear) echo "planveyor_profile_clear <architect|coder|planner> [main|censor]" ;;

    planveyor_owner_answers_set) echo "planveyor_owner_answers_set <role> [PLAN_PATH] <<'EOF' ... EOF" ;;
    planveyor_clear_owner_answers) echo "planveyor_clear_owner_answers" ;;

    planveyor_doc_lint) echo "planveyor_doc_lint" ;;
    planveyor_docs_hygiene_list) echo "planveyor_docs_hygiene_list [BASE..HEAD|BASE HEAD]" ;;
    planveyor_docs_hygiene_suggest) echo "planveyor_docs_hygiene_suggest [--range BASE..HEAD|BASE HEAD] [--include-followups] [--include-snapshots] [--verbose] [--fix-missing-blocks dry-run|apply]" ;;
    planveyor_docs_hygiene_archive) echo "planveyor_docs_hygiene_archive --range BASE..HEAD [--apply]" ;;
    planveyor_docs_archive_snapshot_info) echo "planveyor_docs_archive_snapshot_info [--db PATH] [--json]" ;;
    planveyor_docs_archive_snapshot_export) echo "planveyor_docs_archive_snapshot_export [--db PATH] [--backend git_text_export|git_whole_sqlite|s3_minio_sqlite] [--output-dir DIR] [--force]" ;;
    planveyor_docs_archive_snapshot_validate) echo "planveyor_docs_archive_snapshot_validate --manifest PATH [--verify-artifact] [--object-file PATH]" ;;
    planveyor_docs_archive_snapshot_restore) echo "planveyor_docs_archive_snapshot_restore --manifest PATH --dest-db PATH [--replace] [--object-file PATH] [--query TEXT] [--expect-min-hits N]" ;;
    planveyor_docs_retrieve_log) echo "planveyor_docs_retrieve_log" ;;
    planveyor_docs_retrieve_outcome_log) echo "planveyor_docs_retrieve_outcome_log" ;;
    planveyor_docs_retrieve_read_log) echo "planveyor_docs_retrieve_read_log" ;;
    planveyor_docs_retrieve_metrics) echo "planveyor_docs_retrieve_metrics [--query-log PATH] [--outcome-log PATH] [--read-log PATH] [--format text|json]" ;;
    planveyor_docs_lookup) echo "planveyor_docs_lookup <canon|followups|plans> [docs_retrieve flags] \"FTS query\"" ;;
    planveyor_docs_get) echo "planveyor_docs_get <path|path:line> [--from-line N --lines M | --full] [--max-bytes N] [--max-lines N] [--format text|md|json] [--no-context] [--read-log PATH|--no-read-log]" ;;
    planveyor_docs_multi_get) echo "planveyor_docs_multi_get [glob|path|@filelist|- ...] [--format md|json] [--max-bytes N] [--max-bytes-per-doc N] [--max-files N] [--no-context] [--read-log PATH|--no-read-log]" ;;
    planveyor_followups_lint) echo "planveyor_followups_lint [docs/followups/<file>.md ...] [--project-root PATH] [--format text|json]" ;;
    planveyor_followups_reconcile) echo "planveyor_followups_reconcile [--project-root PATH] [--report|--apply] [--write-to DIR] [--format text|json]" ;;
    planveyor_followups_apply) echo "planveyor_followups_apply --frozen-manifest <cycle.json> [--apply] [--project-root PATH]" ;;
    planveyor_followups_promote) echo "planveyor_followups_promote --project-root PATH --file docs/followups/<file>.md --line N --plan-path docs/plans/<...>.md [--dry-run|--apply] | --prepare-v2/--finalize-v2 --item-id <stable-id> --plan-path docs/plans/<...>.md [--frozen-manifest <cycle.json> --commit-oid <Commit-A>]" ;;
    planveyor_process_improvements_promote) echo "planveyor_process_improvements_promote --project-root PATH --backlog docs/process_improvements/<file>.md --entry PI-001 --execution-kind <kind> --execution-ref <ref> --promoted-at '<timestamp>' [--report|--apply] [--format text|json]" ;;
    planveyor_process_improvements_reconcile) echo "planveyor_process_improvements_reconcile [--project-root PATH] [--backlog docs/process_improvements/<file>.md] [--report|--apply --handled-at '<timestamp>'] [--format text|json]" ;;
    planveyor_followups_query) echo "planveyor_followups_query <ready-candidates|needs-owner-triage|broken-plan-links|stale-promoted|cleanup-ready|cleanup-receipt> [--source-ref <exact> --item-id <stable-id>] [--project-root PATH] [--format text|json]" ;;
    planveyor_followups_triage) echo "planveyor_followups_triage [--all] | [--file docs/followups/<inbox>.md] | [--range BASE..HEAD|BASE HEAD] [--dry-run|--apply]" ;;
    planveyor_code_draft_stub_from_plan) echo "planveyor_code_draft_stub_from_plan [PLAN_PATH] [--role Planner|Coder|Architect]" ;;



    planveyor_manager_collab) echo "planveyor_manager_collab" ;;
    planveyor_manager_collab_tui) echo "planveyor_manager_collab_tui [--q] [--no-alt-screen] [--merge [--range auto|<MERGE_SHA>|<BASE..HEAD>]]" ;;
    planveyor_manager_collab_cmd) echo "planveyor_manager_collab_cmd <status|plan_set|analysis [PLAN_PATH]|decomposition [PLAN_PATH]|run [Q|PLAN_PATH [--followups-capture-cycle-id UUIDv4]]|merge_status|merge_run|merge_apply|close|reset> [ARGS...]" ;;
    planveyor_merge_collab_tui) echo "planveyor_merge_collab_tui [--no-alt-screen] [--range auto|<MERGE_SHA>|<BASE..HEAD>]" ;;
    planveyor_merge_collab_cmd) echo "planveyor_merge_collab_cmd [--range auto|<MERGE_SHA>|<BASE..HEAD>]" ;;
    planveyor_merge_apply_collab_tui) echo "planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" ;;
    planveyor_merge_apply_collab_cmd) echo "planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]" ;;
    planveyor_manager_custom_pipeline) echo "planveyor_manager_custom_pipeline" ;;
    planveyor_manager_custom_pipeline_tui) echo "planveyor_manager_custom_pipeline_tui [--no-alt-screen]" ;;
    planveyor_manager_custom_pipeline_cmd) echo "planveyor_manager_custom_pipeline_cmd <status|plan_set|run [PLAN_PATH|Q]|run_q> [ARGS...]" ;;
    planveyor_manager_resume) echo "planveyor_manager_resume" ;;

    planveyor_arch|planveyor_planner|planveyor_coder|planveyor_reviewer|planveyor_reviewer_code_risk|planveyor_reviewer_code_contracts|planveyor_manager)
      echo "${cmd}"
      ;;
    planveyor_arch_init|planveyor_planner_init|planveyor_coder_init|planveyor_reviewer_init|planveyor_reviewer_code_risk_init|planveyor_reviewer_code_contracts_init|planveyor_manager_init)
      echo "${cmd}"
      ;;
    planveyor_arch_resume|planveyor_planner_resume|planveyor_coder_resume|planveyor_reviewer_resume|planveyor_reviewer_code_risk_resume|planveyor_reviewer_code_contracts_resume|planveyor_manager_resume)
      echo "${cmd}"
      ;;

    *) echo "${cmd} [args...]" ;;
  esac
}

_planveyor_help_range_example() {
  # Prints the saved review range as BASE..HEAD for catalog examples.  Inside
  # a guarded owner (planveyor_help) the rows read the range carriers under
  # the owner's already validated root: the guarded range readers would
  # revalidate the authority context four times for every example row.  A
  # direct call without an owner context keeps using those readers.
  local base="" head=""
  if _planveyor_authority_context_carrier_present && _planveyor_authority_parent_context_shape; then
    base="$(_planveyor_read "$PLANVEYOR_CTX_ROOT/.planveyor.range.base" 2>/dev/null || true)"
    head="$(_planveyor_read "$PLANVEYOR_CTX_ROOT/.planveyor.range.head" 2>/dev/null || true)"
  else
    base="$(planveyor_range_base 2>/dev/null || true)"
    head="$(planveyor_range_head 2>/dev/null || true)"
  fi
  print -r -- "${base:-BASE}..${head:-HEAD}"
}

_planveyor_help_cmd_example() {
  local cmd="${1:-}"
  [[ -n "${cmd//[[:space:]]/}" ]] || { echo " "; return 0; }
  case "$cmd" in
    planveyor_consumer_init) echo "./bin/planveyor planveyor_consumer_init /absolute/new/sibling --source-commit <full-40-hex> --author-name \"Your Name\" --author-email you@example.invalid" ;;
    planveyor_consumer_doctor) echo "./bin/planveyor --project /absolute/sibling planveyor_consumer_doctor" ;;
    planveyor_plan_lint) echo "./bin/planveyor --project /absolute/sibling planveyor_plan_lint docs/plans/<plan>.md" ;;
    planveyor_runtime_py) echo "./bin/planveyor --project /absolute/sibling planveyor_runtime_py plan_lint.py docs/plans/<plan>.md" ;;
    planveyor_contract_upgrade) echo "./bin/planveyor --project /absolute/sibling planveyor_contract_upgrade --source-commit <full-40-hex>" ;;
    planveyor_show) echo "planveyor_show --all" ;;
    planveyor_help) echo "planveyor_help --manual" ;;
    planveyor_show_manual) echo "planveyor_show_manual" ;;
    planveyor_show_collab) echo "planveyor_show_collab --wide" ;;
    planveyor_show_process) echo "planveyor_show_process" ;;

    planveyor_plan_set) echo "planveyor_plan_set docs/plans/YYMMDD_HHMM_topic.md" ;;
    planveyor_q_set) echo "planveyor_q_set --status \"ready for coder\" \"in progress\" --for-manager-mode manager-collab" ;;
    planveyor_q_append) echo "planveyor_q_append docs/plans/YYMMDD_HHMM_new_tail.md --for-manager-mode manager-collab" ;;
    planveyor_q_show) echo "planveyor_q_show" ;;
    planveyor_q_history) echo "planveyor_q_history --limit 20" ;;
    planveyor_planqueue_metrics) echo "planveyor_planqueue_metrics" ;;
    planveyor_planqueue_metrics_json) echo "planveyor_planqueue_metrics_json" ;;
    planveyor_planning_wave_readback) echo "planveyor_planning_wave_readback" ;;
    planveyor_planning_wave_readback_json) echo "planveyor_planning_wave_readback_json" ;;
    planveyor_wave_telemetry_report) echo "planveyor_wave_telemetry_report" ;;
    planveyor_wave_telemetry_report_json) echo "planveyor_wave_telemetry_report_json" ;;
    planveyor_docs_closeout) echo "planveyor_docs_closeout docs/plans/YYMMDD_HHMM_topic.md --json" ;;
    planveyor_analysis_init) echo "planveyor_analysis_init docs/plans/YYMMDD_HHMM_analysis_wave.md" ;;
    planveyor_q_small_slice) echo "planveyor_q_small_slice docs/plans/YYMMDD_HHMM_topic.md" ;;
    planveyor_q_next_json) echo "planveyor_q_next_json --manager-mode manager-collab" ;;
    planveyor_q_small_slice_json) echo "planveyor_q_small_slice_json docs/plans/YYMMDD_HHMM_topic.md" ;;
    planveyor_q_advance_json) echo "planveyor_q_advance_json Done --manager-mode manager-collab" ;;
    planveyor_q_closeout_json) echo "planveyor_q_closeout_json --manager-mode manager-collab" ;;
    planveyor_q_stop_json) echo "planveyor_q_stop_json docs_closeout_blocked --source-plan docs/plans/YYMMDD_HHMM_topic.md" ;;
    planveyor_q_planpath_override_json) echo "planveyor_q_planpath_override_json docs/plans/YYMMDD_HHMM_topic.md queue_activation" ;;
    planveyor_q_history_json) echo "planveyor_q_history_json --limit 20" ;;
    planveyor_q_final_report) echo "planveyor_q_final_report --format json" ;;
    planveyor_q_clear) echo "planveyor_q_clear" ;;
    planveyor_q_recover) echo "planveyor_q_recover --json" ;;
    planveyor_decomposition_init) echo "planveyor_decomposition_init  # auto-seed if PLAN_PATH not provided" ;;
    planveyor_decomposition_seed_promote) echo "planveyor_decomposition_seed_promote docs/plans/YYMMDD_HHMM_meaningful_topic.md" ;;
    planveyor_decomposition_collab) echo "planveyor_decomposition_collab docs/plans/YYMMDD_HHMM_umbrella_topic.md" ;;
    planveyor_decomposition_collab_tui) echo "planveyor_decomposition_collab_tui docs/plans/YYMMDD_HHMM_umbrella_topic.md --no-alt-screen" ;;
    planveyor_plan_bundle) echo "planveyor_plan_bundle --closeout-json docs/plans/YYMMDD_HHMM_topic.md" ;;
    planveyor_plan_closeout_preflight) echo "planveyor_plan_closeout_preflight docs/plans/YYMMDD_HHMM_topic.md" ;;
    planveyor_plan_list) echo "planveyor_plan_list upgrade" ;;
    planveyor_plan_list_status) echo "planveyor_plan_list_status \"ready for coder\"" ;;

    planveyor_session) echo "planveyor_session planner" ;;
    planveyor_session_set) echo "planveyor_session_set planner <SID> runner=codex" ;;
    planveyor_rollout_packet_create) echo "planveyor_rollout_packet_create planveyor helper_boundary --source-plan docs/plans/260329_0028_process_rollout_packet_helper_scaffold_without_cross_repo_writes.md --dry-run" ;;
    planveyor_rollout_packet_show) echo "planveyor_rollout_packet_show docs/rollout_packets/YYMMDD_HHMM_planveyor_helper_boundary.md" ;;
    planveyor_rollout_packet_import_instructions) echo "planveyor_rollout_packet_import_instructions docs/rollout_packets/YYMMDD_HHMM_planveyor_helper_boundary.md --print-target-plan-seed" ;;
    planveyor_rollout_packet_lint) echo "planveyor_rollout_packet_lint --all --json" ;;
    planveyor_rollout_packet_ack) echo "planveyor_rollout_packet_ack --packet docs/rollout_packets/YYMMDD_HHMM_planveyor_helper_boundary.md --status imported --target-plan docs/plans/YYMMDD_HHMM_process_rollout_packet_inbox_adoption.md" ;;
    planveyor_rollout_packet_query) echo "planveyor_rollout_packet_query --status open --json" ;;
    planveyor_rollout_packet_reconcile) echo "planveyor_rollout_packet_reconcile --report --target-root \${PLANVEYOR_TARGET_ROOT:-\$HOME/planveyor} --target-repo planveyor --json" ;;
    planveyor_rollout_packet_outcome_set) echo "planveyor_rollout_packet_outcome_set --target-plan docs/plans/YYMMDD_HHMM_process_rollout_packet_inbox_adoption.md --packet-id YYMMDD_HHMM_planveyor_helper_boundary --packet-path docs/rollout_packets/YYMMDD_HHMM_planveyor_helper_boundary.md --outcome adopted" ;;
    planveyor_shared_docs_mirror_drift) echo "planveyor_shared_docs_mirror_drift --target-root \${PLANVEYOR_TARGET_ROOT:-\$HOME/planveyor} --json" ;;
    planveyor_mirror_strict_gate) echo "planveyor_mirror_strict_gate --target-root \${PLANVEYOR_TARGET_ROOT:-\$HOME/planveyor} --json" ;;
    planveyor_upstream_request_show) echo "planveyor_upstream_request_show docs/upstream_packets/YYMMDD_HHMM_planveyor_owner_runbook.md" ;;
    planveyor_upstream_request_import) echo "planveyor_upstream_request_import --packet docs/upstream_packets/YYMMDD_HHMM_planveyor_owner_runbook.md" ;;
    planveyor_upstream_request_ack) echo "planveyor_upstream_request_ack --packet docs/upstream_packets/YYMMDD_HHMM_planveyor_owner_runbook.md --source-decision-ref docs/plans/YYMMDD_HHMM_process_owner_runbook_gap.md --source-execution-ref docs/plans/YYMMDD_HHMM_process_owner_runbook_gap.md#Evidence" ;;
    planveyor_upstream_request_query) echo "planveyor_upstream_request_query --status open --json" ;;
    planveyor_bare_entrypoints_doctor) echo "planveyor_bare_entrypoints_doctor --bin-dir \"$HOME/.local/bin\"" ;;
    planveyor_ai_gate) echo "planveyor_ai_gate --range HEAD~1..HEAD --policy docs/tools/ai_gate_policy.example.json" ;;
    planveyor_ai_gate_smoke) echo "planveyor_ai_gate_smoke --receipt-path .tmp/planveyor_ai_gate_smoke.json" ;;

    planveyor_runner_set) echo "planveyor_runner_set planner codex" ;;
    planveyor_runner_clear) echo "planveyor_runner_clear reviewer" ;;
    planveyor_runner_matrix) echo "planveyor_runner_matrix" ;;
    planveyor_role_runner_preflight) echo "planveyor_role_runner_preflight planner --json" ;;
    planveyor_custom_role_step) echo "planveyor_custom_role_step coder --plan docs/plans/YYMMDD_HHMM_process_example.md --json" ;;
    planveyor_role_run) echo "planveyor_role_run reviewer_code_risk --json" ;;
    planveyor_role_run_probe) echo "planveyor_role_run_probe run --kind retention --target-plan docs/plans/YYMMDD_HHMM_process_example.md --scenario terminal_recovery --json" ;;
    planveyor_role_run_receipt_check) echo "planveyor_role_run_receipt_check .planveyor.role_runs/<run_id>.json --json" ;;
    planveyor_profile) echo "planveyor_profile planner" ;;
    planveyor_profile_set) echo "planveyor_profile_set planner sol-ultra" ;;
    planveyor_profile_clear) echo "planveyor_profile_clear planner censor" ;;

    planveyor_manager_collab_cmd) echo "planveyor_manager_collab_cmd decomposition docs/plans/YYMMDD_HHMM_decomposition.md" ;;
    planveyor_manager_collab) echo "planveyor_manager_collab" ;;
    planveyor_manager_collab_tui) echo "planveyor_manager_collab_tui" ;;
    planveyor_merge_collab_tui) echo "planveyor_merge_collab_tui --range auto" ;;
    planveyor_merge_collab_cmd) echo "planveyor_merge_collab_cmd --range <MERGE_SHA>" ;;
    planveyor_merge_apply_collab_tui) echo "planveyor_merge_apply_collab_tui --from feature/my-branch --to main" ;;
    planveyor_merge_apply_collab_cmd) echo "planveyor_merge_apply_collab_cmd --from feature/my-branch --to main --then-review 1" ;;
    planveyor_manager_custom_pipeline) echo "planveyor_manager_custom_pipeline" ;;
    planveyor_manager_custom_pipeline_tui) echo "planveyor_manager_custom_pipeline_tui" ;;
    planveyor_manager_custom_pipeline_cmd) echo "planveyor_manager_custom_pipeline_cmd run Q" ;;
    planveyor_merge_tracker_next_step) echo "planveyor_merge_tracker_next_step" ;;
    planveyor_merge_tracker_tick) echo "planveyor_merge_tracker_tick step:review_range" ;;
    planveyor_merge_range_stats_json) echo "planveyor_merge_range_stats_json \"$(_planveyor_help_range_example)\"" ;;
    planveyor_post_merge_packetization_gate) echo "planveyor_post_merge_packetization_gate --range \"$(_planveyor_help_range_example)\"  # legacy --create-drafts is zero-write/red; use recover wrapper" ;;
    planveyor_post_merge_packetization_gate_recover) echo "planveyor_post_merge_packetization_gate_recover --range \"$(_planveyor_help_range_example)\" --packet docs/rollout_packets/<packet>.md --stage-packets  # optional: --source-plan docs/plans/<provenance-plan>.md" ;;
    planveyor_post_merge_receipt_skeleton) echo "planveyor_post_merge_receipt_skeleton --help" ;;
    planveyor_post_merge_receipt_preflight) echo "planveyor_post_merge_receipt_preflight plan_harvest --path docs/reviews/<stamp>_plan_harvest_range_<base7>_<head7>.md --format json" ;;
    planveyor_post_merge_docs_finalize_tick) echo "planveyor_post_merge_docs_finalize_tick --role Architect --range \"$(_planveyor_help_range_example)\" --path docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md" ;;
    planveyor_post_merge_operational_receipt) echo "planveyor_post_merge_operational_receipt --help  # requires --archive-snapshot-json with backend/manifest/artifact/checksum/restore/readback fields" ;;
    planveyor_post_merge_docs_hygiene_suggest_gate) echo "planveyor_post_merge_docs_hygiene_suggest_gate" ;;
    planveyor_merge_bundle_report) echo "planveyor_merge_bundle_report --format json  # packetization_gate.active_packetization_report + superseded_packetization_reports" ;;
    planveyor_post_merge_ready_to_push_closeout) echo "planveyor_post_merge_ready_to_push_closeout --format json  # why_blocked + staging_command/pathspec_file; pending_owner_gate=git push" ;;
    planveyor_merge_range_verdict_digest) echo "planveyor_merge_range_verdict_digest --format json  # final owner digest; pending_owner_gate=git push; read-only" ;;
    planveyor_review_risk_packet) echo "planveyor_review_risk_packet --range \"$(_planveyor_help_range_example)\" --review-artifact docs/code_reviews/<...>.md --post-merge-audit docs/reviews/<...>_post_merge_audit_range_<base7>_<head7>.md --operational-receipt docs/reviews/<...>_post_merge_operational_receipt_range_<base7>_<head7>.md --ready-to-push-closeout docs/reviews/<...>_ready_to_push_closeout_range_<base7>_<head7>.md --packetization-report docs/reviews/<...>_packetization_gate_range_<base7>_<head7>.md --json" ;;
    planveyor_review_range_init) echo "planveyor_review_range_init --force-new 1" ;;
    planveyor_review_target_snapshot) echo "planveyor_review_target_snapshot docs/plans/YYMMDD_HHMM_topic.md --current-bundle" ;;
    planveyor_followups_lint) echo "planveyor_followups_lint --project-root \${PLANVEYOR_TARGET_ROOT:-\$HOME/planveyor}" ;;
    planveyor_followups_reconcile) echo "planveyor_followups_reconcile --project-root \${PLANVEYOR_TARGET_ROOT:-\$HOME/planveyor} --report" ;;
    planveyor_followups_apply) echo "planveyor_followups_apply --frozen-manifest .tmp/followups_capture/<plan>/v2_frozen_manifest.json --apply" ;;
    planveyor_followups_promote) echo "planveyor_followups_promote --project-root \${PLANVEYOR_TARGET_ROOT:-\$HOME/planveyor} --file docs/followups/process_followups_master.md --prepare-v2 --item-id example-001 --plan-path docs/plans/260327_1900_process_example_followup.md --dry-run" ;;
    planveyor_process_improvements_promote) echo "planveyor_process_improvements_promote --project-root \${PLANVEYOR_ROOT:-\$HOME/planveyor} --backlog docs/process_improvements/source__process_improvements_backlog.md --entry PI-001 --execution-kind plan --execution-ref docs/plans/260430_1200_example.md --promoted-at '2026-04-30 12:00 +0000' --report" ;;
    planveyor_process_improvements_reconcile) echo "planveyor_process_improvements_reconcile --project-root \${PLANVEYOR_ROOT:-\$HOME/planveyor} --report" ;;
    planveyor_followups_query) echo "planveyor_followups_query ready-candidates --source-ref docs/plans/example.md --item-id example-001 --project-root \${PLANVEYOR_TARGET_ROOT:-\$HOME/planveyor}" ;;
    planveyor_followups_triage) echo "planveyor_followups_triage --all --dry-run | planveyor_followups_triage --range BASE..HEAD --dry-run" ;;


    *) echo "${cmd}" ;;
  esac
}

_planveyor_help_cmd_summary() {
  local cmd="${1:-}"
  [[ -n "${cmd//[[:space:]]/}" ]] || { echo " "; return 0; }

  case "$cmd" in
    planveyor_show) echo "dashboard: show blocks (manual/collab/process)" ;;
    planveyor_help) echo "cookbook: this help" ;;
    planveyor_show_manual) echo "show manual block (context + sessions + commands)" ;;
    planveyor_show_collab) echo "show collab block (manager + agents)" ;;
    planveyor_show_process) echo "show process tracks block (Architect)" ;;

    planveyor_plan_set) echo "set active plan path (.planveyor.planpath)" ;;
    planveyor_q_set) echo "materialize repo-local Manager queue from explicit plans/status/umbrella import" ;;
    planveyor_q_append) echo "append explicit repo-local plans to initialized Manager queue tail without rebuilding state" ;;
    planveyor_q_show) echo "show repo-local Manager queue state with scoped current/historical stop diagnostics" ;;
    planveyor_q_history) echo 'show read-only `.planveyor.planqueue.log` history; does not replace `planveyor_q_show`' ;;
    planveyor_planqueue_metrics) echo 'generate read-only planning-contour health metrics from `.planveyor.planqueue.{log,json}`' ;;
    planveyor_planqueue_metrics_json) echo 'print planning-contour queue health metrics JSON' ;;
    planveyor_planning_wave_readback) echo 'show read-only planning-wave buckets, preview, provenance and accepted-route history' ;;
    planveyor_planning_wave_readback_json) echo 'print planning-wave readback JSON' ;;
    planveyor_wave_telemetry_report) echo 'show read-only per-wave telemetry and retrieval-corpus report' ;;
    planveyor_wave_telemetry_report_json) echo 'print per-wave telemetry report JSON' ;;
    planveyor_docs_closeout) echo "show manager docs-closeout state/context and final_docs_commit for one plan" ;;
    planveyor_analysis_init) echo "prepare existing analysis-wave plan and print oracle-derived readback" ;;
    planveyor_q_small_slice) echo "classify whether a plan qualifies for reduced same-session censors" ;;
    planveyor_q_next_json) echo "activate/read next queue item as JSON" ;;
    planveyor_q_small_slice_json) echo "classify reduced-censor eligibility as JSON" ;;
    planveyor_q_advance_json) echo "advance queue after terminal child status as JSON" ;;
    planveyor_q_closeout_json) echo "materialize queue closeout handoff as JSON" ;;
    planveyor_q_stop_json) echo "record non-terminal queue stop as JSON" ;;
    planveyor_q_planpath_override_json) echo "record queue-driven planpath change as JSON" ;;
    planveyor_q_history_json) echo 'show read-only `.planveyor.planqueue.log` history as JSON' ;;
    planveyor_q_final_report) echo "show read-only queue-level finalizer report after queue_complete=true" ;;
    planveyor_q_clear) echo "clear repo-local Manager queue state (log stays append-only)" ;;
    planveyor_q_recover) echo "recover an interrupted queue transaction that a recovery_required payload names" ;;
    planveyor_decomposition_init) echo "bootstrap decomposition seed/scaffold + ensure Manager session" ;;
    planveyor_decomposition_seed_promote) echo "rename auto-seed decomposition plan after Architect clarifies topic" ;;
    planveyor_decomposition_collab) echo "bootstrap and run decomposition wave via Manager collab (one-shot)" ;;
    planveyor_decomposition_collab_tui) echo "bootstrap and run decomposition wave via Manager collab TUI" ;;
    planveyor_plan_bundle) echo "resolve/print/stage/guard/classify exact plan bundle by git root" ;;
    planveyor_plan_closeout_preflight) echo "normalize semantic/materialization closeout readiness from exact bundle JSON" ;;
    planveyor_plan_list) echo "list plans (non-Done/non-Superseded)" ;;
    planveyor_plan_list_status) echo "list plans filtered by status substring" ;;
    planveyor_range_set) echo "save BASE/HEAD[/MERGE] review range" ;;
    planveyor_range_set_merge) echo "derive BASE from MERGE^1 and save range" ;;
    planveyor_status_line) echo "print numbered **Status:** line from plan" ;;
    planveyor_merge_init) echo "alias: initialize merge tracker" ;;
    planveyor_merge_tracker_init) echo "create merge tracker for current range" ;;
    planveyor_merge_tracker_ensure) echo "auto-range + init tracker (best-effort)" ;;
    planveyor_merge_tracker_next_step) echo "print first unchecked merge step key" ;;
    planveyor_merge_tracker_tick) echo "tick merge tracker step via oracle" ;;
    planveyor_merge_tracker_show) echo "show merge tracker header/checklist" ;;
    planveyor_merge_range_stats_json) echo "emit helper-backed merge range stats JSON" ;;
    planveyor_post_merge_packetization_gate) echo "generate active packetization report/readback for shared canon range deltas" ;;
    planveyor_post_merge_packetization_gate_recover) echo "recover explicit current rollout packets by full-OID range identity with optional packet-local provenance and exact staging" ;;
    planveyor_post_merge_receipt_skeleton) echo "emit parser-valid post-merge receipt skeleton frames" ;;
    planveyor_post_merge_receipt_preflight) echo "run step-local post-merge receipt schema preflight before tracker tick/advance" ;;
    planveyor_post_merge_docs_finalize_tick) echo "run strict Architect docs-finalize preflight and then tick only step:docs_finalize" ;;
    planveyor_post_merge_operational_receipt) echo "write schema-backed post-merge operational receipt" ;;
    planveyor_post_merge_docs_hygiene_suggest_gate) echo "run report-only docs hygiene suggest and tick its merge step after parseable success" ;;
    planveyor_merge_bundle_report) echo "report final merge bundle artifacts/git status plus active/superseded packetization readback (read-only)" ;;
    planveyor_post_merge_ready_to_push_closeout) echo "fail-closed local commit/tick for ready_to_push with terminal companion proof, why_blocked, safe staging command/pathspec diagnostics (never push)" ;;
    planveyor_merge_range_verdict_digest) echo "read-only final owner digest over merge_bundle_report, risk_packet, and ready_to_push proof" ;;
    planveyor_verify) echo "run registry-driven read-only integrity checks; default is fast, --full adds one canonical unittest discovery" ;;
    planveyor_merge_next) echo "suggest next post-merge step by tracker/artifacts" ;;
    planveyor_review_risk_packet) echo "generate compact range review risk_packet from exact truth hosts" ;;
    planveyor_review_range_init) echo "create review-only plan for range (optional docs)" ;;
    planveyor_review_range_start) echo "start reviewer session for current/specified range" ;;
    planveyor_review_target_snapshot) echo "emit stdout-only current-bundle target_snapshot JSON for review artifacts" ;;

    planveyor_session) echo "read stored session id (.planveyor.session.<key>)" ;;
    planveyor_session_set) echo "store session id for key (.planveyor.session.<key>)" ;;
    planveyor_rollout_packet_create) echo "create a source-local rollout packet skeleton (no sibling-repo writes)" ;;
    planveyor_rollout_packet_show) echo "show a source-local rollout packet summary or raw content" ;;
    planveyor_rollout_packet_import_instructions) echo "print target-local import instructions from a source-local packet" ;;
    planveyor_rollout_packet_lint) echo "run read-only grammar lint for source-local rollout packets" ;;
    planveyor_rollout_packet_ack) echo "record source-side packet acknowledgement/status transition" ;;
    planveyor_rollout_packet_query) echo "list source-local rollout packets with receipt/outcome readback fields" ;;
    planveyor_rollout_packet_reconcile) echo "report stale or inconsistent source-local rollout packets and target outcomes" ;;
    planveyor_rollout_packet_outcome_set) echo "record one canonical target-local outcome through the structured rollout packet carrier" ;;
    planveyor_shared_docs_mirror_drift) echo "read-only exact shared-docs mirror drift guard" ;;
    planveyor_mirror_strict_gate) echo "fail-closed shared-docs mirror drift gate" ;;
    planveyor_upstream_request_show) echo "show a source-local upstream request packet summary or raw content" ;;
    planveyor_upstream_request_import) echo "import an upstream request into source-local process improvements" ;;
    planveyor_upstream_request_ack) echo "record source-side decision/execution refs on an imported upstream request" ;;
    planveyor_upstream_request_query) echo "list source-local upstream request packets by explicit fields" ;;
    planveyor_bare_entrypoints_doctor) echo "inspect bare PATH shims and fresh shell visibility" ;;
    planveyor_ai_gate) echo "run pre-merge AI gate against current repo" ;;
    planveyor_ai_gate_smoke) echo "run deterministic synthetic AI gate smoke into explicit receipt path" ;;

    planveyor_runner) echo "get default runner for role (worktree-local)" ;;
    planveyor_runner_set) echo "set default runner for role (worktree-local)" ;;
    planveyor_runner_clear) echo "clear runner override for role (worktree-local)" ;;
    planveyor_runner_matrix) echo "show runner selection matrix" ;;
    planveyor_role_runner_preflight) echo "fail-fast role runner execution-readiness readback" ;;
    planveyor_custom_role_step) echo "run one exact-plan custom Manager role step and validate its execution receipt" ;;
    planveyor_role_run) echo "run one role wrapper and write a compact execution receipt" ;;
    planveyor_role_run_probe) echo "run, inspect, and recover exact-ID role-run probes in the isolated managed namespace" ;;
    planveyor_role_run_receipt_check) echo "fail-closed readback check for role execution receipts" ;;
    planveyor_profile) echo "show effective Codex profile for role/mode" ;;
    planveyor_profile_set) echo "set Codex profile override for role/mode" ;;
    planveyor_profile_clear) echo "clear Codex profile override for role/mode" ;;

    planveyor_owner_answers_set) echo "stash one-shot Owner answers for next run" ;;
    planveyor_clear_owner_answers) echo "clear pending Owner answers" ;;

    planveyor_doc_lint) echo "run exact canonical doc lint (project docs)" ;;
    planveyor_docs_hygiene_list) echo "optional docs inventory helper (not a merge gate)" ;;
    planveyor_docs_hygiene_suggest) echo "report-only docs cleanup handoff / suggest optional git-rm candidates" ;;
    planveyor_docs_hygiene_archive) echo "archive cleanup candidates to central docs archive" ;;
    planveyor_docs_archive_snapshot_info) echo "print central docs archive snapshot facts" ;;
    planveyor_docs_archive_snapshot_export) echo "export portable docs archive snapshot artifact/manifest" ;;
    planveyor_docs_archive_snapshot_validate) echo "validate portable docs archive snapshot manifest/artifact" ;;
    planveyor_docs_archive_snapshot_restore) echo "restore portable docs archive snapshot into local SQLite FTS DB" ;;
    planveyor_docs_retrieve_log) echo "print active docs retrieval query log path (or disabled)" ;;
    planveyor_docs_retrieve_outcome_log) echo "print active docs retrieval outcome log path (or disabled)" ;;
    planveyor_docs_retrieve_read_log) echo "print active docs read/open log path (or disabled)" ;;
    planveyor_docs_retrieve_metrics) echo "summarize query, outcome, and read/open retrieval logs" ;;
    planveyor_docs_lookup) echo "one-shot docs retrieval with instrumented read/open and a retrieval receipt skeleton" ;;
    planveyor_docs_get) echo "read one docs file with caps and path-only read/open telemetry" ;;
    planveyor_docs_multi_get) echo "batch-read docs files with caps and path-only read/open telemetry" ;;
    planveyor_followups_lint) echo "lint backlog files and promoted-pointer semantics" ;;
    planveyor_followups_reconcile) echo "report/apply safe promoted->handled followups sync" ;;
    planveyor_followups_apply) echo "apply only a Manager-frozen V2 followups union through the serial CAS writer" ;;
    planveyor_followups_promote) echo "prepare/finalize V2 promotion with Commit-A proof, or use the legacy line wrapper" ;;
    planveyor_process_improvements_promote) echo "promote one process-improvement row with explicit execution pointers" ;;
    planveyor_process_improvements_reconcile) echo "report/apply safe process-improvement promoted->handled sync" ;;
    planveyor_followups_query) echo "structured operational views over followups backlog" ;;
    planveyor_followups_triage) echo "triage/import inbox followups into cluster masters" ;;
    planveyor_code_draft_stub_from_plan) echo "create code draft stub for a plan" ;;




    planveyor_manager_collab) echo "run Manager collab pipeline (one-shot)" ;;
    planveyor_manager_collab_tui) echo "run Manager collab in TUI (single-plan, queue via --q, or merge-run via --merge)" ;;
    planveyor_manager_collab_cmd) echo "send MANAGER_CMD to Manager; explicit run PLAN_PATH --followups-capture-cycle-id UUIDv4 continues only before the first followups dispatch" ;;
    planveyor_merge_collab_tui) echo "run merge-mode collab pipeline in TUI" ;;
    planveyor_merge_collab_cmd) echo "run merge-mode collab pipeline (one-shot)" ;;
    planveyor_merge_apply_collab_tui) echo "run merge+conflicts+commit(no-push) and then merge review in TUI" ;;
    planveyor_merge_apply_collab_cmd) echo "run merge+conflicts+commit(no-push) one-shot (optional then-review)" ;;
    planveyor_manager_custom_pipeline) echo "run optional custom manager pipeline (one-shot)" ;;
    planveyor_manager_custom_pipeline_tui) echo "run optional custom manager pipeline in TUI" ;;
    planveyor_manager_custom_pipeline_cmd) echo "send MANAGER_CMD to custom manager pipeline (one-shot; 'run Q' = queue mode)" ;;
    planveyor_manager_resume) echo "resume Manager session (manual)" ;;

    planveyor_arch|planveyor_planner|planveyor_coder|planveyor_reviewer|planveyor_reviewer_code_risk|planveyor_reviewer_code_contracts|planveyor_manager)
      echo "run role step (status-driven; uses current plan + session id)"
      ;;
    planveyor_arch_init|planveyor_planner_init|planveyor_coder_init|planveyor_reviewer_init|planveyor_reviewer_code_risk_init|planveyor_reviewer_code_contracts_init|planveyor_manager_init)
      echo "init role session (create new sid / bootstrap)"
      ;;
    planveyor_arch_resume|planveyor_planner_resume|planveyor_coder_resume|planveyor_reviewer_resume|planveyor_reviewer_code_risk_resume|planveyor_reviewer_code_contracts_resume|planveyor_manager_resume)
      echo "resume role session (manual resume)"
      ;;

    *) echo "see function in scripts/planveyor.zsh" ;;
  esac
}

_planveyor_help_print_catalog_table() {
  # Prints a command catalog as a table: cmd | usage | example | summary.
  local title="${1:-}"
  shift || true
  [[ -n "${title//[[:space:]]/}" ]] || title="Commands"

  local tab=$'\t'
  local -a rows
  rows=()
  rows+=("cmd${tab}usage${tab}example${tab}summary")

  local cmd
  for cmd in "$@"; do
    [[ -n "${cmd//[[:space:]]/}" ]] || continue
    local usage="" ex="" summary=""
    usage="$(_planveyor_help_cmd_usage "$cmd")"
    ex="$(_planveyor_help_cmd_example "$cmd")"
    summary="$(_planveyor_help_cmd_summary "$cmd")"
    rows+=("${cmd}${tab}$(_planveyor_table_cell "$usage")${tab}$(_planveyor_table_cell "$ex")${tab}$(_planveyor_table_cell "$summary")")
  done

  echo "#### ${title}"
  if command -v column >/dev/null 2>&1; then
    printf '%s\n' "${rows[@]}" | column -t -s $'\t'
  else
    printf '%s\n' "${rows[@]}"
  fi
}

_planveyor_manual_sessions_table() {
  # Usage: _planveyor_manual_sessions_table <wide:0|1> [project_root]
  # A guarded owner passes the root it has already bound.  Rows read their
  # carriers under that root: the guarded session/runner readers would each
  # revalidate the authority context again for every row.
  local wide="${1:-0}"
  local root="${2:-}"
  if [[ -z "${root//[[:space:]]/}" ]]; then
    root="$(_planveyor_project_root)" || return $?
  fi
  local -a role_rows
  role_rows=()
  local tab=$'\t'
  if (( wide )); then
    role_rows+=("role${tab}runner${tab}sid${tab}set_at${tab}session_file")
  else
    role_rows+=("role${tab}runner${tab}sid${tab}set")
  fi

  local role
  for role in architect planner coder reviewer reviewer_code_risk reviewer_code_contracts manager; do
    local sid="" runner="" set_at=""
    sid="$(_planveyor_read "$root/.planveyor.session.${role}" 2>/dev/null || true)"
    case "$role" in
      reviewer_code_risk|reviewer_code_contracts) runner="$(_planveyor_runner_at_root "$root" reviewer 2>/dev/null || true)" ;;
      *) runner="$(_planveyor_runner_at_root "$root" "$role" 2>/dev/null || true)" ;;
    esac
    [[ "$sid" == "<SESSION_ID>" ]] && sid=""

    local log_path="$root/.planveyor.session.${role}.log"
    if [[ -f "$log_path" ]]; then
      local log_last=""
      log_last="$(_planveyor_last_line "$log_path" 2>/dev/null || true)"
      if [[ -n "${log_last//[[:space:]]/}" && "$log_last" == *$'\t'* ]]; then
        set_at="${log_last%%$'\t'*}"
        set_at="${set_at#"${set_at%%[![:space:]]*}"}"
      fi
    fi
    set_at="$(_planveyor_dt_short "$set_at")"

    if (( wide )); then
      role_rows+=(
        "${role}${tab}$(_planveyor_table_cell "$runner")${tab}$(_planveyor_table_cell "$sid")${tab}$(_planveyor_table_cell "$set_at")${tab}$(_planveyor_table_cell ".planveyor.session.${role}")"
      )
    else
      local sid_disp="$sid"
      if [[ -n "${sid_disp//[[:space:]]/}" ]]; then
        if _planveyor_is_uuid "$sid_disp"; then
          sid_disp="${sid_disp%%-*}"
        else
          sid_disp="${sid_disp[1,8]}"
        fi
      fi
      role_rows+=(
        "${role}${tab}$(_planveyor_table_cell "$runner")${tab}$(_planveyor_table_cell "$sid_disp")${tab}$(_planveyor_table_cell "$set_at")"
      )
    fi
  done

  if command -v column >/dev/null 2>&1; then
    printf '%s\n' "${role_rows[@]}" | column -t -s $'\t'
  else
    printf '%s\n' "${role_rows[@]}"
  fi
}

_planveyor_process_sessions_table() {
  # Usage: _planveyor_process_sessions_table <wide:0|1> [project_root]
  # Like the manual table: rows read under the root bound by the owner.
  local wide="${1:-0}"
  local root="${2:-}"
  if [[ -z "${root//[[:space:]]/}" ]]; then
    root="$(_planveyor_project_root)" || return $?
  fi
  local tab=$'\t'
  local -a rows
  rows=()
  if (( wide )); then
    rows+=("track${tab}session_key${tab}sid${tab}action${tab}set_at${tab}session_file")
  else
    rows+=("track${tab}sid${tab}action${tab}set")
  fi

  local -a tracks
  tracks=(
    $'roles\tarchitect_process_roles'
    $'collab\tarchitect_process_collab'
    $'inno\tarchitect_innovations'
  )

  local t
  for t in "${tracks[@]}"; do
    local track="${t%%$'\t'*}"
    local session_key="${t#*$'\t'}"
    local sid="" set_at=""
    sid="$(_planveyor_read "$root/.planveyor.session.${session_key}" 2>/dev/null || true)"
    [[ "$sid" == "<SESSION_ID>" ]] && sid=""

    local log_path="$root/.planveyor.session.${session_key}.log"
    if [[ -f "$log_path" ]]; then
      local log_last=""
      log_last="$(_planveyor_last_line "$log_path" 2>/dev/null || true)"
      if [[ -n "${log_last//[[:space:]]/}" && "$log_last" == *$'\t'* ]]; then
        set_at="${log_last%%$'\t'*}"
        set_at="${set_at#"${set_at%%[![:space:]]*}"}"
      fi
    fi
    set_at="$(_planveyor_dt_short "$set_at")"

    local action=""
    if [[ -z "${sid//[[:space:]]/}" ]]; then
      action="start"
    elif _planveyor_is_uuid "$sid"; then
      action="resume"
    else
      action="UNCONFIRMED"
    fi

    if (( wide )); then
      rows+=(
        "${track}${tab}$(_planveyor_table_cell "$session_key")${tab}$(_planveyor_table_cell "$sid")${tab}$(_planveyor_table_cell "$action")${tab}$(_planveyor_table_cell "$set_at")${tab}$(_planveyor_table_cell ".planveyor.session.${session_key}")"
      )
    else
      local sid_disp="$sid"
      if [[ -n "${sid_disp//[[:space:]]/}" ]]; then
        if _planveyor_is_uuid "$sid_disp"; then
          sid_disp="${sid_disp%%-*}"
        else
          sid_disp="${sid_disp[1,12]}"
        fi
      fi
      rows+=(
        "${track}${tab}$(_planveyor_table_cell "$sid_disp")${tab}$(_planveyor_table_cell "$action")${tab}$(_planveyor_table_cell "$set_at")"
      )
    fi
  done

  if command -v column >/dev/null 2>&1; then
    printf '%s\n' "${rows[@]}" | column -t -s $'\t'
  else
    printf '%s\n' "${rows[@]}"
  fi
}

_planveyor_log_source_from_tsv_line() {
  # Extracts wrapper source from a generic planveyor TSV log line.
  # Supported patterns:
  # - collab agent log: <ts>\t<sid>\t<event>\t<source[;note]>
  # - session log:      <ts>\t<sid>\t... source=<source> ...
  local line="$1"
  [[ -n "${line//[[:space:]]/}" ]] || return 1
  [[ "$line" == *$'\t'* ]] || return 1

  local rest="${line#*$'\t'}"   # sid + tail
  [[ "$rest" == *$'\t'* ]] || return 1
  rest="${rest#*$'\t'}"         # third field (+ optional fourth)

  local field3="$rest"
  local field4=""
  if [[ "$rest" == *$'\t'* ]]; then
    field3="${rest%%$'\t'*}"
    field4="${rest#*$'\t'}"
  fi

  local src=""
  if [[ -n "${field4//[[:space:]]/}" ]]; then
    src="$field4"
    if [[ "$src" == *"source="* ]]; then
      src="${src#*source=}"
      src="${src%%[;[:space:]]*}"
    else
      src="${src%%;*}"
      src="${src%% *}"
    fi
  elif [[ "$field3" == *"source="* ]]; then
    src="${field3#*source=}"
    src="${src%%[;[:space:]]*}"
  fi

  src="${src//$'\r'/}"
  src="${src#"${src%%[![:space:]]*}"}"
  src="${src%"${src##*[![:space:]]}"}"
  [[ "$src" == planveyor_* ]] || return 1
  echo "$src"
}

_planveyor_collab_last_source_hint() {
  # Usage: _planveyor_collab_last_source_hint [project_root]
  # Returns dominant wrapper source from latest collab agent log rows:
  #   <source>\t<matched>/<total_with_source>
  local root="${1:-}"
  typeset -A counts
  local total=0
  local role=""
  for role in "${(@f)$(_planveyor_collab_agent_roles_display "$root")}"; do
    local log_path="$(_planveyor_collab_agent_log_file "$role" "$root")"
    [[ -f "$log_path" ]] || continue
    local last=""
    last="$(_planveyor_last_line "$log_path" 2>/dev/null || true)"
    local src=""
    src="$(_planveyor_log_source_from_tsv_line "$last" 2>/dev/null || true)"
    [[ -n "${src//[[:space:]]/}" ]] || continue
    (( counts[$src]++ ))
    (( total++ ))
  done
  (( total > 0 )) || return 1

  local best_src=""
  local best_n=0
  local key=""
  for key in ${(k)counts}; do
    if (( counts[$key] > best_n )); then
      best_src="$key"
      best_n=${counts[$key]}
    fi
  done
  [[ -n "${best_src//[[:space:]]/}" ]] || return 1
  echo "${best_src}"$'\t'"${best_n}/${total}"
}

_planveyor_log_last_source_in_file() {
  # Returns the last parseable planveyor_* source from a TSV log file.
  local log_path="$1"
  [[ -f "$log_path" ]] || return 1
  local line=""
  local src=""
  local last_src=""
  while IFS= read -r line || [[ -n "$line" ]]; do
    src="$(_planveyor_log_source_from_tsv_line "$line" 2>/dev/null || true)"
    [[ -n "${src//[[:space:]]/}" ]] && last_src="$src"
  done < "$log_path"
  [[ -n "${last_src//[[:space:]]/}" ]] || return 1
  echo "$last_src"
}

_planveyor_collab_sessions_table() {
  # Usage: _planveyor_collab_sessions_table <wide:0|1> [project_root]
  # Like the manual table: rows read under the root bound by the owner.
  local wide="${1:-1}"
  local root="${2:-}"
  if [[ -z "${root//[[:space:]]/}" ]]; then
    root="$(_planveyor_project_root)" || return $?
  fi

  local source_hint=""
  local source_hint_out=""
  source_hint_out="$(_planveyor_collab_last_source_hint "$root" 2>/dev/null || true)"
  if [[ -n "${source_hint_out//[[:space:]]/}" ]]; then
    source_hint="${source_hint_out%%$'\t'*}"
  fi

  local -a rows
  rows=()
  local tab=$'\t'
  if (( wide )); then
    rows+=("role${tab}thread_id${tab}src${tab}set_at${tab}state_file")
  else
    rows+=("role${tab}thread_id${tab}src${tab}set${tab}file")
  fi

  local -a collab_roles
  collab_roles=("${(@f)$(_planveyor_collab_agent_roles_display "$root")}")
  local role
  for role in manager "${collab_roles[@]}"; do
    local state_path="" sid="" set_at="" log_path="" role_source=""
    if [[ "$role" == "manager" ]]; then
      state_path="$root/.planveyor.session.manager"
      sid="$(_planveyor_read "$state_path" 2>/dev/null || true)"
      [[ "$sid" == "<SESSION_ID>" ]] && sid=""
      log_path="$root/.planveyor.session.manager.log"
    else
      state_path="$(_planveyor_collab_agent_file "$role" "$root")"
      if [[ -f "$state_path" ]]; then
        sid="$(_planveyor_read "$state_path" 2>/dev/null || true)"
      fi
      log_path="$(_planveyor_collab_agent_log_file "$role" "$root")"
    fi

    if [[ -f "$log_path" ]]; then
      local log_last=""
      log_last="$(_planveyor_last_line "$log_path" 2>/dev/null || true)"
      if [[ -n "${log_last//[[:space:]]/}" && "$log_last" == *$'\t'* ]]; then
        set_at="${log_last%%$'\t'*}"
        set_at="${set_at#"${set_at%%[![:space:]]*}"}"
        role_source="$(_planveyor_log_source_from_tsv_line "$log_last" 2>/dev/null || true)"
      fi
      if [[ -z "${role_source//[[:space:]]/}" ]]; then
        role_source="$(_planveyor_log_last_source_in_file "$log_path" 2>/dev/null || true)"
      fi
    fi
    set_at="$(_planveyor_dt_short "$set_at")"
    [[ -n "${role_source//[[:space:]]/}" ]] || role_source="$source_hint"

    if (( wide )); then
      rows+=(
        "${role}${tab}$(_planveyor_table_cell "$sid")${tab}$(_planveyor_table_cell "$role_source")${tab}$(_planveyor_table_cell "$set_at")${tab}$(_planveyor_table_cell "${state_path:t}")"
      )
    else
      rows+=(
        "${role}${tab}$(_planveyor_table_cell "$sid")${tab}$(_planveyor_table_cell "$role_source")${tab}$(_planveyor_table_cell "$set_at")${tab}$(_planveyor_table_cell "${state_path:t}")"
      )
    fi
  done

  if command -v column >/dev/null 2>&1; then
    printf '%s\n' "${rows[@]}" | column -t -s $'\t'
  else
    printf '%s\n' "${rows[@]}"
  fi
}

planveyor_show_manual() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_show_manual)" || return $?
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
  local wide=0
  while (( $# > 0 )); do
    case "${1:-}" in
      --wide) wide=1 ;;
      --help|-h)
        echo "Usage: planveyor_show_manual [--wide]" >&2
        return 0
        ;;
      *)
        echo "Usage: planveyor_show_manual [--wide]" >&2
        return 1
        ;;
    esac
    shift
  done

  local root=""
  root="$(_planveyor_project_root)" || return $?
  echo "root: ${root}"

  local range_base=""
  local range_head=""
  local range_merge=""
  range_base="$(planveyor_range_base 2>/dev/null || true)"
  range_head="$(planveyor_range_head 2>/dev/null || true)"
  range_merge="$(planveyor_range_merge 2>/dev/null || true)"
  if [[ -n "${range_base//[[:space:]]/}" && -n "${range_head//[[:space:]]/}" ]]; then
    echo "range: ${range_base}..${range_head}"
    if [[ -n "${range_merge//[[:space:]]/}" ]]; then
      echo "merge: ${range_merge}"
    fi
  else
    echo "range: (not set)"
  fi

  local plan_path=""
  plan_path="$(planveyor_planpath 2>/dev/null || true)"
  if [[ -n "${plan_path//[[:space:]]/}" ]]; then
    local plan_fs="$plan_path"
    [[ "$plan_fs" == /* ]] || plan_fs="${root}/${plan_fs}"
    if [[ -f "$plan_fs" ]]; then
      echo "plan: ${plan_path}"
    else
      echo "plan: ${plan_path} (missing)"
    fi
    local status_line=""
    if [[ -f "$plan_fs" ]]; then
      status_line="$(planveyor_status_line "$plan_fs" 2>/dev/null || true)"
    fi
    if [[ -n "${status_line//[[:space:]]/}" ]]; then
      local status_value=""
      status_value="$(_planveyor_extract_status_value "$status_line" 2>/dev/null || true)"
      local runner=""
      runner="$(_planveyor_suggest_runner_from_status "$status_value")"
      echo "status: ${status_line}"
      [[ -n "${status_value//[[:space:]]/}" ]] && echo "next: ${runner} (from Status: ${status_value})"
    fi
  else
    echo "plan: (not set)"
  fi

  _planveyor_manual_sessions_table "$wide" "$root"
  if (( wide )); then
    echo ""
    echo "execution_ready:"
    _planveyor_role_runner_execution_ready_table
  fi

  local pybin=""
  pybin="$(_planveyor_get_pybin 2>/dev/null || true)"
  if [[ -n "${pybin//[[:space:]]/}" ]]; then
    echo "pybin: ${pybin}"
  else
    echo "pybin: (missing)"
  fi

  local answers_path="$root/.planveyor.owner_answers"
  if [[ -f "$answers_path" ]]; then
    local to=""
    local plan=""
    local -a body_lines
    body_lines=()
    local line=""
    local in_body=0
    while IFS= read -r line || [[ -n "$line" ]]; do
      if (( in_body )); then
        body_lines+=("$line")
        continue
      fi
      [[ -z "${line//[[:space:]]/}" ]] && continue
      [[ "$line" == TO=* ]] && { to="${line#TO=}"; continue; }
      [[ "$line" == PLAN_PATH=* ]] && { plan="${line#PLAN_PATH=}"; continue; }
      [[ "$line" == "---" ]] && { in_body=1; continue; }
    done < "$answers_path"
    to="${to//[[:space:]]/}"
    plan="${plan//[[:space:]]/}"
    local body_total=${#body_lines}
    echo "owner_answers: pending (TO=${to:-?}, PLAN_PATH=${plan:-?}, lines=${body_total})"
    if (( body_total > 0 )); then
      local max_preview=12
      (( body_total < max_preview )) && max_preview="$body_total"
      echo "owner_answers_preview:"
      local i=1
      for i in {1..$max_preview}; do
        echo "  ${body_lines[$i]}"
      done
      if (( body_total > max_preview )); then
        echo "  ... (${body_total-max_preview} more lines; see: cat \"${answers_path}\")"
      fi
    fi
  else
    echo "owner_answers: (none)"
  fi

  echo ""
  echo "commands (manual; see: planveyor_help --manual):"
  echo "  planveyor_show --all|--manual|--collab|--process [--wide]"
  echo "  planveyor_help --all|--manual|--collab|--process"
  echo ""
  echo "  # plans"
  echo "  planveyor_plan_set <PLAN_PATH>"
  echo "  planveyor_plan_closeout_preflight [--docs-closeout-json <path|->] [--json] <PLAN_PATH>"
  echo "  planveyor_q_set <PLAN_PATH...>|--status <STATUS...>|--from-umbrella <PLAN_PATH> --for-manager-mode <manager-collab|manager-custom-pipeline>"
  echo "  planveyor_q_append [--json] <PLAN_PATH...> --for-manager-mode <manager-collab|manager-custom-pipeline>"
  echo "  planveyor_q_show"
  echo "  planveyor_planqueue_metrics"
  echo "  planveyor_planning_wave_readback"
  echo "  planveyor_wave_telemetry_report"
  echo "  planveyor_q_final_report [--format plain|json]"
  echo "  planveyor_q_next_json --manager-mode <MODE> | planveyor_q_small_slice_json <PLAN_PATH> | planveyor_q_advance_json <Done|Superseded> --manager-mode <MODE>"
  echo "  planveyor_q_closeout_json --manager-mode <manager-collab|manager-custom-pipeline> | planveyor_q_stop_json <REASON> [--source-plan <PLAN_PATH>] | planveyor_q_planpath_override_json <PLAN_PATH> [REASON]"
  echo "  planveyor_q_clear"
  echo "  planveyor_bare_entrypoints_doctor [--bin-dir DIR]"
  echo "  planveyor_rollout_packet_create <target_repo> <topic_slug> [--source-plan docs/plans/<...>.md] [--dry-run]"
  echo "  planveyor_rollout_packet_show docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md [--raw]"
  echo "  planveyor_rollout_packet_import_instructions docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md [--print-target-plan-seed]"
  echo "  planveyor_rollout_packet_lint (--all | docs/rollout_packets/<packet>.md|docs/rollout_packets) [--json]"
  echo "  planveyor_rollout_packet_ack --packet docs/rollout_packets/<...>.md --status imported --target-plan docs/plans/<...>.md"
  echo "  planveyor_rollout_packet_query [--status open|imported|superseded|cancelled|all] [--json]"
  echo "  planveyor_rollout_packet_reconcile --report [--older-than-days N] [--target-root PATH --target-repo planveyor] [--json]"
  echo "  planveyor_rollout_packet_outcome_set --target-plan docs/plans/<...>.md --packet-id <id> --packet-path docs/rollout_packets/<...>.md --outcome <canonical-or-alias>"
  echo "  planveyor_upstream_request_show docs/upstream_packets/<YYMMDD_HHMM>_<origin_repo>_<topic>.md [--raw]"
  echo "  planveyor_upstream_request_import --packet docs/upstream_packets/<...>.md [--dry-run]"
  echo "  planveyor_upstream_request_ack --packet docs/upstream_packets/<...>.md --source-decision-ref docs/plans/<...> [--source-execution-ref docs/plans/<...>] [--dry-run]"
  echo "  planveyor_upstream_request_query [--status open] [--origin-repo <sibling>] [--json]"
  echo "  planveyor_plan_list [--include-non-executable] [TERMS...]"
  echo "  planveyor_plan_list_status <STATUS_FILTER> [--include-non-executable] [TERMS...]"
  echo ""
  echo "  # sessions / runners"
  echo "  planveyor_session <key>"
  echo "  planveyor_session_set <key> <SID> [META]"
  echo "  planveyor_runner <role>"
  echo "  planveyor_runner_set <role> <runner>"
  echo "  planveyor_runner_clear <role>"
  echo "  planveyor_role_runner_preflight <role> [--json]"
  echo "  planveyor_custom_role_step <role> --plan <PLAN_PATH> --json"
  echo "  planveyor_role_run <role> [--timeout SECONDS] [--json]"
  echo "  planveyor_role_run_receipt_check <receipt.json> [--json]"
  echo "  planveyor_profile <architect|coder|planner> [main|censor]"
  echo "  planveyor_profile_set <architect|coder|planner> <PROFILE> [main|censor]"
  echo "  planveyor_profile_clear <architect|coder|planner> [main|censor]"
  echo ""
  echo "  # roles (status-driven)"
  echo "  planveyor_arch | planveyor_planner | planveyor_coder | planveyor_reviewer | planveyor_reviewer_code_risk | planveyor_reviewer_code_contracts | planveyor_manager"
  echo "  planveyor_arch_init | planveyor_planner_init | planveyor_coder_init | planveyor_reviewer_init | planveyor_reviewer_code_risk_init | planveyor_reviewer_code_contracts_init | planveyor_manager_init"
  echo "  planveyor_arch_resume | planveyor_planner_resume | planveyor_coder_resume | planveyor_reviewer_resume | planveyor_reviewer_code_risk_resume | planveyor_reviewer_code_contracts_resume | planveyor_manager_resume"
  echo ""
  echo "  # docs/hygiene"
  echo "  planveyor_doc_lint  # strict canonical pass"
  echo "  planveyor_docs_hygiene_list [BASE..HEAD|BASE HEAD]  # optional inventory helper"
  echo "  planveyor_docs_hygiene_suggest              # report-only cleanup handoff"
  echo "  planveyor_docs_hygiene_archive --range BASE..HEAD [--apply]  # manual rerun / вне pipeline"
  echo "  planveyor_followups_lint [docs/followups/<file>.md ...] [--project-root PATH] [--format text|json]"
  echo "  planveyor_followups_reconcile [--project-root PATH] [--report|--apply] [--write-to DIR] [--format text|json]"
  echo "  planveyor_followups_apply --frozen-manifest <cycle.json> [--apply] [--project-root PATH]"
  echo "  planveyor_followups_promote --project-root PATH --file docs/followups/<file>.md --line N --plan-path docs/plans/<...>.md [--dry-run|--apply]"
  echo "  planveyor_followups_promote --project-root PATH --file docs/followups/<file>.md --prepare-v2|--finalize-v2 --item-id <stable-id> --plan-path docs/plans/<...>.md [--frozen-manifest <cycle.json> --commit-oid <Commit-A>]"
  echo "  planveyor_process_improvements_promote --project-root PATH --backlog docs/process_improvements/<file>.md --entry PI-001 --execution-kind <kind> --execution-ref <ref> --promoted-at '<timestamp>' [--report|--apply]"
  echo "  planveyor_process_improvements_reconcile [--project-root PATH] [--backlog docs/process_improvements/<file>.md] [--report|--apply --handled-at '<timestamp>']"
  echo "  planveyor_followups_query <ready-candidates|needs-owner-triage|broken-plan-links|stale-promoted|cleanup-ready|cleanup-receipt> [--source-ref <exact> --item-id <stable-id>] [--project-root PATH] [--format text|json]"
  echo "  planveyor_followups_triage [--all] | [--file docs/followups/<inbox>.md] | [--range BASE..HEAD|BASE HEAD] [--dry-run|--apply]"
  echo "  planveyor_docs_index_build <canon|followups|plans|all> [--db PATH] [--root docs] [--chunk-target-tokens N] [--force-rebuild]"
  echo "  planveyor_docs_db  # print default docs retrieval DB path"
  echo "  planveyor_docs_retrieve <canon|followups|plans> [--db PATH] [--k N|--all] [--format text|md|json|--md] [--files] [--min-score 0..1] [--no-context] [--log-file PATH|--no-log] \"FTS query\""
  echo "  planveyor_docs_retrieve_log  # print active docs retrieval query log path (or 'disabled')"
  echo "  planveyor_docs_retrieve_outcome_log  # print active docs retrieval outcome log path (or 'disabled')"
  echo "  planveyor_docs_retrieve_read_log  # print active docs read/open log path (or 'disabled')"
  echo "  planveyor_docs_retrieve_outcome (--event-id ID|--latest) --outcome used|partial|miss|noise|not_evaluated [--opened-file PATH] [--cited-file PATH] [--note TEXT]"
  echo "  planveyor_docs_retrieve_metrics [--query-log PATH] [--outcome-log PATH] [--read-log PATH] [--format text|json]"
  echo "  planveyor_docs_lookup <canon|followups|plans> [docs_retrieve flags] \"FTS query\"  # query + docs_multi_get + receipt skeleton"
  echo "  planveyor_docs_get <path|path:line> [--from-line N --lines M | --full] [--max-bytes N] [--max-lines N] [--format text|md|json] [--no-context] [--read-log PATH|--no-read-log]"
  echo "  planveyor_docs_multi_get [glob|path|@filelist|- ...] [--format md|json] [--max-bytes N] [--max-bytes-per-doc N] [--max-files N] [--no-context] [--read-log PATH|--no-read-log]"
  echo "  planveyor_docs_context_check --corpus <canon|followups|plans> [--db PATH] [--format text|json] [--max-uncovered N] [--max-hints N]"
  echo "  planveyor_docs_archive_db  # print default central docs archive DB path"
  echo "  planveyor_docs_archive_query [--db PATH] [--profile signal|all] [--kind KIND] [--k N] [--md] \"query\""
  echo "  planveyor_docs_archive_show [--db PATH] (--id N | --path PATH)"
  echo "  planveyor_docs_archive_snapshot_info [--db PATH] [--json]"
  echo "  planveyor_docs_archive_snapshot_export [--db PATH] [--backend git_text_export|git_whole_sqlite|s3_minio_sqlite] [--output-dir DIR] [--force]"
  echo "  planveyor_docs_archive_snapshot_validate --manifest PATH [--verify-artifact] [--object-file PATH]"
  echo "  planveyor_docs_archive_snapshot_restore --manifest PATH --dest-db PATH [--replace] [--object-file PATH] [--query TEXT] [--expect-min-hits N]"
  echo "  planveyor_docs_hygiene_archive --range BASE..HEAD [--apply]"
  echo "  planveyor_code_draft_stub_from_plan [PLAN_PATH] [--role Planner|Coder|Architect]"
  echo ""
  echo "  # review/merge (range + tracker)"
  echo "  planveyor_range_set <BASE_SHA> <HEAD_SHA> [MERGE_SHA]"
  echo "  planveyor_range_set_merge <MERGE_SHA> [HEAD_SHA]"
  echo "  planveyor_merge_init | planveyor_merge_tracker_init | planveyor_merge_tracker_ensure | planveyor_merge_tracker_show | planveyor_merge_next | planveyor_post_merge_packetization_gate | planveyor_post_merge_packetization_gate_recover | planveyor_post_merge_receipt_skeleton | planveyor_post_merge_receipt_preflight | planveyor_post_merge_docs_finalize_tick | planveyor_post_merge_operational_receipt | planveyor_post_merge_docs_hygiene_suggest_gate | planveyor_merge_bundle_report | planveyor_post_merge_ready_to_push_closeout | planveyor_merge_range_verdict_digest"
  echo "  planveyor_review_range_start [EXCLUDE_DOCS=1|0] | planveyor_review_range_start <BASE_SHA> <HEAD_SHA> [EXCLUDE_DOCS=1|0]"
  echo "  planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]"
  echo "  planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]"
  echo ""
  echo "  # services"
}

_planveyor_collab_agent_file() {
  # Usage: _planveyor_collab_agent_file <role> [project_root]
  local root="${2:-}"
  if [[ -z "${root//[[:space:]]/}" ]]; then
    root="$(_planveyor_project_root)" || return $?
  fi
  echo "${root}/.planveyor.collab.agent.$1"
}
_planveyor_collab_agent_log_file() {
  # Usage: _planveyor_collab_agent_log_file <role> [project_root]
  local root="${2:-}"
  if [[ -z "${root//[[:space:]]/}" ]]; then
    root="$(_planveyor_project_root)" || return $?
  fi
  echo "${root}/.planveyor.collab.agent.$1.log"
}

_planveyor_collab_agent_role_is_known() {
  case "${1:-}" in
    architect|planner|coder|reviewer|reviewer_code_risk|reviewer_code_contracts) return 0 ;;
    *) return 1 ;;
  esac
}

_planveyor_collab_agent_roles_primary() {
  print -l -- architect planner coder reviewer_code_risk reviewer_code_contracts
}

_planveyor_collab_v2_task_expected_leaf() {
  case "${1:-}" in
    architect) echo "architect_sol_xhigh_v2" ;;
    planner) echo "planner_terra_ultra_v2" ;;
    coder) echo "coder_terra_ultra_v2" ;;
    reviewer_code_risk) echo "reviewer_code_risk_sol_xhigh_v2" ;;
    reviewer_code_contracts) echo "reviewer_code_contracts_sol_xhigh_v2" ;;
    *) return 1 ;;
  esac
}

_planveyor_collab_v2_task_name_is_compatible() {
  local role_id="${1:-}"
  local task_name="${2:-}"
  local expected_leaf=""

  expected_leaf="$(_planveyor_collab_v2_task_expected_leaf "$role_id" 2>/dev/null)" || return 1
  [[ "$task_name" == "/root/${expected_leaf}" ]]
}

_planveyor_collab_agent_roles_display() {
  # Usage: _planveyor_collab_agent_roles_display [project_root]
  local -a roles
  roles=("${(@f)$(_planveyor_collab_agent_roles_primary)}")
  local legacy_state="$(_planveyor_collab_agent_file reviewer "${1:-}")"
  local legacy_log="$(_planveyor_collab_agent_log_file reviewer "${1:-}")"
  if [[ -f "$legacy_state" || -f "$legacy_log" ]]; then
    roles+=(reviewer)
  fi
  print -l -- "${roles[@]}"
}

_planveyor_collab_log_last_id() {
  # Reads last logged thread id from `.planveyor.collab.agent.<role>.log`.
  # Supports both formats:
  #   legacy:  <TS>\t<ID>
  #   current: <TS>\t<ID>\t<EVENT>[\t<NOTE>]
  local role_id="$1"
  local log_path="$(_planveyor_collab_agent_log_file "$role_id")"
  [[ -f "$log_path" ]] || return 1
  local last=""
  last="$(_planveyor_last_line "$log_path" 2>/dev/null || true)"
  [[ -n "${last//[[:space:]]/}" ]] || return 1
  if [[ "$last" == *$'\t'* ]]; then
    local rest="${last#*$'\t'}"
    local id="${rest%%$'\t'*}"
    id="${id//$'\r'/}"
    id="${id#"${id%%[![:space:]]*}"}"
    id="${id%"${id##*[![:space:]]}"}"
    [[ -n "${id//[[:space:]]/}" ]] || return 1
    echo "$id"
    return 0
  fi
  return 1
}

_planveyor_collab_event_is_known() {
  case "${1:-}" in
    spawn|respawn|reset|close|sync) return 0 ;;
    *) return 1 ;;
  esac
}

_planveyor_collab_log_append() {
  # Usage: _planveyor_collab_log_append <role> <id> [event] [note]
  # event: spawn|respawn|reset|close|sync
  # Normalized envelope mapping for `.planveyor.collab.agent.<role>.log`:
  # - schema_version = collab_agent_log.v1 (doc-level contract; TSV stays append-only)
  # - event_type = collab_agent.<event> (legacy 2-column rows stay historical/UNCONFIRMED)
  # - ts = column 1
  # - trace_id = column 2 (`sid`) when it is a real subagent/session id
  # - event_id/span_id = derived from role + ts + event + sid
  # - parent_span_id = N/A; `prev=` in notes remains lineage hint only
  local role_id="$1"
  local sid="$2"
  local event="${3:-sync}"
  local note="${4:-}"
  local log_path="$(_planveyor_collab_agent_log_file "$role_id")"
  local now="$(_planveyor_now)"
  if ! _planveyor_collab_event_is_known "$event"; then
    echo "Refusing to append collab log: unsupported event; expected spawn|respawn|reset|close|sync" >&2
    return 1
  fi
  # Keep log TSV-friendly and append-only.
  note="${note//$'\t'/ }"
  note="${note//$'\n'/ }"
  if [[ -n "${note//[[:space:]]/}" ]]; then
    printf "%s\t%s\t%s\t%s\n" "$now" "$sid" "$event" "$note" >> "$log_path"
  else
    printf "%s\t%s\t%s\n" "$now" "$sid" "$event" >> "$log_path"
  fi
}

_planveyor_collab_snapshot_ids() {
  # Prints role<tab>id for all collab roles.
  local role=""
  for role in "${(@f)$(_planveyor_collab_agent_roles_display)}"; do
    local sid=""
    local state_path="$(_planveyor_collab_agent_file "$role")"
    if [[ -f "$state_path" ]]; then
      sid="$(_planveyor_read "$state_path" 2>/dev/null || true)"
      sid="${sid//$'\r'/}"
      sid="${sid#"${sid%%[![:space:]]*}"}"
      sid="${sid%"${sid##*[![:space:]]}"}"
    fi
    printf "%s\t%s\n" "$role" "$sid"
  done
}

_planveyor_collab_log_transitions() {
  # Usage: _planveyor_collab_log_transitions <before_snapshot.tsv> <after_snapshot.tsv> [source]
  local before_file="$1"
  local after_file="$2"
  local source="${3:-wrapper}"
  [[ -f "$before_file" && -f "$after_file" ]] || return 1

  typeset -A before_map
  typeset -A after_map
  local role="" sid=""
  while IFS=$'\t' read -r role sid || [[ -n "${role//[[:space:]]/}" ]]; do
    [[ -n "${role//[[:space:]]/}" ]] || continue
    before_map[$role]="$sid"
  done < "$before_file"
  while IFS=$'\t' read -r role sid || [[ -n "${role//[[:space:]]/}" ]]; do
    [[ -n "${role//[[:space:]]/}" ]] || continue
    after_map[$role]="$sid"
  done < "$after_file"

  for role in "${(@f)$(_planveyor_collab_agent_roles_display)}"; do
    local before_sid="${before_map[$role]:-}"
    local after_sid="${after_map[$role]:-}"
    if [[ -n "${before_sid//[[:space:]]/}" && -z "${after_sid//[[:space:]]/}" ]]; then
      _planveyor_collab_log_append "$role" "$before_sid" "close" "$source"
    elif [[ -z "${before_sid//[[:space:]]/}" && -n "${after_sid//[[:space:]]/}" ]]; then
      _planveyor_collab_log_append "$role" "$after_sid" "spawn" "$source"
    elif [[ -n "${before_sid//[[:space:]]/}" && -n "${after_sid//[[:space:]]/}" && "$before_sid" != "$after_sid" ]]; then
      # Ignore short->full normalization (same session id prefix). This can happen
      # when wrappers expand an 8-hex Codex SID prefix to the full UUID.
      if [[ "$before_sid" != *"-"* && "$after_sid" == "${before_sid}"-* ]]; then
        continue
      fi
      if [[ "$after_sid" != *"-"* && "$before_sid" == "${after_sid}"-* ]]; then
        continue
      fi
      _planveyor_collab_log_append "$role" "$after_sid" "respawn" "${source};prev=${before_sid}"
    fi
  done
}

_planveyor_expand_codex_sid_prefix() {
  # Best-effort: expand a short UUID prefix (e.g. "019c1400") to a full sid by
  # scanning rollout logs in the effective CODEX_HOME for this worktree.
  local prefix="${1:-}"
  [[ -n "${prefix//[[:space:]]/}" ]] || return 1
  [[ "$prefix" != *"-"* ]] || return 1
  # Only accept hex-ish prefixes to avoid weird matches.
  [[ "$prefix" == [0-9a-fA-F]## ]] || return 1

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local codex_home="$(_planveyor_codex_home_effective)"

  local out=""
  local sid_full=""

  out="$(_planveyor_py_any "$(_planveyor_codex_session_stats_script)" --list --codex-home "$codex_home" --search-all --limit 400 --days 90 --cwd-prefix "$root" 2>/dev/null || true)"
  sid_full="$(printf '%s\n' "$out" | awk -F $'\t' -v p="$prefix" 'NR>1 && index($1,p)==1 {print $1; exit}')"

  if [[ -z "${sid_full//[[:space:]]/}" ]]; then
    out="$(_planveyor_py_any "$(_planveyor_codex_session_stats_script)" --list --codex-home "$codex_home" --search-all --limit 400 --days 90 --cwd-prefix "$root" --null-sessions 2>/dev/null || true)"
    sid_full="$(printf '%s\n' "$out" | awk -F $'\t' -v p="$prefix" 'NR>1 && index($1,p)==1 {print $1; exit}')"
  fi

  if [[ -z "${sid_full//[[:space:]]/}" ]]; then
    # Last resort: drop cwd filter, but still search-all. Prefix collisions are
    # unlikely for 8+ chars; we accept the first match.
    out="$(_planveyor_py_any "$(_planveyor_codex_session_stats_script)" --list --codex-home "$codex_home" --search-all --limit 800 --days 180 2>/dev/null || true)"
    sid_full="$(printf '%s\n' "$out" | awk -F $'\t' -v p="$prefix" 'NR>1 && index($1,p)==1 {print $1; exit}')"
  fi

  [[ -n "${sid_full//[[:space:]]/}" ]] || return 1
  echo "$sid_full"
}

_planveyor_collab_agent_sync_one() {
  local role_id="$1"
  _planveyor_collab_agent_role_is_known "$role_id" || return 1

  local file_path="$(_planveyor_collab_agent_file "$role_id")"
  [[ -f "$file_path" ]] || return 0

  local sid=""
  sid="$(_planveyor_read "$file_path" 2>/dev/null || true)"
  [[ -n "${sid//[[:space:]]/}" ]] || return 0

  # If Manager stored a short UUID prefix, try to expand it to the full sid
  # so tooling (show/table/stats) works reliably.
  if [[ "$sid" != *"-"* && "$sid" =~ '^[0-9a-fA-F]{8}$' ]]; then
    local expanded=""
    expanded="$(_planveyor_expand_codex_sid_prefix "$sid" 2>/dev/null || true)"
    [[ -n "${expanded//[[:space:]]/}" ]] && sid="$expanded"
  fi

  # Normalize file format to match `.planveyor.session.*` convention:
  # - optional `# <timestamp>` header
  # - session/thread id on the last non-empty line (so Manager prompt can read it).
  local now="$(_planveyor_now)"
  local first_line=""
  first_line="$(head -n 1 "$file_path" 2>/dev/null || true)"
  local last_line=""
  last_line="$(_planveyor_last_line "$file_path" 2>/dev/null || true)"
  if [[ "$first_line" != \#* || "$last_line" != "$sid" ]]; then
    printf "# %s\n%s\n" "$now" "$sid" > "$file_path"
  fi

  local log_path="$(_planveyor_collab_agent_log_file "$role_id")"
  local last_id=""
  last_id="$(_planveyor_collab_log_last_id "$role_id" 2>/dev/null || true)"
  if [[ "$last_id" != "$sid" ]]; then
    _planveyor_collab_log_append "$role_id" "$sid" "sync"
  fi
}

_planveyor_collab_agent_sync_all() {
  local role
  for role in "${(@f)$(_planveyor_collab_agent_roles_display)}"; do
    _planveyor_collab_agent_sync_one "$role" >/dev/null 2>&1 || true
  done
}

planveyor_collab_state_write_alive() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_collab_state_write_alive)" || return $?
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
  # Usage:
  #   source scripts/planveyor.zsh && planveyor_collab_state_write_alive <role> <TASK_NAME|SID> [event] [note]
  #
  # V2 task names are persisted only after the Manager has proved exact liveness
  # via `list_agents`; this helper validates their canonical role/name mapping.
  # Legacy V1 SIDs still require rollout metadata, preserving the phantom-thread
  # guard for UUID and short-prefix callers.
  local role_id="${1:-}"
  local handle="${2:-}"
  local event="${3:-sync}"
  local note="${4:-}"
  local usage="Usage: planveyor_collab_state_write_alive <architect|planner|coder|reviewer|reviewer_code_risk|reviewer_code_contracts> <TASK_NAME|SID> [event] [note]"

  if ! _planveyor_collab_agent_role_is_known "$role_id"; then
    echo "$usage" >&2
    return 1
  fi
  [[ -n "${handle//[[:space:]]/}" ]] || {
    echo "$usage" >&2
    return 1
  }
  if ! _planveyor_collab_event_is_known "$event"; then
    echo "Refusing to persist collab state for ${role_id}: unsupported event; expected spawn|respawn|reset|close|sync" >&2
    return 1
  fi

  local handle_full="$handle"
  if [[ "$handle_full" == /* ]]; then
    if ! _planveyor_collab_v2_task_name_is_compatible "$role_id" "$handle_full"; then
      local expected_leaf=""
      expected_leaf="$(_planveyor_collab_v2_task_expected_leaf "$role_id" 2>/dev/null || true)"
      [[ -n "$expected_leaf" ]] || expected_leaf="no-v2-task-for-role"
      echo "Refusing to persist collab state for ${role_id}: incompatible V2 task name=${handle_full}; expected canonical task=/root/${expected_leaf}" >&2
      return 1
    fi
  else
    if [[ "$handle_full" != *"-"* ]]; then
      local expanded=""
      expanded="$(_planveyor_expand_codex_sid_prefix "$handle_full" 2>/dev/null || true)"
      [[ -n "${expanded//[[:space:]]/}" ]] && handle_full="$expanded"
    fi

    local stats_script="$(_planveyor_codex_session_stats_script)"
    local codex_home="$(_planveyor_codex_home_effective)"
    local meta_out=""
    meta_out="$(_planveyor_py_any "$stats_script" --sid "$handle_full" --codex-home "$codex_home" --search-all --mode quick --format kv 2>/dev/null || true)"
    [[ -n "${meta_out//[[:space:]]/}" ]] || {
      echo "Refusing to persist collab state for ${role_id}: no rollout found for sid=${handle_full}" >&2
      return 1
    }
  fi

  local file_path="$(_planveyor_collab_agent_file "$role_id")"
  local now="$(_planveyor_now)"
  local tmp_path="${file_path}.tmp.$$"
  if ! printf "# %s\n%s\n" "$now" "$handle_full" > "$tmp_path"; then
    echo "Refusing to persist collab state for ${role_id}: cannot stage state file" >&2
    return 1
  fi
  if ! _planveyor_collab_log_append "$role_id" "$handle_full" "$event" "$note"; then
    command rm -f -- "$tmp_path"
    return 1
  fi
  if ! command mv -f -- "$tmp_path" "$file_path"; then
    command rm -f -- "$tmp_path"
    echo "Refusing to persist collab state for ${role_id}: cannot install staged state file" >&2
    return 1
  fi
  echo "$handle_full"
}

planveyor_show_collab() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_show_collab)" || return $?
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
  # Default to wide for debugging/triage.
  local wide=1
  while (( $# > 0 )); do
    case "${1:-}" in
      --wide) wide=1 ;;
      --compact) wide=0 ;;
      --help|-h)
        echo "Usage: planveyor_show_collab [--wide|--compact]" >&2
        return 0
        ;;
      *)
        echo "Usage: planveyor_show_collab [--wide|--compact]" >&2
        return 1
        ;;
    esac
    shift
  done

  local root=""
  root="$(_planveyor_project_root)" || return $?
  echo "root: ${root}"
  local wt="$(_planveyor_worktree_id 2>/dev/null || true)"
  [[ -n "${wt//[[:space:]]/}" ]] && echo "worktree: ${wt}"


  local plan_path=""
  plan_path="$(planveyor_planpath 2>/dev/null || true)"
  if [[ -n "${plan_path//[[:space:]]/}" ]]; then
    local plan_fs="$plan_path"
    [[ "$plan_fs" == /* ]] || plan_fs="${root}/${plan_fs}"
    if [[ -f "$plan_fs" ]]; then
      echo "plan: ${plan_path}"
      local status_line=""
      status_line="$(planveyor_status_line "$plan_fs" 2>/dev/null || true)"
      [[ -n "${status_line//[[:space:]]/}" ]] && echo "status: ${status_line}"
    else
      echo "plan: ${plan_path} (missing)"
    fi
  else
    echo "plan: (not set)"
  fi

  local manager_sid=""
  manager_sid="$(planveyor_session manager 2>/dev/null || true)"
  [[ "$manager_sid" == "<SESSION_ID>" ]] && manager_sid=""
  if [[ -n "${manager_sid//[[:space:]]/}" ]]; then
    echo "manager_sid: ${manager_sid}"
  else
    echo "manager_sid: (missing)"
  fi
  local source_hint=""
  local source_hint_cov=""
  local source_hint_out=""
  source_hint_out="$(_planveyor_collab_last_source_hint "$root" 2>/dev/null || true)"
  if [[ -n "${source_hint_out//[[:space:]]/}" ]]; then
    source_hint="${source_hint_out%%$'\t'*}"
    if [[ "$source_hint_out" == *$'\t'* ]]; then
      source_hint_cov="${source_hint_out#*$'\t'}"
    fi
    if [[ -n "${source_hint_cov//[[:space:]]/}" ]]; then
      echo "collab_entrypoint: ${source_hint} (${source_hint_cov} agent logs)"
    else
      echo "collab_entrypoint: ${source_hint}"
    fi
  fi

  echo ""
  _planveyor_collab_sessions_table "$wide" "$root"

  echo ""
  echo "commands:"
  echo "  planveyor_show --collab [--wide]"
  echo "  planveyor_help --collab"
  echo ""
  echo "  # manager (one-shot)"
  echo "  planveyor_manager_collab"
  echo "  planveyor_q_set <PLAN_PATH...>|--status <STATUS...>|--from-umbrella <PLAN_PATH> --for-manager-mode <manager-collab|manager-custom-pipeline>"
  echo "  planveyor_q_append [--json] <PLAN_PATH...> --for-manager-mode <manager-collab|manager-custom-pipeline>"
  echo "  planveyor_q_show"
  echo "  planveyor_planqueue_metrics"
  echo "  planveyor_planning_wave_readback"
  echo "  planveyor_wave_telemetry_report"
  echo "  planveyor_q_clear"
  echo "  planveyor_decomposition_init [PLAN_PATH]"
  echo "  planveyor_decomposition_seed_promote <NEW_PLAN_PATH> [OLD_PLAN_PATH]"
  echo "  planveyor_decomposition_collab [PLAN_PATH]"
  echo ""
  echo "  # merge-mode (post-merge checks; starts pipeline)"
  echo "  planveyor_merge_collab_tui [--no-alt-screen] [--range auto|<MERGE_SHA>|<BASE..HEAD>]"
  echo "  planveyor_merge_collab_cmd [--range auto|<MERGE_SHA>|<BASE..HEAD>]"
  echo "  planveyor_merge_apply_collab_tui [--no-alt-screen] --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]"
  echo "  planveyor_merge_apply_collab_cmd --from <BRANCH> [--to <BRANCH>] [--then-review 0|1]"
  echo ""
  echo "  # manager (TUI)"
  echo "  planveyor_manager_collab_tui [--q] [--no-alt-screen] [--merge [--range auto|<MERGE_SHA>|<BASE..HEAD>]]"
  echo "  planveyor_decomposition_collab_tui [PLAN_PATH] [--no-alt-screen]"
  echo ""
  echo "  # manager commands (one-shot)"
  echo "  planveyor_manager_collab_cmd status"
  echo "  planveyor_manager_collab_cmd analysis docs/plans/YYMMDD_HHMM_analysis_wave.md"
  echo "  planveyor_manager_collab_cmd decomposition docs/plans/YYMMDD_HHMM_decomposition.md"
  echo "  planveyor_manager_collab_cmd run Q"
  echo "  planveyor_manager_collab_cmd run docs/plans/YYMMDD_HHMM_topic.md --followups-capture-cycle-id <UUIDv4>"
  echo "  planveyor_manager_collab_cmd close role=all"
  echo "  planveyor_manager_collab_cmd reset role=coder"
  echo "  planveyor_manager_custom_pipeline"
  echo "  planveyor_manager_custom_pipeline_tui [--no-alt-screen]"
  echo "  planveyor_manager_custom_pipeline_cmd status"
  echo "  planveyor_manager_custom_pipeline_cmd plan_set docs/plans/YYMMDD_HHMM_topic.md"
  echo "  planveyor_manager_custom_pipeline_cmd run"
  echo "  planveyor_manager_custom_pipeline_cmd run docs/plans/YYMMDD_HHMM_topic.md"
  echo "  planveyor_manager_custom_pipeline_cmd run Q"
  echo ""
  echo "  # fallback (manual resume + command)"
  echo "  planveyor_manager_resume  # then type: MANAGER_CMD=status|merge_run ...|close role=...|reset role=...|plan_set ...|run"
}

planveyor_show_process() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_show_process)" || return $?
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
  local wide=0
  while (( $# > 0 )); do
    case "${1:-}" in
      --wide) wide=1 ;;
      --help|-h)
        echo "Usage: planveyor_show_process [--wide]" >&2
        return 0
        ;;
      *)
        echo "Usage: planveyor_show_process [--wide]" >&2
        return 1
        ;;
    esac
    shift
  done

  local root="$(_planveyor_project_root)"
  echo "root: ${root}"

  echo ""
  _planveyor_process_sessions_table "$wide" "$root"

  echo ""
  echo "commands (process; see: planveyor_help --process):"
  echo "  planveyor_show --process [--wide]"
  echo "  planveyor_show_process [--wide]"
  echo ""
  echo "  # track TUI (resume if possible, else start)"
  echo "  planveyor_arch_roles_resume"
  echo "  planveyor_arch_collab_resume"
  echo "  planveyor_arch_inno_resume"
  echo ""
  echo "  # (deprecated aliases)"
  echo "  planveyor_arch_process_roles_tui"
  echo "  planveyor_arch_process_collab_tui"
  echo "  planveyor_arch_innovations_tui"
  echo ""
  echo "  # architect process utilities"
  echo "  planveyor_ai_gate --range BASE..HEAD --policy docs/tools/ai_gate_policy.example.json"
  echo "  planveyor_ai_gate_smoke --receipt-path .tmp/planveyor_ai_gate_smoke.json"
  echo "  planveyor_arch_merge_notes_start"
  echo "  planveyor_arch_plan_harvest_start"
  echo "  planveyor_arch_post_merge_audit_start"
  echo "  planveyor_arch_canon_sweep_start"
}

planveyor_show() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_show)" || return $?
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
  local filter="all"
  # Empty unless --wide is given: `${wide:+--wide}` below forwards the flag
  # only when requested.  A literal 0 is non-empty and would force the wide
  # manual view with its per-role execution-ready preflights.
  local wide=""

  while (( $# > 0 )); do
    case "${1:-}" in
      --all) filter="all" ;;
      --manual) filter="manual" ;;
      --collab) filter="collab" ;;
      --process) filter="process" ;;
      --wide) wide=1 ;;
      --help|-h)
        echo "Usage: planveyor_show [--all|--manual|--collab|--process] [--wide]" >&2
        return 0
        ;;
      *)
        echo "Usage: planveyor_show [--all|--manual|--collab|--process] [--wide]" >&2
        return 1
        ;;
    esac
    shift
  done

  case "$filter" in
    manual)
      planveyor_show_manual ${wide:+--wide}
      ;;
    collab)
      if (( wide )); then
        planveyor_show_collab --wide
      else
        planveyor_show_collab --compact
      fi
      ;;
    process)
      planveyor_show_process ${wide:+--wide}
      ;;
    all|*)
      echo "=== Manual ==="
      planveyor_show_manual ${wide:+--wide}
      echo ""
      echo "=== Collab ==="
      if (( wide )); then
        planveyor_show_collab --wide
      else
        planveyor_show_collab --compact
      fi
      echo ""
      echo "=== Process ==="
      planveyor_show_process ${wide:+--wide}
      ;;
  esac
}

planveyor_help() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_help)" || return $?
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
  local filter="all"
  local command=""
  while (( $# > 0 )); do
    case "${1:-}" in
      --all|all) filter="all" ;;
      --manual|manual) filter="manual" ;;
      --collab|collab) filter="collab" ;;
      --process|process) filter="process" ;;
      --help|-h)
        echo "Usage: planveyor_help [--all|--manual|--collab|--process|<command>]" >&2
        return 0
        ;;
      planveyor_*)
        [[ -z "$command" && "$filter" == "all" ]] || {
          echo "Usage: planveyor_help [--all|--manual|--collab|--process|<command>]" >&2
          return 1
        }
        command="${1:-}"
        ;;
      *)
        echo "Usage: planveyor_help [--all|--manual|--collab|--process|<command>]" >&2
        return 1
        ;;
    esac
    shift
  done

  local -a all_cmds
  all_cmds=("${(@f)$(_planveyor_list_public_commands)}")
  if [[ -n "$command" ]]; then
    local command_known=0
    local public_command=""
    for public_command in "${all_cmds[@]}"; do
      [[ "$public_command" == "$command" ]] || continue
      command_known=1
      break
    done
    (( command_known )) || {
      echo "Unknown planveyor command: ${command}" >&2
      return 1
    }
    _planveyor_help_cmd_usage "$command"
    return 0
  fi

  # Define narrow block command sets for drift checks (best-effort, auto).
  local -a process_cmds
  process_cmds=()
  process_cmds+=(${(M)all_cmds:#planveyor_show_process})
  process_cmds+=(${(M)all_cmds:#planveyor_arch_*_resume})
  process_cmds+=(${(M)all_cmds:#planveyor_arch_process_*_tui})
  process_cmds+=(${(M)all_cmds:#planveyor_arch_innovations_tui})
  process_cmds+=(${(M)all_cmds:#planveyor_arch_*_start})
  process_cmds=(${(u)process_cmds})
  process_cmds=(${(o)process_cmds})

  local -a collab_cmds
  collab_cmds=()
  collab_cmds+=(${(M)all_cmds:#planveyor_show_collab})
  collab_cmds+=(${(M)all_cmds:#planveyor_decomposition_*})
  collab_cmds+=(${(M)all_cmds:#planveyor_manager_collab*})
  collab_cmds+=(${(M)all_cmds:#planveyor_merge_collab*})
  collab_cmds+=(${(M)all_cmds:#planveyor_merge_apply_collab*})
  collab_cmds+=(planveyor_manager_resume)
  collab_cmds=(${(u)collab_cmds})
  collab_cmds=(${(o)collab_cmds})

  typeset -A is_process is_collab
  local c
  for c in "${process_cmds[@]}"; do is_process[$c]=1; done
  for c in "${collab_cmds[@]}"; do is_collab[$c]=1; done

  local -a manual_cmds
  manual_cmds=()
  local name
  for name in "${all_cmds[@]}"; do
    [[ -n "${name//[[:space:]]/}" ]] || continue
    [[ -n "${is_process[$name]:-}" ]] && continue
    [[ -n "${is_collab[$name]:-}" ]] && continue
    manual_cmds+=("$name")
  done


  local show_block_manual=0 show_block_collab=0 show_block_process=0
  case "$filter" in
    manual) show_block_manual=1 ;;
    collab) show_block_collab=1 ;;
    process) show_block_process=1 ;;
    all|*) show_block_manual=1; show_block_collab=1; show_block_process=1 ;;
  esac

  # The dashboards below read under the root this invocation has already
  # validated.  Re-entering guarded readers for every row would revalidate the
  # authority context through the Python bridge several times per row.
  local root="$PLANVEYOR_CTX_ROOT"

  if (( show_block_manual )); then
    echo "## Manual"
    echo ""
    echo "### Sessions (manual dashboard)"
    _planveyor_manual_sessions_table 0 "$root"
    echo ""
    echo "### Commands (core)"
    echo "planveyor_show [--all|--manual|--collab|--process] [--wide]     dashboard (show blocks)"
    echo "planveyor_help [--all|--manual|--collab|--process|<command>]    cookbook (this help)"
    echo ""
    echo "# plans"
    echo "planveyor_plan_set <PLAN_PATH>"
    echo "planveyor_plan_bundle [--print|--check|--preflight|--scope-check|--stage|--commit-ready|--commit-exact|--closeout-json|--capture-rejected|--verify-rejected|--cleanup-rejected] <PLAN_PATH>; --commit-exact --preflight-json <path|-> (--message-auto|--message-file <path>)"
    echo "planveyor_plan_closeout_preflight [--docs-closeout-json <path|->] [--json] <PLAN_PATH>"
    echo "planveyor_plan_provenance_context [HELPER_ARGS...]"
    echo "planveyor_plan_provenance_stamp <PLAN_PATH> [HELPER_ARGS...]"
    echo "planveyor_bare_entrypoints_doctor [--bin-dir DIR]"
    echo "planveyor_plan_list [--include-non-executable] [TERMS...]"
    echo "planveyor_plan_list_status <STATUS_FILTER> [--include-non-executable] [TERMS...]"
    echo ""
    echo "# roles (status-driven)"
    echo "planveyor_arch | planveyor_planner | planveyor_coder | planveyor_reviewer | planveyor_reviewer_code_risk | planveyor_reviewer_code_contracts | planveyor_manager"
    echo "planveyor_arch_init | planveyor_planner_init | planveyor_coder_init | planveyor_reviewer_init | planveyor_reviewer_code_risk_init | planveyor_reviewer_code_contracts_init | planveyor_manager_init"
    echo "planveyor_arch_resume | planveyor_planner_resume | planveyor_coder_resume | planveyor_reviewer_resume | planveyor_reviewer_code_risk_resume | planveyor_reviewer_code_contracts_resume | planveyor_manager_resume"
    echo ""
    echo "# sessions / runners"
    echo "planveyor_session <key>"
    echo "planveyor_session_set <key> <SID> [META]"
    echo "planveyor_runner <role>"
    echo "planveyor_runner_set <role> <runner>"
    echo "planveyor_runner_clear <role>"
    echo "planveyor_runner_matrix [ROLES...]"
    echo "planveyor_role_runner_preflight <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> [--json]"
    echo "planveyor_custom_role_step <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> --plan <PLAN_PATH> [--timeout SECONDS] --json"
    echo "planveyor_role_run <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> [--timeout SECONDS] [--json]"
    echo "planveyor_role_run_receipt_check <receipt.json> [--run-id ID] [--session-key KEY] [--target-plan PLAN] [--pre-status STATUS] [--json]"
    echo "planveyor_profile <architect|coder|planner> [main|censor]"
    echo "planveyor_profile_set <architect|coder|planner> <PROFILE> [main|censor]"
    echo "planveyor_profile_clear <architect|coder|planner> [main|censor]"
    echo ""
    echo "# docs/hygiene"
    echo "planveyor_doc_lint  # strict canonical pass"
    echo "planveyor_docs_hygiene_list [BASE..HEAD|BASE HEAD]  # optional inventory helper"
    echo "planveyor_docs_hygiene_suggest              # report-only cleanup handoff"
    echo "planveyor_docs_hygiene_archive --range BASE..HEAD [--apply]  # manual rerun / вне pipeline"
    echo "planveyor_shared_docs_mirror_drift [--target-root PATH] [--json]  # exact shared-docs mirror guard"
    echo "planveyor_mirror_strict_gate [--target-root PATH] [--json]  # fail-closed shared-docs mirror gate"
    echo "planveyor_followups_triage [--all] | [--file docs/followups/<inbox>.md] | [--range BASE..HEAD|BASE HEAD] [--dry-run|--apply]"
    echo "planveyor_code_draft_stub_from_plan [PLAN_PATH] [--role Planner|Coder|Architect]"
    echo ""
    echo "# review/merge"
    echo "planveyor_range_set <BASE_SHA> <HEAD_SHA> [MERGE_SHA]"
    echo "planveyor_range_set_merge <MERGE_SHA> [HEAD_SHA]"
    echo "planveyor_merge_init | planveyor_merge_tracker_init | planveyor_merge_tracker_ensure | planveyor_merge_tracker_show | planveyor_merge_next | planveyor_post_merge_packetization_gate | planveyor_post_merge_packetization_gate_recover | planveyor_post_merge_receipt_skeleton | planveyor_post_merge_receipt_preflight | planveyor_post_merge_docs_finalize_tick | planveyor_post_merge_operational_receipt | planveyor_post_merge_docs_hygiene_suggest_gate | planveyor_merge_bundle_report | planveyor_post_merge_ready_to_push_closeout | planveyor_merge_range_verdict_digest"
    echo "planveyor_merge_range_stats_json [BASE..HEAD | BASE HEAD]"
    echo "planveyor_review_range_start [EXCLUDE_DOCS=1|0] | planveyor_review_range_start <BASE_SHA> <HEAD_SHA> [EXCLUDE_DOCS=1|0]"
    echo ""
    echo "# services"
    echo ""
    echo "### Commands (full catalog; auto, grouped)"
    local -a sec_sessions sec_plans sec_roles sec_docs sec_dev sec_services sec_misc
    sec_sessions=(); sec_plans=(); sec_roles=(); sec_docs=(); sec_dev=(); sec_services=(); sec_misc=()
    local m
    for m in "${manual_cmds[@]}"; do
      case "$m" in
        planveyor_session*|planveyor_sessions_*|planveyor_runner*|planveyor_pybin*)
          sec_sessions+=("$m")
          ;;
        planveyor_arch*|planveyor_planner*|planveyor_coder*|planveyor_reviewer*|planveyor_manager*)
          sec_roles+=("$m")
          ;;
        planveyor_plan*|planveyor_range*|planveyor_status_line)
          sec_plans+=("$m")
          ;;
        planveyor_doc*|planveyor_docs_*|planveyor_shared_docs_*|planveyor_followups*|planveyor_code_draft*|planveyor_merge_*|planveyor_post_merge_packetization_gate|planveyor_post_merge_packetization_gate_recover|planveyor_post_merge_receipt_skeleton|planveyor_post_merge_receipt_preflight|planveyor_post_merge_docs_finalize_tick|planveyor_post_merge_operational_receipt|planveyor_post_merge_docs_hygiene_suggest_gate|planveyor_review_*|planveyor_owner_answers_*|planveyor_clear_owner_answers)
          sec_docs+=("$m")
          ;;
        planveyor_limit*|planveyor_seed*|planveyor_dev_*)
          sec_dev+=("$m")
          ;;
        planveyor_services*)
          sec_services+=("$m")
          ;;
        *)
          sec_misc+=("$m")
          ;;
      esac
    done
    sec_sessions=(${(o)sec_sessions})
    sec_plans=(${(o)sec_plans})
    sec_roles=(${(o)sec_roles})
    sec_docs=(${(o)sec_docs})
    sec_dev=(${(o)sec_dev})
    sec_services=(${(o)sec_services})
    sec_misc=(${(o)sec_misc})

    echo ""
    _planveyor_help_print_catalog_table "Sessions" "${sec_sessions[@]}"
    echo ""
    _planveyor_help_print_catalog_table "Plans" "${sec_plans[@]}"
    echo ""
    _planveyor_help_print_catalog_table "Roles" "${sec_roles[@]}"
    echo ""
    _planveyor_help_print_catalog_table "Docs/Hygiene" "${sec_docs[@]}"
    echo ""
    _planveyor_help_print_catalog_table "Dev/Limits" "${sec_dev[@]}"
    echo ""
    _planveyor_help_print_catalog_table "Services/Server" "${sec_services[@]}"
    if (( ${#sec_misc[@]} > 0 )); then
      echo ""
      _planveyor_help_print_catalog_table "Misc" "${sec_misc[@]}"
    fi
    (( show_block_collab || show_block_process )) && echo ""
  fi

  if (( show_block_collab )); then
    echo "## Collab"
    echo ""
    echo "### Sessions (collab agents)"
    _planveyor_collab_sessions_table 0 "$root"
    echo ""
    echo "### Commands"
    echo "planveyor_show --collab [--wide]                 show collab block"
    echo "planveyor_help --collab                          show collab cookbook block"
    echo "planveyor_show_collab [--wide|--compact]         show collab agents table"
    echo "planveyor_merge_collab_tui [--no-alt-screen]     start merge-mode pipeline in TUI"
    echo "planveyor_merge_collab_cmd [--range ...]         one-shot merge-mode pipeline"
    echo "planveyor_merge_apply_collab_tui --from ...      merge+resolve+commit(no-push) and run review"
    echo "planveyor_merge_apply_collab_cmd --from ...      one-shot merge+resolve+commit(no-push)"
    echo "planveyor_decomposition_init [PLAN_PATH]         bootstrap decomposition seed/scaffold and ensure Manager"
    echo "planveyor_decomposition_seed_promote <NEW_PLAN_PATH> [OLD_PLAN_PATH]   rename auto-seed after Architect intake"
    echo "planveyor_decomposition_collab [PLAN_PATH]       one-shot decomposition wave bootstrap via Manager collab"
    echo "planveyor_decomposition_collab_tui [PLAN_PATH] [--no-alt-screen]   decomposition wave bootstrap in Manager TUI"
    echo "planveyor_manager_collab                         run Manager collab (one-shot)"
    echo "planveyor_q_set <PLAN_PATH...>|--status ...|--from-umbrella <PLAN> --for-manager-mode <MODE>   materialize mode-filtered queue state"
    echo "planveyor_q_append [--json] <PLAN_PATH...> --for-manager-mode <MODE>       append mode-filtered explicit plans"
    echo "planveyor_q_show                                inspect queue state"
    echo "planveyor_planqueue_metrics                     generate queue health scorecard from .planveyor.planqueue.{log,json}"
    echo "planveyor_planning_wave_readback                inspect planning-wave buckets/preview/provenance/routes"
    echo "planveyor_wave_telemetry_report                 inspect per-wave telemetry/retrieval corpus; unknown cost stays unknown"
    echo "planveyor_docs_closeout <PLAN_PATH> [--followups-capture-cycle-id <UUIDv4>] [--json]    inspect scoped docs-closeout ownership/final commit proof"
    echo "planveyor_q_small_slice <PLAN_PATH>             inspect reduced-conveyor small-slice eligibility"
    echo "planveyor_q_next_json --manager-mode <MODE> | planveyor_q_small_slice_json <PLAN_PATH> | planveyor_q_advance_json <Done|Superseded> --manager-mode <MODE>"
    echo "planveyor_q_closeout_json --manager-mode <manager-collab|manager-custom-pipeline> | planveyor_q_stop_json <REASON> [--source-plan <PLAN_PATH>] | planveyor_q_planpath_override_json <PLAN_PATH> [REASON]"
    echo "planveyor_q_clear                               clear queue state"
    echo "planveyor_manager_collab_tui [--q] [--no-alt-screen] [--merge [--range ...]]   run Manager collab in TUI / queue / merge-mode"
    echo "planveyor_manager_collab_cmd <CMD>               one-shot MANAGER_CMD=... ('run Q' = queue mode)"
    echo "planveyor_manager_custom_pipeline_cmd <CMD>      one-shot custom MANAGER_CMD=... ('run Q' = queue mode)"
    echo "planveyor_manager_resume                         resume Manager session"
    echo ""
    echo "### Commands (full catalog; auto)"
    _planveyor_help_print_catalog_table "Catalog (collab)" "${collab_cmds[@]}"
    (( show_block_process )) && echo ""
  fi

  if (( show_block_process )); then
    echo "## Process tracks (Architect)"
    echo ""
    echo "### Sessions (architect tracks)"
    _planveyor_process_sessions_table 0 "$root"
    echo ""
    echo "### Commands"
    echo "planveyor_show --process [--wide]                show process block"
    echo "planveyor_show_process [--wide]                  show tracks table"
    echo "planveyor_ai_gate --range BASE..HEAD --policy docs/tools/ai_gate_policy.example.json   run pre-merge AI gate"
    echo "planveyor_ai_gate_smoke --receipt-path .tmp/planveyor_ai_gate_smoke.json   deterministic wrapper smoke"
    echo "planveyor_arch_roles_resume                      resume/start roles track TUI"
    echo "planveyor_arch_collab_resume                     resume/start collab track TUI"
    echo "planveyor_arch_inno_resume                       resume/start innovations track TUI"
    echo "planveyor_arch_merge_notes_start                 start merge notes track"
    echo "planveyor_arch_plan_harvest_start                start plan harvest track"
    echo "planveyor_arch_post_merge_audit_start            start post-merge audit track"
    echo "planveyor_arch_canon_sweep_start                 start canon sweep track"
    echo "  (deprecated: planveyor_arch_process_roles_tui | planveyor_arch_process_collab_tui | planveyor_arch_innovations_tui)"
    echo ""
    echo "### Commands (full catalog; auto)"
    _planveyor_help_print_catalog_table "Catalog (process)" "${process_cmds[@]}"
  fi
}

planveyor_plan_list() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_list)" || return $?
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
  # Usage:
  #   planveyor_plan_list                # list all non-Done + non-Superseded plans
  #   planveyor_plan_list --include-non-executable
  #   planveyor_plan_list auth deploy    # filter by substrings (case-insensitive) in filename/path (OR: any term matches)
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local include_non_executable=0
  local -a terms
  terms=()
  local arg=""
  for arg in "$@"; do
    case "$arg" in
      --include-non-executable)
        include_non_executable=1
        ;;
      --help|-h)
        echo "Usage: planveyor_plan_list [--include-non-executable] [TERMS...]"
        return 0
        ;;
      *)
        terms+=("$arg")
        ;;
    esac
  done

  pushd "$root" >/dev/null || return 1

  local -a files
  files=("${(@f)$(rg --files docs/plans 2>/dev/null | rg '\.md$' | rg -v '^docs/plans/_template\.md$' | rg -v '^docs/plans/README\.md$' || true)}")
  files=("${(@)files:#}")

  local f
  for f in "${files[@]}"; do
    [[ -n "${f//[[:space:]]/}" ]] || continue
    # Optional filter by substrings (case-insensitive) on filename/path.
    if (( ${#terms} > 0 )); then
      local ok=0
      local f_l="${f:l}"
      local filter_term=""
      for filter_term in "${terms[@]}"; do
        local t_l="${filter_term:l}"
        [[ -n "${t_l//[[:space:]]/}" ]] || continue
        if [[ "$f_l" == *"$t_l"* ]]; then
          ok=1
          break
        fi
      done
      (( ok )) || continue
    fi

    local status_line=""
    status_line="$(_planveyor_plan_status_line_lenient "$f" 2>/dev/null || true)"
    local status_value=""
    status_value="$(_planveyor_extract_status_value "$status_line" 2>/dev/null || true)"
    status_value="${status_value#"${status_value%%[![:space:]]*}"}"
    status_value="${status_value%"${status_value##*[![:space:]]}"}"

    if [[ -z "${status_value//[[:space:]]/}" ]]; then
      continue
    fi
    local status_l="${status_value:l}"
    if [[ "$status_l" == done* || "$status_l" == superseded* ]]; then
      continue
    fi

    local runtime_class="executable"
    local queue_closeout_kind="not_ready"
    local queue_closeout_ready="false"
    local oracle_summary=""
    oracle_summary="$(_planveyor_plan_oracle_summary "$f" 2>/dev/null || true)"
    if [[ -n "${oracle_summary//[[:space:]]/}" && "$oracle_summary" == *$'\t'* ]]; then
      runtime_class="${oracle_summary%%$'\t'*}"
      local oracle_rest="${oracle_summary#*$'\t'}"
      queue_closeout_kind="${oracle_rest%%$'\t'*}"
      queue_closeout_ready="${oracle_rest#*$'\t'}"
    fi
    if [[ "$queue_closeout_kind" == "non_executable_ready" && "$include_non_executable" != "1" ]]; then
      continue
    fi

    local runner=""
    runner="$(_planveyor_suggest_runner_from_status "$status_value")"
    local status_display="$status_value"
    if [[ "$queue_closeout_kind" == "non_executable_ready" && "$runtime_class" != "executable" ]]; then
      status_display="${status_value} [${runtime_class}]"
      runner="(Owner)"
    fi
    printf '%s\t%s | planveyor_plan_set "%s" | %s\n' "$status_display" "$f" "$f" "$runner"
  done | sort -f

  popd >/dev/null || return 1
}

planveyor_plan_list_status() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_list_status)" || return $?
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
  # Usage:
  #   planveyor_plan_list_status done                 # list all Done plans
  #   planveyor_plan_list_status done upgrade notice  # list Done plans filtered by substrings (case-insensitive; OR)
  #   planveyor_plan_list_status "ready for planner"  # list any status by (case-insensitive) substring match
  #   planveyor_plan_list_status "ready for planner" --include-non-executable
  local root=""
  root="$(_planveyor_project_root)" || return $?

  local status_filter="${1:-}"
  [[ -n "${status_filter//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_plan_list_status <STATUS_FILTER> [--include-non-executable] [TERMS...]" >&2
    return 1
  }
  shift || true

  local status_filter_l="${status_filter:l}"
  status_filter_l="${status_filter_l#"${status_filter_l%%[![:space:]]*}"}"
  status_filter_l="${status_filter_l%"${status_filter_l##*[![:space:]]}"}"

  local include_non_executable=0
  local -a terms
  terms=()
  local arg=""
  for arg in "$@"; do
    case "$arg" in
      --include-non-executable)
        include_non_executable=1
        ;;
      --help|-h)
        echo "Usage: planveyor_plan_list_status <STATUS_FILTER> [--include-non-executable] [TERMS...]"
        return 0
        ;;
      *)
        terms+=("$arg")
        ;;
    esac
  done

  pushd "$root" >/dev/null || return 1

  local -a files
  files=("${(@f)$(rg --files docs/plans 2>/dev/null | rg '\.md$' | rg -v '^docs/plans/_template\.md$' | rg -v '^docs/plans/README\.md$' || true)}")
  files=("${(@)files:#}")

  local f
  for f in "${files[@]}"; do
    [[ -n "${f//[[:space:]]/}" ]] || continue

    # Optional filter by substrings (case-insensitive) on filename/path.
    if (( ${#terms} > 0 )); then
      local ok=0
      local f_l="${f:l}"
      local filter_term=""
      for filter_term in "${terms[@]}"; do
        local t_l="${filter_term:l}"
        [[ -n "${t_l//[[:space:]]/}" ]] || continue
        if [[ "$f_l" == *"$t_l"* ]]; then
          ok=1
          break
        fi
      done
      (( ok )) || continue
    fi

    local status_line=""
    status_line="$(_planveyor_plan_status_line_lenient "$f" 2>/dev/null || true)"
    local status_value=""
    status_value="$(_planveyor_extract_status_value "$status_line" 2>/dev/null || true)"
    status_value="${status_value#"${status_value%%[![:space:]]*}"}"
    status_value="${status_value%"${status_value##*[![:space:]]}"}"
    [[ -n "${status_value//[[:space:]]/}" ]] || continue

    local status_l="${status_value:l}"
    if [[ "$status_l" != *"$status_filter_l"* ]]; then
      continue
    fi

    local runtime_class="executable"
    local queue_closeout_kind="not_ready"
    local queue_closeout_ready="false"
    local oracle_summary=""
    oracle_summary="$(_planveyor_plan_oracle_summary "$f" 2>/dev/null || true)"
    if [[ -n "${oracle_summary//[[:space:]]/}" && "$oracle_summary" == *$'\t'* ]]; then
      runtime_class="${oracle_summary%%$'\t'*}"
      local oracle_rest="${oracle_summary#*$'\t'}"
      queue_closeout_kind="${oracle_rest%%$'\t'*}"
      queue_closeout_ready="${oracle_rest#*$'\t'}"
    fi
    if [[ "$queue_closeout_kind" == "non_executable_ready" && "$include_non_executable" != "1" ]]; then
      continue
    fi

    local runner=""
    runner="$(_planveyor_suggest_runner_from_status "$status_value")"
    local status_display="$status_value"
    if [[ "$queue_closeout_kind" == "non_executable_ready" && "$runtime_class" != "executable" ]]; then
      status_display="${status_value} [${runtime_class}]"
      runner="(Owner)"
    fi
    printf '%s\t%s | planveyor_plan_set "%s" | %s\n' "$status_display" "$f" "$f" "$runner"
  done | sort -f

  popd >/dev/null || return 1
}

planveyor_clear_owner_answers() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_clear_owner_answers)" || return $?
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
  local file_path="$root/.planveyor.owner_answers"
  if [[ -f "$file_path" ]]; then
    rm -f "$file_path" 2>/dev/null || true
    echo "Cleared: ${file_path}" >&2
  else
    echo "No pending Owner answers: ${file_path}" >&2
  fi
}

planveyor_bare_entrypoints_install() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_bare_entrypoints_install)" || return $?
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
  local target_dir=""
  local -a managed_cmds
  managed_cmds=("${(@f)$(_planveyor_bare_entrypoints_managed_commands)}")
  while (( $# > 0 )); do
    case "${1:-}" in
      --bin-dir)
        shift || true
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_bare_entrypoints_install [--bin-dir DIR]" >&2
          return 1
        }
        target_dir="${1:-}"
        ;;
      --help|-h)
        echo "Usage: planveyor_bare_entrypoints_install [--bin-dir DIR]" >&2
        echo "Default target priority: --bin-dir -> PLANVEYOR_BARE_BIN_DIR -> first writable stable PATH dir." >&2
        local summary_line=""
        for summary_line in "${(@f)$(_planveyor_bare_entrypoints_summary_lines)}"; do
          echo "$summary_line" >&2
        done
        return 0
        ;;
      *)
        echo "Usage: planveyor_bare_entrypoints_install [--bin-dir DIR]" >&2
        return 1
        ;;
    esac
    shift || true
  done

  local explicit_target=0
  if [[ -z "${target_dir//[[:space:]]/}" && -n "${PLANVEYOR_BARE_BIN_DIR:-}" ]]; then
    target_dir="${PLANVEYOR_BARE_BIN_DIR}"
  fi
  [[ -n "${target_dir//[[:space:]]/}" ]] && explicit_target=1

  local tooling_root=""
  tooling_root="$(_planveyor_root_from_loaded_script 2>/dev/null || true)"
  if [[ -z "${tooling_root//[[:space:]]/}" ]]; then
    tooling_root="$(_planveyor_root)"
    [[ "$tooling_root" == /* ]] || tooling_root="${PWD%/}/${tooling_root}"
  fi

  if (( explicit_target )); then
    [[ "$target_dir" == /* ]] || target_dir="${PWD%/}/${target_dir}"
    mkdir -p "$target_dir" 2>/dev/null || {
      echo "Cannot create install target: ${target_dir}" >&2
      echo "Fallback: $(_planveyor_bare_entrypoints_fallback_hint planveyor_plan_set)" >&2
      return 1
    }
    [[ -d "$target_dir" ]] || {
      echo "Install target is not a directory: ${target_dir}" >&2
      return 1
    }
    [[ -w "$target_dir" ]] || {
      echo "Install target is not writable: ${target_dir}" >&2
      echo "Fallback: $(_planveyor_bare_entrypoints_fallback_hint planveyor_plan_set)" >&2
      return 1
    }
  else
    local -A seen_dirs
    local -a stable_seen stable_rejected
    stable_seen=()
    stable_rejected=()
    local path_dir=""
    for path_dir in "${path[@]}"; do
      [[ -n "${path_dir//[[:space:]]/}" && -z "${seen_dirs[$path_dir]:-}" ]] || continue
      seen_dirs[$path_dir]=1
      _planveyor_bare_entrypoints_is_stable_autodetect_dir "$path_dir" || continue
      stable_seen+=("$path_dir")
      [[ -d "$path_dir" ]] || continue
      if [[ -w "$path_dir" ]]; then
        target_dir="$path_dir"
        break
      fi
      stable_rejected+=("$path_dir")
    done

    if [[ -z "${target_dir//[[:space:]]/}" ]]; then
      echo "No writable stable PATH target found for bare planveyor entrypoints." >&2
      if (( ${#stable_seen[@]} > 0 )); then
        echo "Stable PATH dirs seen: ${stable_seen[*]}" >&2
      fi
      if (( ${#stable_rejected[@]} > 0 )); then
        echo "Rejected (not writable): ${stable_rejected[*]}" >&2
      fi
      echo "Use --bin-dir DIR or PLANVEYOR_BARE_BIN_DIR to choose a target explicitly." >&2
      echo "Fallback: $(_planveyor_bare_entrypoints_fallback_hint planveyor_plan_set)" >&2
      return 1
    fi
  fi

  local shim_cmd=""
  for shim_cmd in "${managed_cmds[@]}"; do
    _planveyor_bare_entrypoints_write_shim "${target_dir}/${shim_cmd}" "$shim_cmd" "$tooling_root" || {
      echo "Failed to install shim: ${target_dir}/${shim_cmd}" >&2
      return 1
    }
  done

  echo "Installed bare planveyor entrypoints to: ${target_dir}" >&2
  local summary_line=""
  for summary_line in "${(@f)$(_planveyor_bare_entrypoints_summary_lines)}"; do
    echo "$summary_line" >&2
  done
  if [[ ":${PATH}:" != *":${target_dir}:"* ]]; then
    echo "Note: ${target_dir} is not in PATH for this shell; add it explicitly before testing bare commands." >&2
  fi
}

_planveyor_bare_entrypoints_is_managed_shim() {
  local shim_cmd="${1:-}"
  local shim_path="${2:-}"
  [[ -n "${shim_cmd//[[:space:]]/}" && -n "${shim_path//[[:space:]]/}" && -f "$shim_path" && -r "$shim_path" ]] || return 1

  local shim_line=""
  local expected_line=""
  local actual_metadata_count=0
  local expected_metadata_count=0
  local -a actual_contract_lines expected_contract_lines
  actual_contract_lines=()
  expected_contract_lines=()

  while IFS= read -r shim_line || [[ -n "$shim_line" ]]; do
    if [[ "$shim_line" == "# installer_tooling_root="* ]]; then
      actual_metadata_count=$((actual_metadata_count + 1))
      continue
    fi
    actual_contract_lines+=("$shim_line")
  done < "$shim_path"
  (( actual_metadata_count == 1 )) || return 1

  while IFS= read -r expected_line || [[ -n "$expected_line" ]]; do
    if [[ "$expected_line" == "# installer_tooling_root="* ]]; then
      expected_metadata_count=$((expected_metadata_count + 1))
      continue
    fi
    expected_contract_lines+=("$expected_line")
  done < <(_planveyor_bare_entrypoints_render_shim "$shim_cmd" "/")
  (( expected_metadata_count == 1 )) || return 1

  [[ "${(j:\n:)actual_contract_lines}" == "${(j:\n:)expected_contract_lines}" ]]
}

_planveyor_bare_entrypoints_doctor_provenance_line() {
  local shim_cmd="${1:-}"
  local shim_path="${2:-}"
  local target_dir="${3:-}"
  [[ -n "${shim_cmd//[[:space:]]/}" && -n "${shim_path//[[:space:]]/}" && -n "${target_dir//[[:space:]]/}" ]] || return 1

  local shim_state="missing"
  local resolved_tooling_root="N/A"
  local provenance_state="missing_root"
  if [[ ! -e "$shim_path" ]]; then
    shim_state="missing"
  elif [[ ! -f "$shim_path" || ! -r "$shim_path" ]]; then
    shim_state="unreadable"
    provenance_state="unreadable"
  elif [[ ! -x "$shim_path" ]]; then
    shim_state="non-executable"
    provenance_state="unreadable"
  else
    if _planveyor_bare_entrypoints_is_managed_shim "$shim_cmd" "$shim_path"; then
      shim_state="installed"
      if [[ -n "${PLANVEYOR_ROOT:-}" ]]; then
        resolved_tooling_root="${PLANVEYOR_ROOT}"
        if [[ -r "${resolved_tooling_root%/}/scripts/planveyor.zsh" ]]; then
          provenance_state="runtime_override"
        elif [[ -e "${resolved_tooling_root%/}" ]]; then
          provenance_state="unreadable"
        else
          provenance_state="missing_root"
        fi
      else
        resolved_tooling_root="${HOME}/planveyor"
        if [[ -r "${resolved_tooling_root%/}/scripts/planveyor.zsh" ]]; then
          provenance_state="stable_default"
        elif [[ -e "${resolved_tooling_root%/}" ]]; then
          provenance_state="unreadable"
        else
          provenance_state="missing_root"
        fi
      fi
    else
      local shim_line=""
      local legacy_root=""
      while IFS= read -r shim_line || [[ -n "$shim_line" ]]; do
        case "$shim_line" in
          baked_tooling_root=*)
            legacy_root="${shim_line#baked_tooling_root=}"
            legacy_root="${legacy_root#\'}"
            legacy_root="${legacy_root%\'}"
            break
            ;;
        esac
      done < "$shim_path"
      if [[ -n "${legacy_root//[[:space:]]/}" ]]; then
        shim_state="installed"
        resolved_tooling_root="$legacy_root"
        provenance_state="legacy_baked_ephemeral"
      else
        shim_state="unmanaged"
        provenance_state="unreadable"
      fi
    fi
  fi

  print -r -- "  provenance ${shim_cmd}: shim_state=${shim_state}; resolved_tooling_root=${resolved_tooling_root}; provenance_state=${provenance_state}; repair_state=not_available_from_facade"
}

planveyor_bare_entrypoints_doctor() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_bare_entrypoints_doctor)" || return $?
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
  local target_dir=""
  local target_source="PATH auto"
  local -a managed_cmds stable_seen stable_rejected
  managed_cmds=("${(@f)$(_planveyor_bare_entrypoints_managed_commands)}")
  stable_seen=()
  stable_rejected=()

  while (( $# > 0 )); do
    case "${1:-}" in
      --bin-dir)
        shift || true
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_bare_entrypoints_doctor [--bin-dir DIR]" >&2
          return 1
        }
        target_dir="${1:-}"
        target_source="--bin-dir"
        ;;
      --help|-h)
        echo "Usage: planveyor_bare_entrypoints_doctor [--bin-dir DIR]" >&2
        echo "Shows install target selection, on-disk shim presence, and fresh /bin/zsh -c visibility." >&2
        return 0
        ;;
      *)
        echo "Usage: planveyor_bare_entrypoints_doctor [--bin-dir DIR]" >&2
        return 1
        ;;
    esac
    shift || true
  done

  if [[ -z "${target_dir//[[:space:]]/}" && -n "${PLANVEYOR_BARE_BIN_DIR:-}" ]]; then
    target_dir="${PLANVEYOR_BARE_BIN_DIR}"
    target_source="PLANVEYOR_BARE_BIN_DIR"
  fi

  if [[ -n "${target_dir//[[:space:]]/}" ]]; then
    [[ "$target_dir" == /* ]] || target_dir="${PWD%/}/${target_dir}"
  else
    local -A seen_dirs
    local path_dir=""
    for path_dir in "${path[@]}"; do
      [[ -n "${path_dir//[[:space:]]/}" && -z "${seen_dirs[$path_dir]:-}" ]] || continue
      seen_dirs[$path_dir]=1
      _planveyor_bare_entrypoints_is_stable_autodetect_dir "$path_dir" || continue
      stable_seen+=("$path_dir")
      [[ -d "$path_dir" ]] || continue
      if [[ -w "$path_dir" ]]; then
        target_dir="$path_dir"
        break
      fi
      stable_rejected+=("$path_dir")
    done
  fi

  local target_in_path="no"
  if [[ -n "${target_dir//[[:space:]]/}" && ":${PATH}:" == *":${target_dir}:"* ]]; then
    target_in_path="yes"
  fi

  print -r -- "Bare entrypoints doctor"
  print -r -- "Target source: ${target_source}"
  if [[ -n "${target_dir//[[:space:]]/}" ]]; then
    print -r -- "Target dir: ${target_dir}"
  else
    print -r -- "Target dir: (none resolved)"
  fi
  print -r -- "Target dir in PATH: ${target_in_path}"

  if [[ -z "${target_dir//[[:space:]]/}" ]]; then
    if (( ${#stable_seen[@]} > 0 )); then
      print -r -- "Stable PATH dirs seen: ${stable_seen[*]}"
    fi
    if (( ${#stable_rejected[@]} > 0 )); then
      print -r -- "Stable PATH dirs rejected (not writable): ${stable_rejected[*]}"
    fi
    print -r -- "Hint: use --bin-dir DIR or PLANVEYOR_BARE_BIN_DIR to inspect a specific target."
  fi

  print -r -- ""
  print -r -- "Target dir shims:"
  if [[ -z "${target_dir//[[:space:]]/}" ]]; then
    print -r -- "  unresolved"
  elif [[ ! -d "$target_dir" ]]; then
    print -r -- "  target dir does not exist"
  else
    local shim_cmd=""
    local shim_path=""
    for shim_cmd in "${managed_cmds[@]}"; do
      shim_path="${target_dir}/${shim_cmd}"
      if [[ -x "$shim_path" ]]; then
        print -r -- "  installed ${shim_cmd} -> ${shim_path}"
      elif [[ -e "$shim_path" ]]; then
        print -r -- "  non-exec  ${shim_cmd} -> ${shim_path}"
      else
        print -r -- "  missing   ${shim_cmd}"
      fi
      _planveyor_bare_entrypoints_doctor_provenance_line "$shim_cmd" "$shim_path" "$target_dir" || return 1
    done
  fi

  print -r -- ""
  print -r -- "Fresh /bin/zsh -c visibility (current PATH):"
  local resolved=""
  local mismatch_count=0
  local expected_path=""
  local shim_cmd=""
  for shim_cmd in "${managed_cmds[@]}"; do
    resolved="$(PATH="$PATH" /bin/zsh -c 'command -v -- "$1" 2>/dev/null' _ "$shim_cmd" 2>/dev/null || true)"
    resolved="${resolved//$'\r'/}"
    resolved="${resolved#"${resolved%%[![:space:]]*}"}"
    resolved="${resolved%"${resolved##*[![:space:]]}"}"
    if [[ -n "${resolved//[[:space:]]/}" ]]; then
      expected_path="${target_dir%/}/${shim_cmd}"
      if [[ -n "${target_dir//[[:space:]]/}" && "$resolved" != "$expected_path" ]]; then
        mismatch_count=$((mismatch_count + 1))
        print -r -- "  visible*  ${shim_cmd} -> ${resolved} (target ${expected_path})"
      else
        print -r -- "  visible   ${shim_cmd} -> ${resolved}"
      fi
    else
      print -r -- "  hidden    ${shim_cmd}"
    fi
  done

  if (( mismatch_count > 0 )); then
    print -r -- ""
    print -r -- "Note: visible* means fresh /bin/zsh -c resolves a different path than the selected target dir."
  fi
  if [[ -n "${target_dir//[[:space:]]/}" && "$target_in_path" != "yes" ]]; then
    print -r -- ""
    print -r -- "Hint: prepend ${target_dir} to PATH before testing bare commands in a fresh shell."
  fi
}

planveyor_plan_set() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_set)" || return $?
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
  local plan_path="$1"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_plan_set <PLAN_PATH>" >&2
    return 1
  }

  local root="$(_planveyor_project_root)" || return $?
  local now="$(_planveyor_now)"

  local file_path="$root/.planveyor.planpath"
  local log_path="$root/.planveyor.planpath.log"
  local last_logged_plan=""
  if [[ -f "$log_path" ]]; then
    last_logged_plan="$(
      tail -n 1 "$log_path" 2>/dev/null \
        | awk -F '\t' 'NF >= 2 { print $2 }'
    )"
  fi

  printf "# %s\n%s\n" "$now" "$plan_path" > "$file_path"
  if [[ "$last_logged_plan" != "$plan_path" ]]; then
    printf "%s\t%s\n" "$now" "$plan_path" >> "$log_path"
  fi
  echo "Saved: ${file_path} (${now})" >&2

  local resolved="$plan_path"
  [[ "$resolved" == /* ]] || resolved="$root/$resolved"
  if [[ ! -f "$resolved" ]]; then
    echo "⚠️ Plan not found: ${plan_path} (ok if not created yet)" >&2
  fi
}

_planveyor_plan_queue() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_plan_queue)" || return $?
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
  local helper="$(_planveyor_script plan_queue.py)"
  [[ -f "$helper" ]] || {
    echo "Missing helper: ${helper}" >&2
    return 1
  }
  local root=""
  root="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$helper" --project-root "$root" "$@"
}

planveyor_q_set() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_q_set)" || return $?
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
  [[ $# -gt 0 ]] || {
    echo "Usage: planveyor_q_set <PLAN_PATH...>|--status <STATUS...>|--from-umbrella <PLAN_PATH> [--resume-parent <none|owner-restamp-required|run-parent-once>] --for-manager-mode <manager-collab|manager-custom-pipeline>" >&2
    return 1
  }
  _planveyor_plan_queue set "$@"
}

planveyor_q_show() {
  _planveyor_plan_queue show "$@"
}

planveyor_q_append() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_q_append)" || return $?
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
  [[ $# -gt 0 ]] || {
    echo "Usage: planveyor_q_append <PLAN_PATH...> --for-manager-mode <manager-collab|manager-custom-pipeline> [--json]" >&2
    return 1
  }
  _planveyor_plan_queue append "$@"
}

planveyor_q_history() {
  _planveyor_plan_queue history "$@"
}

_planveyor_planqueue_metrics() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_planqueue_metrics)" || return $?
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
  local helper="$(_planveyor_script planqueue_metrics.py)"
  [[ -f "$helper" ]] || {
    echo "Missing helper: ${helper}" >&2
    return 1
  }
  local root=""
  root="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$helper" --root "$root" "$@"
}

planveyor_planqueue_metrics() {
  _planveyor_planqueue_metrics "$@"
}

planveyor_planqueue_metrics_json() {
  _planveyor_planqueue_metrics --json "$@"
}

_planveyor_planning_wave_readback() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_planning_wave_readback)" || return $?
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
  local helper="$(_planveyor_script planning_wave_readback.py)"
  [[ -f "$helper" ]] || {
    echo "Missing helper: ${helper}" >&2
    return 1
  }
  local root=""
  root="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$helper" --root "$root" "$@"
}

planveyor_planning_wave_readback() {
  _planveyor_planning_wave_readback "$@"
}

planveyor_planning_wave_readback_json() {
  _planveyor_planning_wave_readback --json "$@"
}

_planveyor_wave_telemetry_report() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_wave_telemetry_report)" || return $?
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
  local helper="$(_planveyor_script wave_telemetry_report.py)"
  [[ -f "$helper" ]] || {
    echo "Missing helper: ${helper}" >&2
    return 1
  }
  local root=""
  root="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$helper" --root "$root" "$@"
}

planveyor_wave_telemetry_report() {
  _planveyor_wave_telemetry_report "$@"
}

planveyor_wave_telemetry_report_json() {
  _planveyor_wave_telemetry_report --json "$@"
}

planveyor_q_final_report() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_q_final_report)" || return $?
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
  local helper="$(_planveyor_script queue_finalizer_report.py)"
  [[ -f "$helper" ]] || {
    echo "Missing helper: ${helper}" >&2
    return 1
  }
  local root=""
  root="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$helper" --repo-root "$root" "$@"
}

planveyor_followups_capture() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_followups_capture)" || return $?
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
  local helper="$(_planveyor_script followups_capture.py)"
  [[ -f "$helper" ]] || {
    echo "Missing helper: ${helper}" >&2
    return 1
  }
  local root=""
  root="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$helper" "$1" --project-root "$root" "${@:2}"
}

planveyor_docs_closeout() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_closeout)" || return $?
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
  local plan_path="${1:-}"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_docs_closeout <PLAN_PATH> [--followups-capture-cycle-id <UUIDv4>] [--json]" >&2
    return 1
  }
  shift || true

  local closeout_tooling_root=""
  closeout_tooling_root="$(_planveyor_closeout_tooling_root 2>/dev/null || true)"
  [[ -n "${closeout_tooling_root//[[:space:]]/}" ]] || {
    echo "Cannot resolve one complete tooling root for bundle/docs closeout" >&2
    return 1
  }
  local helper="${closeout_tooling_root}/scripts/docs_closeout.py"
  [[ -f "$helper" ]] || {
    echo "Missing helper: ${helper}" >&2
    return 1
  }

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local bundle_json
  local bundle_rc=0
  bundle_json="$(planveyor_plan_bundle --closeout-json "$plan_path" 2>&1)" || bundle_rc=$?
  if (( bundle_rc != 0 )); then
    local accepted_red_error_rc=1
    if (( bundle_rc == 2 )); then
      _planveyor_py_any - "$bundle_json" <<'PY' >/dev/null 2>&1
import json
import sys


class DuplicateKeyError(ValueError):
    pass


class NonStandardConstantError(ValueError):
    pass


def exact_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def reject_constant(value):
    raise NonStandardConstantError(value)


try:
    payload = json.loads(
        sys.argv[1],
        object_pairs_hook=exact_object,
        parse_constant=reject_constant,
    )
except (json.JSONDecodeError, DuplicateKeyError, NonStandardConstantError):
    raise SystemExit(1)

expected = {
    "schema": "planveyor_rejected_baseline_error.v1",
    "state": "blocked",
    "reason_code": "accepted_red_closeout_invalid_carrier",
}
raise SystemExit(
    0
    if isinstance(payload, dict)
    and all(payload.get(key) == value for key, value in expected.items())
    else 1
)
PY
      accepted_red_error_rc=$?
    fi
    if (( bundle_rc != 2 || accepted_red_error_rc != 0 )); then
      print -u2 -r -- "$bundle_json"
      return 1
    fi
  fi
  printf '%s\n' "$bundle_json" | _planveyor_py_any "$helper" --project-root "$root" --plan "$plan_path" --bundle-json - "$@" --repo-profile-id "$(_planveyor_repo_profile_id)" --content-profile-id "$(_planveyor_content_profile_id)"
}

planveyor_plan_closeout_preflight() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_closeout_preflight)" || return $?
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
  local plan_path=""
  local docs_closeout_json=""
  while (( $# > 0 )); do
    case "${1:-}" in
      --docs-closeout-json)
        shift
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_plan_closeout_preflight [--docs-closeout-json <path|->] [--json] <PLAN_PATH>" >&2
          return 1
        }
        docs_closeout_json="$1"
        ;;
      --json) ;;
      -*)
        echo "Usage: planveyor_plan_closeout_preflight [--docs-closeout-json <path|->] [--json] <PLAN_PATH>" >&2
        return 1
        ;;
      *)
        [[ -z "$plan_path" ]] || {
          echo "Usage: planveyor_plan_closeout_preflight [--docs-closeout-json <path|->] [--json] <PLAN_PATH>" >&2
          return 1
        }
        plan_path="$1"
        ;;
    esac
    shift
  done
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_plan_closeout_preflight [--docs-closeout-json <path|->] [--json] <PLAN_PATH>" >&2
    return 1
  }

  local root=""
  root="$(_planveyor_project_root)" || return $?
  if [[ -n "$docs_closeout_json" ]]; then
    local capture_helper="$(_planveyor_script followups_capture.py)"
    [[ -f "$capture_helper" ]] || {
      echo "Missing helper: ${capture_helper}" >&2
      return 1
    }
    _planveyor_py_any "$capture_helper" preflight --project-root "$root" --plan-ref "$plan_path" \
      --docs-closeout-json "$docs_closeout_json"
    return $?
  fi

  local bundle_json
  bundle_json="$(planveyor_plan_bundle --closeout-json "$plan_path")" || return 1

  local bundle_json_path
  bundle_json_path="$(mktemp "${TMPDIR:-/tmp}/planveyor_closeout_preflight.XXXXXX")" || return 1
  printf '%s\n' "$bundle_json" > "$bundle_json_path" || {
    rm -f "$bundle_json_path"
    return 1
  }

  _planveyor_py_any - "$root" "$bundle_json_path" <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path


root = Path(sys.argv[1]).resolve()
bundle_json_path = Path(sys.argv[2]).resolve()


def _load_payload() -> dict[str, object]:
    try:
        with bundle_json_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Invalid planveyor_plan_bundle --closeout-json payload: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(payload, dict):
        print("Invalid planveyor_plan_bundle --closeout-json payload: expected object", file=sys.stderr)
        sys.exit(1)
    return payload


def _index_lock_path(repo_root: Path) -> Path | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--git-path", "index.lock"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    raw_path = result.stdout.strip()
    if not raw_path:
        return None
    lock_path = Path(raw_path)
    if not lock_path.is_absolute():
        lock_path = repo_root / lock_path
    return lock_path.resolve()


def _probe_git_writable(repo_root_value: object) -> OrderedDict[str, object]:
    repo_root_text = str(repo_root_value or "").strip()
    result: OrderedDict[str, object] = OrderedDict(
        [
            ("repo_root", repo_root_text or None),
            ("git_writable", False),
            ("reason", ""),
            ("probe_path", None),
        ]
    )
    if not repo_root_text:
        result["reason"] = "missing_repo_root"
        return result

    repo_root = Path(repo_root_text).resolve()
    if not repo_root.is_dir():
        result["reason"] = "repo_root_missing"
        return result

    lock_path = _index_lock_path(repo_root)
    if lock_path is None:
        result["reason"] = "git_index_lock_path_unavailable"
        return result
    result["probe_path"] = str(lock_path)
    if lock_path.exists():
        result["reason"] = "index_lock_exists"
        return result

    probe_path = lock_path.parent / f".planveyor-closeout-write-probe.{os.getpid()}"
    try:
        fd = os.open(str(probe_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        probe_path.unlink()
    except OSError as exc:
        try:
            if probe_path.exists():
                probe_path.unlink()
        except OSError:
            pass
        result["reason"] = f"write_probe_failed:{exc.strerror or exc.__class__.__name__}"
        return result

    result["git_writable"] = True
    result["reason"] = "ok"
    return result


payload = _load_payload()
repo_roots = payload.get("repo_roots")
repo_payloads = [item for item in repo_roots if isinstance(item, dict)] if isinstance(repo_roots, list) else []
git_probes = [_probe_git_writable(repo_payload.get("repo_root")) for repo_payload in repo_payloads]
git_writable = bool(git_probes) and all(bool(probe.get("git_writable")) for probe in git_probes)

source_closeout_kind = str(payload.get("closeout_kind") or "needs_rerun")
semantic_ready = bool(payload.get("bundle_ok"))
semantic_verdict = "go" if semantic_ready else "blocked"
bundle_ready = semantic_ready and source_closeout_kind in {"commit_ready", "already_materialized"}
staged_exact = semantic_ready and source_closeout_kind == "commit_ready"


def _payload_has_path_problem(token: str) -> bool:
    for repo_payload in repo_payloads:
        path_problems = repo_payload.get("path_problems")
        if not isinstance(path_problems, dict):
            continue
        for problems in path_problems.values():
            if isinstance(problems, list) and token in problems:
                return True
    return False

commit_skeletons = [
    str(repo_payload.get("commit_skeleton") or "").strip()
    for repo_payload in repo_payloads
    if str(repo_payload.get("commit_skeleton") or "").strip()
]
safe_command = None
commit_ready = False
if staged_exact and git_writable and len(commit_skeletons) == 1:
    commit_ready = True
    safe_command = commit_skeletons[0]

if not semantic_ready:
    closeout_state = "needs_rerun"
    if _payload_has_path_problem("current-review-red"):
        next_owner = "Coder"
    else:
        next_owner = "Reviewer"
elif source_closeout_kind == "already_materialized":
    closeout_state = "already_materialized"
    next_owner = "Architect"
elif source_closeout_kind == "commit_ready" and commit_ready:
    closeout_state = "commit_ready"
    next_owner = "Architect"
elif source_closeout_kind == "commit_ready" and not git_writable:
    closeout_state = "closeout_blocked_git_metadata"
    next_owner = "Owner"
elif source_closeout_kind == "commit_ready":
    closeout_state = "closeout_blocked_ambiguous_command"
    next_owner = "Owner"
elif source_closeout_kind == "staged_mismatch":
    closeout_state = "staged_mismatch"
    next_owner = "Architect"
elif source_closeout_kind == "staged_empty":
    closeout_state = "needs_stage"
    next_owner = "Architect"
else:
    closeout_state = "needs_rerun"
    next_owner = "Reviewer"

result = OrderedDict(
    [
        ("plan", payload.get("plan")),
        ("semantic_ready", semantic_ready),
        ("semantic_verdict", semantic_verdict),
        ("bundle_ready", bundle_ready),
        ("staged_exact", staged_exact),
        ("git_writable", git_writable),
        ("commit_ready", commit_ready),
        ("closeout_state", closeout_state),
        ("next_owner", next_owner),
        ("safe_command", safe_command),
        ("source_closeout_kind", source_closeout_kind),
        ("source_bundle_ok", bool(payload.get("bundle_ok"))),
        ("source_errors", payload.get("errors") if isinstance(payload.get("errors"), list) else []),
        ("git_writable_probes", git_probes),
        ("source", "planveyor_plan_bundle --closeout-json"),
    ]
)

print(json.dumps(result, ensure_ascii=False, indent=2))
PY
  local py_status=$?
  rm -f "$bundle_json_path"
  return "$py_status"
}

planveyor_q_small_slice() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_q_small_slice)" || return $?
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
  local plan_path="${1:-}"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_q_small_slice <PLAN_PATH>" >&2
    return 1
  }
  shift || true
  _planveyor_plan_queue small-slice "$plan_path" "$@"
}

planveyor_q_clear() {
  _planveyor_plan_queue clear "$@"
}

planveyor_q_recover() {
  _planveyor_plan_queue recover "$@"
}

planveyor_q_next_json() {
  _planveyor_q_next_json "$@"
}

_planveyor_q_next_json() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_q_next_json)" || return $?
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
  [[ $# -gt 0 ]] || {
    echo "Usage: _planveyor_q_next_json --manager-mode <manager-collab|manager-custom-pipeline>" >&2
    return 1
  }
  _planveyor_plan_queue next --json "$@"
}

_planveyor_docs_closeout_json() {
  local plan_path="${1:-}"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: _planveyor_docs_closeout_json <PLAN_PATH>" >&2
    return 1
  }
  shift || true
  planveyor_docs_closeout "$plan_path" --json "$@"
}

_planveyor_q_small_slice_json() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_q_small_slice_json)" || return $?
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
  local plan_path="${1:-}"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: _planveyor_q_small_slice_json <PLAN_PATH>" >&2
    return 1
  }
  shift || true
  _planveyor_plan_queue small-slice "$plan_path" --json "$@"
}

planveyor_q_small_slice_json() {
  _planveyor_q_small_slice_json "$@"
}

_planveyor_q_advance_json() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_q_advance_json)" || return $?
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
  local final_status="${1:-}"
  [[ -n "${final_status//[[:space:]]/}" ]] || {
    echo "Usage: _planveyor_q_advance_json <Done|Superseded> --manager-mode <manager-collab|manager-custom-pipeline>" >&2
    return 1
  }
  shift || true
  _planveyor_plan_queue advance --final-status "$final_status" --json "$@"
}

planveyor_q_advance_json() {
  _planveyor_q_advance_json "$@"
}

_planveyor_q_closeout_json() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_q_closeout_json)" || return $?
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
  _planveyor_plan_queue closeout --json "$@"
}

planveyor_q_closeout_json() {
  _planveyor_q_closeout_json "$@"
}

_planveyor_q_stop_json() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_q_stop_json)" || return $?
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
  local reason="${1:-}"
  [[ -n "${reason//[[:space:]]/}" ]] || {
    echo "Usage: _planveyor_q_stop_json <REASON> [--source-plan <PLAN_PATH>]" >&2
    return 1
  }
  shift || true
  _planveyor_plan_queue stop --reason "$reason" --json "$@"
}

planveyor_q_stop_json() {
  _planveyor_q_stop_json "$@"
}

_planveyor_q_planpath_override_json() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_q_planpath_override_json)" || return $?
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
  local plan_path="${1:-}"
  local reason="${2:-queue_activation}"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: _planveyor_q_planpath_override_json <PLAN_PATH> [REASON]" >&2
    return 1
  }
  _planveyor_plan_queue planpath-override --plan "$plan_path" --reason "$reason" --json
}

planveyor_q_planpath_override_json() {
  _planveyor_q_planpath_override_json "$@"
}

_planveyor_q_history_json() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_q_history_json)" || return $?
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
  _planveyor_plan_queue history --json "$@"
}

planveyor_q_history_json() {
  _planveyor_q_history_json "$@"
}

_planveyor_plan_phase_overlay_state() {
  local plan_path="${1:-}"
  [[ -n "${plan_path//[[:space:]]/}" ]] || return 1
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tooling_root=""
  tooling_root="$(_planveyor_root)" || return $?
  local plan_fs="$plan_path"
  [[ "$plan_fs" == /* ]] || plan_fs="$root/$plan_fs"
  [[ -f "$plan_fs" ]] || {
    echo "Missing plan: ${plan_path}" >&2
    return 1
  }

  _planveyor_py_any_authority_stdin "$plan_fs" "${tooling_root%/}/scripts" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

plan_path = Path(sys.argv[1])
for script_dir in sys.argv[2:]:
    if script_dir and script_dir not in sys.path:
        sys.path.insert(0, script_dir)

try:
    import plan_status_oracle
except Exception as exc:
    print(f"plan_status_oracle import failed: {exc}", file=sys.stderr)
    raise SystemExit(1)

text = plan_path.read_text(encoding="utf-8")
strict = plan_status_oracle.strict_plan_meta_json(text)
if strict.state != "valid" or not isinstance(strict.plan_meta, dict):
    print(
        f"plan_meta_strict_read_failed: {plan_path}: reason_code={strict.reason_code}",
        file=sys.stderr,
    )
    raise SystemExit(1)
meta = strict.plan_meta
overlay = meta.get("phase_overlay")
state = meta.get("phase_state")
overlay_norm = overlay.strip().lower() if isinstance(overlay, str) and overlay.strip() else ""
state_norm = state.strip().lower() if isinstance(state, str) and state.strip() else ""
print(f"{overlay_norm}\t{state_norm}")
PY
}

_planveyor_decomposition_plan_admission() {
  local requested="${1:-}"
  [[ -n "${requested//[[:space:]]/}" ]] || return 1
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tooling_root=""
  tooling_root="$(_planveyor_root)" || return $?
  local template_path=""
  template_path="$(_planveyor_doc_template_source_path "plans" "_template.md")" || return 1

  _planveyor_py_any_authority_stdin "$requested" "$root" "$template_path" "${tooling_root%/}/scripts" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

requested_raw = sys.argv[1]
root = Path(os.path.abspath(sys.argv[2]))
template_path = Path(sys.argv[3])
for script_dir in sys.argv[4:]:
    if script_dir and script_dir not in sys.path:
        sys.path.insert(0, script_dir)
try:
    import plan_status_oracle
except Exception as exc:
    print(f"Refusing decomposition init: plan_status_oracle import failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
plans_root = Path(os.path.abspath(root / "docs" / "plans"))


def reject(reason: str) -> None:
    print(f"Refusing decomposition init: {reason}", file=sys.stderr)
    raise SystemExit(1)


if any(char in requested_raw for char in ("\n", "\r", "\t", "\0")):
    reject("PLAN_PATH contains control characters")
requested = Path(requested_raw)
if ".." in requested.parts:
    reject("PLAN_PATH traversal is not allowed")
candidate = Path(os.path.abspath(requested if requested.is_absolute() else root / requested))
try:
    candidate_rel_to_plans = candidate.relative_to(plans_root)
except ValueError:
    reject("PLAN_PATH must stay inside the current repo docs/plans tree")
if not candidate_rel_to_plans.parts or candidate.suffix != ".md":
    reject("PLAN_PATH must name a docs/plans/*.md file")

try:
    root_mode = plans_root.lstat().st_mode
except OSError:
    reject("docs/plans parent must already exist")
if plans_root.is_symlink() or not stat.S_ISDIR(root_mode):
    reject("docs/plans parent must be a real directory")

cursor = plans_root
for part in candidate_rel_to_plans.parts[:-1]:
    cursor = cursor / part
    try:
        mode = cursor.lstat().st_mode
    except OSError:
        reject("missing PLAN_PATH parent chain is not admissible")
    if cursor.is_symlink() or not stat.S_ISDIR(mode):
        reject("PLAN_PATH parent chain contains a symlink or non-directory object")

candidate_exists = os.path.lexists(candidate)
if candidate_exists:
    try:
        candidate_stat = candidate.lstat()
        candidate_mode = candidate_stat.st_mode
    except OSError:
        reject("PLAN_PATH object cannot be inspected")
    if candidate.is_symlink() or not stat.S_ISREG(candidate_mode):
        reject("existing PLAN_PATH must be a regular non-symlink file")
else:
    relative = candidate.relative_to(root).as_posix()
    print(f"missing\t{relative}\t{candidate}\tmissing\tmissing")
    raise SystemExit(0)

try:
    raw_bytes = candidate.read_bytes()
    text = raw_bytes.decode("utf-8")
except (OSError, UnicodeDecodeError):
    reject("existing PLAN_PATH must be readable UTF-8")

status_values = re.findall(r"^\*\*Status:\*\*\s*(.*?)\s*$", text, flags=re.MULTILINE)
if len(status_values) != 1:
    reject("existing PLAN_PATH must contain exactly one Status header")
status = status_values[0]
allowed_statuses = {
    value.casefold()
    for value in (
        "Architect initial draft",
        "Architect draft",
        "Ready for Planner",
        "Planner intake",
        "Ready for Architect response",
        "Architect response",
        "Planner finalize",
        "Ready for Coder",
        "Coder intake",
        "In progress",
        "Ready for Review",
        "Reviewer intake",
        "Reviewer code review",
        "Reviewer visual review",
        "Ready for Arch review",
        "Architect arch review",
        "Superseded",
        "Done",
    )
}
if status.casefold() not in allowed_statuses:
    reject("existing PLAN_PATH has an unsupported Status value")
if status.casefold() in {"done", "superseded"}:
    reject("terminal or Superseded plans cannot receive decomposition overlay")


def json_blocks(value: str) -> list[tuple[re.Match[str], dict[str, object]]]:
    """Template-shape canonicalizer + legacy admission duplicate guard.

    The admission decision reads plan_meta content and validity through the
    shared duplicate-safe strict reader below; this helper stays because (a)
    normalize_template_shape needs exact fence positions to rebuild canonical
    bytes for the shape comparison and (b) the admission gate keeps refusing
    ambiguous or unparseable plan_meta fences anywhere in the document, with
    the exact legacy reject strings.
    """

    blocks: list[tuple[re.Match[str], dict[str, object]]] = []
    for match in re.finditer(r"^```json\s*$\n(.*?)^```\s*$", value, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE):
        payload_text = match.group(1).strip()
        try:
            payload = json.loads(payload_text)
        except Exception:
            if "plan_meta" in payload_text:
                reject("existing PLAN_PATH contains an unparseable plan_meta block")
            continue
        if isinstance(payload, dict) and "plan_meta" in payload:
            blocks.append((match, payload))
    return blocks


blocks = json_blocks(text)

strict = plan_status_oracle.strict_plan_meta_json(text)
if strict.state == "valid":
    meta = strict.plan_meta
    # Legacy duplicate-safe admission guard: extra parseable plan_meta fences
    # outside the sole top-level Meta carrier stay inadmissible.
    if len(blocks) != 1:
        reject("existing PLAN_PATH must contain exactly one parseable plan_meta block")
else:
    if strict.reason_code in {"meta_section_ambiguous", "plan_meta_carrier_ambiguous"}:
        reject("existing PLAN_PATH must contain exactly one parseable plan_meta block")
    if strict.reason_code == "plan_meta_not_object":
        reject("plan_meta must be an object")
    reject("existing PLAN_PATH contains an unparseable plan_meta block")
if not isinstance(meta, dict):
    reject("plan_meta must be an object")

overlay = meta.get("phase_overlay")
phase_state = meta.get("phase_state")
wave_family = meta.get("wave_family")
promoted_from = meta.get("promoted_from")
if overlay == "decomposition_wave" and phase_state == "active":
    if wave_family is not None or promoted_from is not None:
        reject("active decomposition overlay is incompatible with wave_family or promoted_from")
    relative = candidate.relative_to(root).as_posix()
    identity = f"{candidate_stat.st_dev}:{candidate_stat.st_ino}"
    print(f"active\t{relative}\t{candidate}\t{hashlib.sha256(raw_bytes).hexdigest()}\t{identity}")
    raise SystemExit(0)
if overlay is not None or phase_state is not None:
    reject("existing PLAN_PATH has incompatible planning overlay markers")

if status != "Architect initial draft":
    reject("neutral candidate must have literal Architect initial draft status")
null_fields = (
    "wave_family",
    "phase_overlay",
    "phase_state",
    "promoted_from",
)
if any(meta.get(field) is not None for field in null_fields):
    reject("neutral candidate has non-null routing carriers")
empty_fields = ("next_plans", "depends_on", "canon_updates")
if any(meta.get(field) != [] for field in empty_fields):
    reject("neutral candidate has non-empty graph or canon carriers")
if "followups_out" in meta and meta.get("followups_out") != []:
    reject("neutral candidate has non-empty graph or canon carriers")

try:
    template_text = template_path.read_text(encoding="utf-8")
except OSError:
    reject("canonical plan template is unavailable")


def normalize_template_shape(value: str) -> str:
    blocks_here = json_blocks(value)
    if len(blocks_here) != 1:
        reject("template-shape comparison requires exactly one plan_meta block")
    match, payload = blocks_here[0]
    canonical_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    normalized = value[: match.start()] + "```json\n" + canonical_json + "\n```" + value[match.end() :]
    lines: list[str] = []
    normalized_headers = (
        "**Date:**",
        "**Stage:**",
        "**Priority:**",
        "**Plan type:**",
        "**Status:**",
    )
    for line in normalized.splitlines():
        if re.match(r"^#\s*Plan:\s*", line):
            lines.append("# Plan: <normalized>")
            continue
        header = next((prefix for prefix in normalized_headers if line.startswith(prefix)), None)
        if header is not None:
            lines.append(f"{header} <normalized>")
            continue
        lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


if normalize_template_shape(text) != normalize_template_shape(template_text):
    reject("existing PLAN_PATH is populated or differs from the canonical neutral template")

relative = candidate.relative_to(root).as_posix()
identity = f"{candidate_stat.st_dev}:{candidate_stat.st_ino}"
print(f"neutral\t{relative}\t{candidate}\t{hashlib.sha256(raw_bytes).hexdigest()}\t{identity}")
PY
}

_planveyor_decomposition_bootstrap_plan_file() {
  local plan_fs="${1:-}"
  local plan_path="${2:-}"
  local admission="${3:-}"
  local expected_hash="${4:-}"
  local expected_identity="${5:-}"
  [[ -n "${plan_fs//[[:space:]]/}" && -n "${plan_path//[[:space:]]/}" ]] || return 1
  local template_path=""
  template_path="$(_planveyor_doc_template_source_path "plans" "_template.md")" || return 1
  local root=""
  root="$(_planveyor_project_root)" || return $?

  _planveyor_py_any - "$plan_fs" "$plan_path" "$admission" "$expected_hash" "$expected_identity" "$template_path" "$root" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path

plan_fs = Path(sys.argv[1])
plan_rel = sys.argv[2]
admission = sys.argv[3]
expected_hash = sys.argv[4]
expected_identity = sys.argv[5]
template_path = Path(sys.argv[6])
root = Path(os.path.abspath(sys.argv[7]))
plans_root = root / "docs" / "plans"

if admission not in {"missing", "neutral", "active"}:
    print("Refusing decomposition init: invalid publication admission", file=sys.stderr)
    raise SystemExit(1)


def regular_non_symlink(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) and not path.is_symlink()


def object_identity(path: Path) -> str:
    value = path.lstat()
    return f"{value.st_dev}:{value.st_ino}"


def safe_parent_chain() -> bool:
    try:
        plans_mode = plans_root.lstat().st_mode
    except OSError:
        return False
    if plans_root.is_symlink() or not stat.S_ISDIR(plans_mode):
        return False
    try:
        relative = plan_fs.relative_to(plans_root)
    except ValueError:
        return False
    cursor = plans_root
    for part in relative.parts[:-1]:
        cursor = cursor / part
        try:
            mode = cursor.lstat().st_mode
        except OSError:
            return False
        if cursor.is_symlink() or not stat.S_ISDIR(mode):
            return False
    return True


if not safe_parent_chain():
    print("Refusing decomposition init: PLAN_PATH parent identity changed after admission", file=sys.stderr)
    raise SystemExit(1)

if admission == "active":
    if (
        not regular_non_symlink(plan_fs)
        or object_identity(plan_fs) != expected_identity
        or hashlib.sha256(plan_fs.read_bytes()).hexdigest() != expected_hash
    ):
        print("Refusing decomposition init: active target identity or bytes changed after admission", file=sys.stderr)
        raise SystemExit(1)
    print("active")
    raise SystemExit(0)


if admission == "missing":
    if os.path.lexists(plan_fs):
        print("Refusing decomposition init: missing target appeared after admission", file=sys.stderr)
        raise SystemExit(1)
    source_bytes = template_path.read_bytes()
    source_mode = template_path.stat().st_mode & 0o777
    mode = "new"
else:
    if not regular_non_symlink(plan_fs) or object_identity(plan_fs) != expected_identity:
        print("Refusing decomposition init: neutral target identity changed after admission", file=sys.stderr)
        raise SystemExit(1)
    source_bytes = plan_fs.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != expected_hash:
        print("Refusing decomposition init: neutral target bytes changed after admission", file=sys.stderr)
        raise SystemExit(1)
    source_mode = plan_fs.stat().st_mode & 0o777
    mode = "stamp"

ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")

def derive_title(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"^\d{6}_\d{4}_", "", stem)
    stem = stem.replace("_", " ").strip(" -_")
    if not stem:
        stem = "decomposition umbrella"
    return f"# Plan: {stem} (decomposition umbrella)"

lines = source_bytes.decode("utf-8").splitlines()
out: list[str] = []
in_json = False
json_buf: list[str] = []

def rewrite_json_block(block: str) -> str:
    try:
        parsed = json.loads(block)
    except Exception:
        return block
    meta = parsed.get("plan_meta")
    if not isinstance(meta, dict):
        return block
    meta["phase_overlay"] = "decomposition_wave"
    meta["phase_state"] = "active"
    parsed["plan_meta"] = meta
    return json.dumps(parsed, ensure_ascii=False, indent=2)

for line in lines:
    if not in_json and re.match(r"^\s*```json\s*$", line, re.IGNORECASE):
        in_json = True
        json_buf = []
        out.append(line)
        continue
    if in_json and re.match(r"^\s*```\s*$", line):
        block = "\n".join(json_buf)
        out.append(rewrite_json_block(block))
        out.append(line)
        in_json = False
        json_buf = []
        continue
    if in_json:
        json_buf.append(line)
        continue

    new_line = line
    if mode == "new":
        if re.match(r"^#\s*Plan:\s*", new_line):
            new_line = derive_title(plan_fs)
        elif re.match(r"^\*\*Date:\*\*.*", new_line):
            new_line = f"**Date:** {ts}"
        elif re.match(r"^\*\*Stage:\*\*.*", new_line):
            new_line = "**Stage:** Stage 1"
        elif re.match(r"^\*\*Plan type:\*\*.*", new_line):
            new_line = "**Plan type:** dev"
        elif re.match(r"^\*\*Status:\*\*.*", new_line):
            new_line = "**Status:** Architect initial draft"
        elif re.match(r"^[ \t]*- Code draft\(s\):.*", new_line):
            new_line = "- Code draft(s): `N/A (active decomposition umbrella; promoted child drafts materialize during the wave)`"
    out.append(new_line)

published = ("\n".join(out) + "\n").encode("utf-8")
temp_name: str | None = None
try:
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=plan_fs.parent,
        prefix=f".{plan_fs.name}.planveyor.",
        delete=False,
    ) as handle:
        temp_name = handle.name
        handle.write(published)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp_name, source_mode)
    if admission == "missing":
        os.link(temp_name, plan_fs)
        os.unlink(temp_name)
        temp_name = None
    else:
        if (
            not safe_parent_chain()
            or not regular_non_symlink(plan_fs)
            or object_identity(plan_fs) != expected_identity
            or hashlib.sha256(plan_fs.read_bytes()).hexdigest() != expected_hash
        ):
            raise OSError("neutral target changed before replace")
        os.replace(temp_name, plan_fs)
        temp_name = None
except OSError as exc:
    if temp_name is not None:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
    print(f"Refusing decomposition init: atomic publication failed ({exc})", file=sys.stderr)
    raise SystemExit(1)

final_text = plan_fs.read_text(encoding="utf-8")
if final_text.count('"phase_overlay": "decomposition_wave"') != 1 or final_text.count('"phase_state": "active"') != 1:
    print("Refusing decomposition init: post-publication marker readback failed", file=sys.stderr)
    raise SystemExit(1)
print(mode)
PY
}

_planveyor_decomposition_seed_plan_path() {
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local ts=""
  ts="$(date +%y%m%d_%H%M)"
  local candidate="docs/plans/${ts}_decomposition_seed.md"
  local candidate_fs="$root/$candidate"
  local suffix=2
  while [[ -e "$candidate_fs" ]]; do
    candidate="docs/plans/${ts}_decomposition_seed_${suffix}.md"
    candidate_fs="$root/$candidate"
    suffix=$((suffix + 1))
  done
  echo "$candidate"
}

planveyor_decomposition_seed_promote() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_decomposition_seed_promote)" || return $?
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
  local new_plan_path="${1:-}"
  local old_plan_path="${2:-}"
  [[ -n "${new_plan_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_decomposition_seed_promote <NEW_PLAN_PATH> [OLD_PLAN_PATH]" >&2
    return 1
  }

  if [[ -z "${old_plan_path//[[:space:]]/}" ]]; then
    old_plan_path="$(planveyor_planpath 2>/dev/null || true)"
  fi
  [[ -n "${old_plan_path//[[:space:]]/}" ]] || {
    echo "Missing OLD_PLAN_PATH. Provide it explicitly or set .planveyor.planpath to the decomposition seed." >&2
    return 1
  }

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local old_fs="$old_plan_path"
  local new_fs="$new_plan_path"
  [[ "$old_fs" == /* ]] || old_fs="$root/$old_fs"
  [[ "$new_fs" == /* ]] || new_fs="$root/$new_fs"
  [[ -f "$old_fs" ]] || {
    echo "Missing seed plan: ${old_plan_path}" >&2
    return 1
  }
  [[ ! -e "$new_fs" ]] || {
    echo "Target plan already exists: ${new_plan_path}" >&2
    return 1
  }
  [[ "${old_fs:t}" == *_decomposition_seed.md || "${old_fs:t}" == *_decomposition_seed_<->.md ]] || {
    echo "Refusing to promote non-seed plan: ${old_plan_path}" >&2
    return 1
  }
  if rg -q '^[[:space:]]*-[[:space:]]*Code draft\(s\):.*docs/code_drafts/' "$old_fs" 2>/dev/null; then
    echo "Refusing to promote seed after code draft link was materialized: ${old_plan_path}" >&2
    return 1
  fi

  mkdir -p "${new_fs:h}" || return 1
  mv "$old_fs" "$new_fs" || return 1
  echo "Renamed decomposition seed: ${old_plan_path} -> ${new_plan_path}" >&2

  local current_plan=""
  current_plan="$(planveyor_planpath 2>/dev/null || true)"
  if [[ "$current_plan" == "$old_plan_path" || "$current_plan" == "$old_fs" ]]; then
    planveyor_plan_set "$new_plan_path" || return 1
  fi

  local answers_path="$root/.planveyor.owner_answers"
  if [[ -f "$answers_path" ]]; then
    _planveyor_py_any - "$answers_path" "$old_plan_path" "$old_fs" "$new_plan_path" "$new_fs" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

answers_path = Path(sys.argv[1])
old_rel = sys.argv[2]
old_abs = sys.argv[3]
new_rel = sys.argv[4]
new_abs = sys.argv[5]

lines = answers_path.read_text(encoding="utf-8").splitlines()
out: list[str] = []
changed = False
for line in lines:
    if line.startswith("PLAN_PATH="):
        value = line[len("PLAN_PATH="):].strip()
        if value in {old_rel, old_abs}:
            line = f"PLAN_PATH={new_rel}"
            changed = True
    out.append(line)

if changed:
    answers_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  fi
}

planveyor_analysis_init() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_analysis_init)" || return $?
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
  # Prepare an existing analysis-wave plan for the ordinary Manager single-plan flow.
  # This is readback/proof only: route mutation truth remains in plan/oracle carriers.
  local plan_path="${1:-}"
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local should_persist_plan=0

  if (( $# > 1 )); then
    echo "Usage: planveyor_analysis_init [PLAN_PATH]" >&2
    return 1
  fi

  if [[ -n "${plan_path//[[:space:]]/}" ]]; then
    should_persist_plan=1
  else
    plan_path="$(planveyor_planpath 2>/dev/null || true)"
  fi
  if [[ -z "${plan_path//[[:space:]]/}" ]]; then
    echo "Usage: planveyor_analysis_init [PLAN_PATH]" >&2
    echo "Missing PLAN_PATH. Provide an existing analysis-wave plan or set .planveyor.planpath." >&2
    return 1
  fi

  local plan_fs="$plan_path"
  [[ "$plan_fs" == /* ]] || plan_fs="$root/$plan_fs"
  if [[ ! -f "$plan_fs" ]]; then
    echo "Missing analysis plan: ${plan_path}" >&2
    return 1
  fi

  local oracle_json=""
  oracle_json="$(planveyor_plan_status_oracle --json "$plan_path")" || return 1

  local fields_tsv=""
  fields_tsv="$(
    print -r -- "$oracle_json" | _planveyor_py_any -c '
import json
import sys

data = json.load(sys.stdin)
keys = (
    "status_value",
    "planning_contour_marker",
    "source_route_state",
    "queue_activation_state",
    "runtime_class",
)
for key in keys:
    value = data.get(key, "")
    if value is None:
        value = ""
    print(f"{key}\t{value}")
'
  )" || return 1

  local -A oracle_fields
  local key=""
  local value=""
  while IFS=$'\t' read -r key value; do
    [[ -n "${key//[[:space:]]/}" ]] || continue
    oracle_fields[$key]="$value"
  done <<< "$fields_tsv"

  local marker="${oracle_fields[planning_contour_marker]:-}"
  if [[ "$marker" != "analysis_wave" ]]; then
    echo "Refusing analysis init: plan is not an analysis-wave source." >&2
    echo "Oracle readback: status=${oracle_fields[status_value]:-} planning_contour_marker=${marker:-none} source_route_state=${oracle_fields[source_route_state]:-} queue_activation_state=${oracle_fields[queue_activation_state]:-} runtime_class=${oracle_fields[runtime_class]:-}" >&2
    return 1
  fi

  if (( should_persist_plan )); then
    planveyor_plan_set "$plan_path" || return 1
  fi

  echo "Prepared analysis wave: ${plan_path}"
  echo "Oracle readback: status=${oracle_fields[status_value]:-} planning_contour_marker=analysis_wave source_route_state=${oracle_fields[source_route_state]:-} queue_activation_state=${oracle_fields[queue_activation_state]:-} runtime_class=${oracle_fields[runtime_class]:-}"
  echo "Next: MANAGER_CMD=run ${plan_path}"
}

planveyor_decomposition_init() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_decomposition_init)" || return $?
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
  local plan_path="${1:-}"
  local should_persist_plan=0
  local plan_created=0
  local bootstrap_mode=""

  if (( $# > 1 )); then
    echo "Usage: planveyor_decomposition_init [PLAN_PATH]" >&2
    return 1
  fi

  if [[ -n "${plan_path//[[:space:]]/}" ]]; then
    should_persist_plan=1
  else
    local current_plan=""
    current_plan="$(planveyor_planpath 2>/dev/null || true)"
    if [[ -n "${current_plan//[[:space:]]/}" ]]; then
      local current_overlay_state=""
      current_overlay_state="$(_planveyor_plan_phase_overlay_state "$current_plan" 2>/dev/null || true)"
      local current_overlay="${current_overlay_state%%$'\t'*}"
      local current_state="${current_overlay_state#*$'\t'}"
      if [[ "$current_overlay" == "decomposition_wave" && "$current_state" == "active" ]]; then
        plan_path="$current_plan"
      fi
    fi
    if [[ -z "${plan_path//[[:space:]]/}" ]]; then
      plan_path="$(_planveyor_decomposition_seed_plan_path)" || return 1
      should_persist_plan=1
    fi
  fi

  local admission_row=""
  admission_row="$(_planveyor_decomposition_plan_admission "$plan_path")" || return 1
  local admission=""
  local plan_fs=""
  local expected_hash=""
  local expected_identity=""
  IFS=$'\t' read -r admission plan_path plan_fs expected_hash expected_identity <<< "$admission_row"
  [[ -n "${admission//[[:space:]]/}" && -n "${plan_path//[[:space:]]/}" && -n "${plan_fs//[[:space:]]/}" ]] || {
    echo "Refusing decomposition init: invalid admission readback" >&2
    return 1
  }

  bootstrap_mode="$(_planveyor_decomposition_bootstrap_plan_file "$plan_fs" "$plan_path" "$admission" "$expected_hash" "$expected_identity")" || return 1
  [[ "$bootstrap_mode" == "new" ]] && plan_created=1

  local overlay_state=""
  overlay_state="$(_planveyor_plan_phase_overlay_state "$plan_path")" || return 1
  local phase_overlay="${overlay_state%%$'\t'*}"
  local phase_state="${overlay_state#*$'\t'}"
  if [[ "$phase_overlay" != "decomposition_wave" || "$phase_state" != "active" ]]; then
    echo "Plan is not an active decomposition umbrella: ${plan_path}" >&2
    echo "Required plan_meta markers:" >&2
    echo '  "phase_overlay": "decomposition_wave"' >&2
    echo '  "phase_state": "active"' >&2
    echo "Current: phase_overlay=${phase_overlay:-<empty>} phase_state=${phase_state:-<empty>}" >&2
    return 1
  fi

  if (( should_persist_plan )); then
    planveyor_plan_set "$plan_path" || return 1
  fi

  local status_pre=""
  status_pre="$(planveyor_status_line "$plan_path" 2>/dev/null || true)"
  [[ -n "${status_pre//[[:space:]]/}" ]] && echo "Plan status (prepare): ${status_pre}" >&2

  local manager_sid=""
  manager_sid="$(planveyor_session manager 2>/dev/null || true)"
  if [[ -n "${manager_sid//[[:space:]]/}" && "$manager_sid" != "<SESSION_ID>" ]]; then
    if ! _planveyor_session_sid_ensure_in_effective_codex_home manager >/dev/null 2>&1; then
      echo "Manager session missing/stale for current CODEX_HOME; initializing a new Manager session..." >&2
      planveyor_manager_init || return 1
    fi
  else
    echo "Initializing Manager session for decomposition wave..." >&2
    planveyor_manager_init || return 1
  fi

  if (( plan_created )); then
    echo "Created decomposition umbrella scaffold: ${plan_path}" >&2
    echo "Input model: describe the raw task in Manager collab / Architect intake; the wave will materialize umbrella + child plans." >&2
  elif [[ "$bootstrap_mode" == "stamp" ]]; then
    echo "Stamped decomposition overlay on umbrella candidate: ${plan_path}" >&2
  fi

  echo "Prepared active decomposition wave: ${plan_path}" >&2
  echo "Next: planveyor_decomposition_collab_tui ${plan_path}" >&2
}

planveyor_decomposition_collab() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_decomposition_collab)" || return $?
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
  if (( $# > 1 )); then
    echo "Usage: planveyor_decomposition_collab [PLAN_PATH]" >&2
    return 1
  fi
  planveyor_decomposition_init "${1:-}" || return 1
  planveyor_manager_collab
}

planveyor_decomposition_collab_tui() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_decomposition_collab_tui)" || return $?
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
  local plan_path=""
  local -a tui_flags
  tui_flags=()

  while (( $# > 0 )); do
    case "${1:-}" in
      --no-alt-screen) tui_flags+=(--no-alt-screen) ;;
      --help|-h)
        echo "Usage: planveyor_decomposition_collab_tui [PLAN_PATH] [--no-alt-screen]" >&2
        return 0
        ;;
      *)
        if [[ -z "${plan_path//[[:space:]]/}" ]]; then
          plan_path="$1"
        else
          echo "Usage: planveyor_decomposition_collab_tui [PLAN_PATH] [--no-alt-screen]" >&2
          return 1
        fi
        ;;
    esac
    shift
  done

  planveyor_decomposition_init "$plan_path" || return 1
  planveyor_manager_collab_tui "${tui_flags[@]}"
}

planveyor_code_draft_stub_from_plan() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_code_draft_stub_from_plan)" || return $?
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
  # Creates a code draft stub for a plan and ensures the plan links it in Context links.
  # Usage:
  #   planveyor_code_draft_stub_from_plan                    # uses saved PLAN_PATH; role=Planner
  #   planveyor_code_draft_stub_from_plan docs/plans/...md   # explicit PLAN_PATH
  #   planveyor_code_draft_stub_from_plan --role Coder       # explicit author role (Planner|Coder|Architect)
  local root="$(_planveyor_project_root)" || return $?

  local author_role="Planner"
  local plan_rel=""
  while (( $# > 0 )); do
    case "${1:-}" in
      --role)
        shift || true
        author_role="${1:-}"
        ;;
      --help|-h)
        echo "Usage: planveyor_code_draft_stub_from_plan [PLAN_PATH] [--role Planner|Coder|Architect]" >&2
        return 0
        ;;
      *)
        if [[ -z "${plan_rel//[[:space:]]/}" ]]; then
          plan_rel="$1"
        else
          echo "Usage: planveyor_code_draft_stub_from_plan [PLAN_PATH] [--role Planner|Coder|Architect]" >&2
          return 1
        fi
        ;;
    esac
    shift || true
  done

  if [[ -z "${plan_rel//[[:space:]]/}" ]]; then
    plan_rel="$(planveyor_planpath)" || return 1
  fi

  case "${author_role:l}" in
    planner) author_role="Planner" ;;
    coder) author_role="Coder" ;;
    architect|arch) author_role="Architect" ;;
    *)
      echo "Unsupported --role: ${author_role} (use Planner|Coder|Architect)" >&2
      return 1
      ;;
  esac

  local plan_path="$plan_rel"
  [[ "$plan_path" == /* ]] || plan_path="$root/$plan_path"
  [[ -f "$plan_path" ]] || { echo "Missing plan: ${plan_rel}" >&2; return 1; }

  local plan_base="${plan_path:t:r}"
  local draft_rel="docs/code_drafts/${plan_base}__code_draft.md"
  local draft_path="$root/$draft_rel"
  local authority_json=""
  local authority_scaffold_json=""
  local tooling_root="$(_planveyor_root)"
  authority_json="$(planveyor_plan_status_oracle --json "$plan_rel")" || {
    echo "Machine-authority readback failed for plan: ${plan_rel}" >&2
    return 1
  }
  authority_scaffold_json="$(
    _planveyor_py_authority_stdin "$authority_json" "$draft_path" "$plan_path" "$tooling_root" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Mapping

payload, draft_path, plan_path, tooling_root = sys.argv[1:5]
payload = json.loads(payload)
draft_exists = Path(draft_path).is_file()
sys.path.insert(0, str(Path(tooling_root) / "scripts"))
from plan_status_oracle import machine_authority_decision_readback, strict_plan_meta_json

plan_text = Path(plan_path).read_text(encoding="utf-8")
strict_meta = strict_plan_meta_json(plan_text)
if strict_meta.state != "valid" or not isinstance(strict_meta.plan_meta, Mapping):
    raise SystemExit("strict machine-authority Meta readback is invalid")
readback = machine_authority_decision_readback(Path(plan_path), plan_text=plan_text)
for field, value in {
    "machine_authority_decision_state": readback.state,
    "machine_authority_decision_reason": readback.reason_code,
    "machine_authority_decision_id": readback.decision_id,
    "machine_authority_decision_carrier_sha256": readback.carrier_sha256,
    "machine_authority_decision_ref_state": readback.ref_state,
}.items():
    if payload.get(field) != value:
        raise SystemExit(f"machine-authority readback changed before scaffold: {field}")

raw_cluster = strict_meta.plan_meta.get("cluster")
cluster = raw_cluster.strip() if isinstance(raw_cluster, str) and raw_cluster.strip() else "UNCONFIRMED"
state = readback.state
ref_state = readback.ref_state
reason = readback.reason_code
ref = None

if state == "legacy":
    pass
elif state == "frozen_confirmed":
    if draft_exists:
        if ref_state != "valid":
            raise SystemExit(
                "existing code draft has no validated machine-authority decision ref; "
                "refusing to rewrite it"
            )
        print("")
    else:
        decision_id = str(payload.get("machine_authority_decision_id") or "")
        carrier_sha256 = str(payload.get("machine_authority_decision_carrier_sha256") or "")
        if not decision_id or not carrier_sha256:
            raise SystemExit("validated machine-authority readback omitted derived active ref fields")
        ref = {
            "applicability": "required",
            "decision_id": decision_id,
            "carrier_sha256": carrier_sha256,
        }
elif state == "not_applicable":
    if draft_exists:
        if ref_state != "valid":
            raise SystemExit(
                "existing code draft has no validated machine-authority decision ref; "
                "refusing to rewrite it"
            )
    else:
        decision = strict_meta.plan_meta.get("machine_authority_decision")
        if not isinstance(decision, Mapping):
            raise SystemExit("validated N-A machine-authority carrier is missing")
        reason_code = decision.get("reason_code")
        carrier_sha256 = readback.carrier_sha256
        if not isinstance(reason_code, str) or not reason_code or not carrier_sha256:
            raise SystemExit("validated machine-authority readback omitted derived N-A ref fields")
        ref = {
            "applicability": "not_applicable",
            "reason_code": reason_code,
            "carrier_sha256": carrier_sha256,
        }
else:
    raise SystemExit(
        "machine-authority carrier is not a validated scaffold input: "
        f"state={state or 'missing'} reason={reason} ref_state={ref_state or 'missing'}"
    )
print(json.dumps({"cluster": cluster, "ref": ref}, ensure_ascii=False, separators=(",", ":")))
PY
  )" || {
    echo "Machine-authority scaffold admission failed for plan: ${plan_rel}" >&2
    return 1
  }

  pushd "$root" >/dev/null || return 1
  mkdir -p docs/code_drafts

  if [[ ! -f "$draft_path" ]]; then
    _planveyor_copy_doc_template_if_missing "$draft_path" "code_drafts" "_template.md" || {
      popd >/dev/null || return 1
      return 1
    }
    _planveyor_py - "$draft_path" "$plan_rel" "$author_role" "$plan_path" "$authority_scaffold_json" <<'PY'
from __future__ import annotations

import json
import re
import sys
from datetime import datetime

draft_path, plan_rel, author_role, plan_fs, authority_scaffold_json = sys.argv[1:6]
authority_scaffold = json.loads(authority_scaffold_json)
cluster = str(authority_scaffold["cluster"])
authority_ref = authority_scaffold["ref"]

ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")

plan_lines = open(plan_fs, "r", encoding="utf-8").read().splitlines()
title = None
if plan_lines:
    m = re.match(r"^#\s*Plan:\s*(.+?)\s*$", plan_lines[0])
    if m:
        title = m.group(1).strip()
if not title:
    title = plan_rel

lines = open(draft_path, "r", encoding="utf-8").read().splitlines()
out: list[str] = []

def repl_meta_json(block: str) -> str:
    try:
        parsed = json.loads(block)
    except Exception:
        return block
    if not isinstance(parsed, dict) or "code_draft_meta" not in parsed:
        return block
    meta = parsed.get("code_draft_meta")
    if not isinstance(meta, dict):
        return block
    meta["plan"] = plan_rel
    meta["cluster"] = cluster
    if authority_ref is not None:
        meta["machine_authority_decision_ref"] = authority_ref
    # Keep a stub target, but make it obvious it's a stub.
    targets = meta.get("targets")
    if not isinstance(targets, list) or not targets:
        meta["targets"] = [{"path": "UNCONFIRMED", "kind": "py"}]
    parsed["code_draft_meta"] = meta
    return json.dumps(parsed, ensure_ascii=False, indent=2)

in_json = False
json_buf: list[str] = []

replacements = {
    r"^# Code draft: .*": f"# Code draft: {title}",
    r"^\*\*Date:\*\*.*": f"**Date:** {ts}",
    r"^\*\*Cluster:\*\*.*": f"**Cluster:** {cluster}",
    r"^\*\*Related plan:\*\*.*": f"**Related plan:** `{plan_rel}`",
    r"^\*\*Author role:\*\*.*": f"**Author role:** {author_role}",
}

for line in lines:
    if not in_json and re.match(r"^\s*```json\s*$", line, re.IGNORECASE):
        in_json = True
        json_buf = []
        out.append(line)
        continue
    if in_json and re.match(r"^\s*```\s*$", line):
        out.append(repl_meta_json("\n".join(json_buf).strip()))
        out.append(line)
        in_json = False
        json_buf = []
        continue
    if in_json:
        json_buf.append(line)
        continue

    new_line = line
    for pat, rep in replacements.items():
        if re.match(pat, new_line):
            new_line = rep
            break
    out.append(new_line)

open(draft_path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
    echo "Created code draft: ${draft_rel}" >&2
  else
    echo "Code draft exists: ${draft_rel}" >&2
  fi

  _planveyor_py - "$plan_path" "$draft_rel" <<'PY'
from __future__ import annotations

import re
import sys

plan_fs, draft_rel = sys.argv[1:3]

lines = open(plan_fs, "r", encoding="utf-8").read().splitlines()
out: list[str] = []

re_cd = re.compile(r"^\s*-\s*Code draft", re.IGNORECASE)
re_ctx = re.compile(r"^\s*\*\*Context links \(source of truth\):\*\*\s*$", re.IGNORECASE)

replaced = False
for line in lines:
    if re_cd.match(line):
        out.append(f"- Code draft(s): `{draft_rel}`")
        replaced = True
    else:
        out.append(line)

if not replaced:
    ctx_idx = None
    end_idx = None
    for i, line in enumerate(out):
        if ctx_idx is None and re_ctx.match(line.strip()):
            ctx_idx = i
            continue
        if ctx_idx is not None:
            if line.strip() == "---":
                end_idx = i
                break
    if ctx_idx is not None and end_idx is not None:
        insert_at = end_idx
        out.insert(insert_at, f"- Code draft(s): `{draft_rel}`")
        replaced = True

if not replaced:
    # Best-effort fallback: append near top.
    out.insert(1, f"- Code draft(s): `{draft_rel}`")

open(plan_fs, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY

  echo "Linked code draft in plan: ${plan_rel}" >&2
  popd >/dev/null || return 1
}

planveyor_pybin_set() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_pybin_set)" || return $?
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
  echo "planveyor_pybin_set is retired: select the trusted planveyor Python in the invoking PATH or CONDA_PREFIX; project files cannot select executables." >&2
  return 2
}

planveyor_session_set() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_session_set)" || return $?
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
  session_key="$(_planveyor_normalize_session_key "$1")" || {
    echo "Usage: planveyor_session_set <architect|coder|planner|reviewer|reviewer_code_risk|reviewer_code_contracts|manager|architect_process_roles|architect_process_collab|architect_innovations> <SESSION_ID> [META]" >&2
    return 1
  }
  local sid="$2"
  [[ -n "${sid//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_session_set <architect|coder|planner|reviewer|reviewer_code_risk|reviewer_code_contracts|manager|architect_process_roles|architect_process_collab|architect_innovations> <SESSION_ID> [META]" >&2
    return 1
  }
  local meta="${3:-}"
  meta="${meta//$'\r'/ }"
  meta="${meta//$'\n'/ }"
  meta="${meta//$'\t'/ }"
  meta="${meta#"${meta%%[![:space:]]*}"}"
  meta="${meta%"${meta##*[![:space:]]}"}"

  # A current context cannot bless an arbitrary old SID.  The only engaged
  # authority proof is the successful init receipt bound to this SID/key.
  _planveyor_session_authority_resume_validate "$session_key" "$sid" || {
    echo "Refusing to save an authority-unbound session id for ${session_key}" >&2
    return 1
  }
  if [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
    local authority_context_sha=""
    authority_context_sha="$(_planveyor_authority_context_field "$PLANVEYOR_CTX_JSON" context_sha256)" || return $?
    meta="${meta:+${meta} }authority_generation=${PLANVEYOR_CTX_GENERATION} authority_context_sha256=${authority_context_sha}"
  fi

  local root="$(_planveyor_project_root)" || return $?
  local now="$(_planveyor_now)"

  local file_path="$root/.planveyor.session.${session_key}"
  local log_path="$root/.planveyor.session.${session_key}.log"
  local file_tmp="${file_path}.tmp.$$"
  if [[ ( -e "$file_path" || -L "$file_path" ) && ( ! -f "$file_path" || -L "$file_path" ) ]]; then
    echo "Invalid session pointer destination (expected a regular file): ${file_path}" >&2
    return 1
  fi
  {
    printf "# %s\n" "$now"
    [[ -n "${meta//[[:space:]]/}" ]] && printf "# meta: %s\n" "$meta"
    printf "%s\n" "$sid"
  } > "$file_tmp" || {
    rm -f "$file_tmp" 2>/dev/null || true
    echo "Failed to write session pointer: ${file_path}" >&2
    return 1
  }
  # Replace the exact path. Unlike mv, os.replace cannot move the temporary
  # pointer inside a directory that appeared after the destination check.
  _planveyor_py_any -c 'import os,sys; os.replace(sys.argv[1], sys.argv[2])' "$file_tmp" "$file_path" || {
    rm -f "$file_tmp" 2>/dev/null || true
    echo "Failed to finalize session pointer: ${file_path}" >&2
    return 1
  }
  if [[ ! -f "$file_path" || -L "$file_path" || "$(_planveyor_last_line "$file_path")" != "$sid" ]]; then
    echo "Failed to verify session pointer: ${file_path}" >&2
    return 1
  fi
  if [[ -n "${meta//[[:space:]]/}" ]]; then
    printf "%s\t%s\t%s\n" "$now" "$sid" "$meta" >> "$log_path" || {
      echo "Failed to append session log: ${log_path}" >&2
      return 1
    }
  else
    printf "%s\t%s\n" "$now" "$sid" >> "$log_path" || {
      echo "Failed to append session log: ${log_path}" >&2
      return 1
    }
  fi
  echo "Saved: ${file_path} (${now})" >&2
}


planveyor_plan_provenance_context() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_provenance_context)" || return $?
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
  local helper_script="$(_planveyor_script codex_session_context.py)"
  [[ -r "$helper_script" ]] || helper_script="$(_planveyor_root)/scripts/codex_session_context.py"
  [[ -r "$helper_script" ]] || {
    echo "Missing helper: ${helper_script}" >&2
    return 1
  }
  # Session pointers and run receipts belong to the selected project. The
  # helper's own default is the runtime checkout, so bind the project root
  # first; argparse keeps the last value, so a caller's --root still wins.
  local project_root=""
  project_root="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$helper_script" --root "$project_root" "$@"
}

planveyor_plan_provenance_stamp() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_provenance_stamp)" || return $?
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
  local plan_path="${1:-}"
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_plan_provenance_stamp <PLAN_PATH> [HELPER_ARGS...]" >&2
    return 1
  }
  shift || true
  planveyor_plan_provenance_context --plan-path "$plan_path" --format markdown "$@"
}



planveyor_owner_answers_set() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_owner_answers_set)" || return $?
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
  role_id="$(_planveyor_normalize_role_id "$1")" || {
    echo "Usage: planveyor_owner_answers_set <architect|coder|planner|reviewer|a|c|p|r> [PLAN_PATH]" >&2
    return 1
  }
  case "$role_id" in
    architect|coder|planner|reviewer) ;;
    *) echo "Usage: planveyor_owner_answers_set <architect|coder|planner|reviewer|a|c|p|r> [PLAN_PATH]" >&2; return 1 ;;
  esac

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local plan_path="${2:-}"
  if [[ -z "${plan_path//[[:space:]]/}" ]]; then
    plan_path="$(planveyor_planpath 2>/dev/null || true)"
  fi
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Missing PLAN_PATH. Provide it as 2nd arg or set .planveyor.planpath." >&2
    return 1
  }

  echo "Paste Owner answers for TO=${role_id}; finish with Ctrl-D." >&2
  local body
  body="$(cat)" || return 1

  local file_path="$root/.planveyor.owner_answers"
  cat > "$file_path" <<EOF
TO=${role_id}
PLAN_PATH=${plan_path}
---
${body}
EOF
  echo "Saved: ${file_path} (TO=${role_id})" >&2
}

_planveyor_owner_answers_for() {
  local role_id="$1"
  local plan_path="$2"
  local mode="${3:-consume}" # consume|peek
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local file_path="$root/.planveyor.owner_answers"
  [[ -f "$file_path" ]] || return 0

  local raw
  raw="$(<"$file_path")" || return 0
  [[ -n "${raw//[[:space:]]/}" ]] || return 0

  local -a lines
  lines=("${(@f)raw}")

  local to=""
  local plan=""
  local idx=1
  local line=""
  while (( idx <= ${#lines} )); do
    line="${lines[$idx]}"
    [[ -z "${line//[[:space:]]/}" ]] && { ((idx++)); continue; }
    [[ "$line" == TO=* ]] && { to="${line#TO=}"; ((idx++)); continue; }
    [[ "$line" == PLAN_PATH=* ]] && { plan="${line#PLAN_PATH=}"; ((idx++)); continue; }
    [[ "$line" == "---" ]] && { ((idx++)); break; }
    break
  done

  to="${to//[[:space:]]/}"
  plan="${plan//[[:space:]]/}"
  to="${to%%#*}"
  plan="${plan%%#*}"
  to="${to//[[:space:]]/}"
  plan="${plan//[[:space:]]/}"

  if [[ -z "$to" ]]; then
    echo "❗ Pending Owner answers: missing header TO=architect|planner|coder|reviewer (file: ${file_path}). Not consuming." >&2
    return 0
  fi
  if [[ "$to" != "$role_id" ]]; then
    echo "❗ Pending Owner answers: TO=${to} but role=${role_id}. Not consuming (file: ${file_path})." >&2
    return 0
  fi
  if [[ -n "$plan" && "$plan" != "$plan_path" ]]; then
    echo "❗ Pending Owner answers: PLAN_PATH mismatch (answers=${plan}, current=${plan_path}). Not consuming (file: ${file_path})." >&2
    return 0
  fi

  local -a rest
  rest=("${(@)lines[$idx,-1]}")
  local answers="${(j:\n:)rest}"
  if [[ "$mode" == "consume" ]]; then
    rm -f "$file_path" 2>/dev/null || true
  fi
  [[ -n "${answers//[[:space:]]/}" ]] || return 0
  echo "$answers"
}

_planveyor_consume_owner_answers_for() {
  _planveyor_owner_answers_for "$1" "$2" "consume"
}

_planveyor_peek_owner_answers_for() {
  _planveyor_owner_answers_for "$1" "$2" "peek"
}

planveyor_status_line() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_status_line)" || return $?
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
  local plan_path="$1"
  [[ -n "${plan_path//[[:space:]]/}" ]] || { echo "Usage: planveyor_status_line <PLAN_PATH>" >&2; return 1; }

  local root="$(_planveyor_project_root)" || return $?
  local plan_fs="$plan_path"
  [[ "$plan_fs" == /* ]] || plan_fs="${root}/${plan_fs}"
  [[ -f "$plan_fs" ]] || { echo "Missing plan: $plan_fs" >&2; return 1; }

  local oracle_py="$(_planveyor_script plan_status_oracle.py)"
  [[ -f "$oracle_py" ]] || { echo "Missing status oracle: $oracle_py" >&2; return 1; }

  _planveyor_py_any "$oracle_py" "$plan_fs"
}

planveyor_review_target_snapshot() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_review_target_snapshot)" || return $?
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
  local helper_py=""
  helper_py="$(_planveyor_script review_target_snapshot.py)" || return 1
  [[ -f "$helper_py" ]] || { echo "Missing review target snapshot helper: $helper_py" >&2; return 1; }
  _planveyor_py_any "$helper_py" "$@"
}

_planveyor_plan_review_artifact_path() {
  local plan_path="$1"
  [[ -n "${plan_path//[[:space:]]/}" ]] || return 1

  local root="$(_planveyor_project_root)" || return $?
  local plan_fs="$plan_path"
  [[ "$plan_fs" == /* ]] || plan_fs="${root}/${plan_fs}"
  [[ -f "$plan_fs" ]] || return 1

  local artifact_rel=""
  artifact_rel="$(
    awk '
      BEGIN { in_section=0 }
      /^##[[:space:]]+Review artifacts/ { in_section=1; next }
      /^##[[:space:]]+/ { if (in_section) exit }
      { if (in_section) print }
    ' "$plan_fs" \
      | rg -o 'docs/(code_reviews|doc_reviews)/[A-Za-z0-9_./-]+\.md' \
      | tail -n 1
  )"
  [[ -n "${artifact_rel//[[:space:]]/}" ]] || return 1
  echo "$artifact_rel"
}

_planveyor_review_bundle_docs_only() {
  (( $# > 0 )) || return 1

  local bundle_path=""
  for bundle_path in "$@"; do
    [[ -n "${bundle_path//[[:space:]]/}" ]] || return 1
    [[ "$bundle_path" == docs/* ]] || return 1
  done
  return 0
}

_planveyor_review_artifact_for_range_plan() {
  local plan_path="${1:-}"
  local base="${2:-}"
  local head="${3:-}"
  [[ -n "${plan_path//[[:space:]]/}" && -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || return 1

  shift 3 || true
  local -a bundle_paths
  bundle_paths=("$@")
  if (( ${#bundle_paths[@]} == 0 )); then
    bundle_paths=("$plan_path")
  fi

  local plan_stem="${plan_path:t:r}"
  if _planveyor_review_bundle_docs_only "${bundle_paths[@]}"; then
    echo "docs/doc_reviews/${plan_stem}.md"
  else
    echo "docs/code_reviews/${plan_stem}.md"
  fi
}

_planveyor_review_range_host_family() {
  if _planveyor_review_bundle_docs_only "$@"; then
    echo "doc_reviews"
  else
    echo "code_reviews"
  fi
}

_planveyor_review_range_plan_path_new() {
  local base="${1:-}"
  local head="${2:-}"
  [[ -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || return 1

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local ts=""
  ts="$(date +%y%m%d_%H%M)"
  local b7=""
  local h7=""
  b7="$(_planveyor_sha7 "$base")"
  h7="$(_planveyor_sha7 "$head")"

  local candidate="docs/plans/${ts}_reviewer_range_${b7}_${h7}.md"
  local candidate_fs="$root/$candidate"
  local suffix=2
  while [[ -e "$candidate_fs" ]]; do
    candidate="docs/plans/${ts}_reviewer_range_${b7}_${h7}_${suffix}.md"
    candidate_fs="$root/$candidate"
    suffix=$((suffix + 1))
  done
  echo "$candidate"
}

_planveyor_review_range_existing_plan_for_tuple() {
  local root="${1:-}"
  local base="${2:-}"
  local head="${3:-}"
  local exclude_docs="${4:-}"
  local profile_id="${5:-}"
  local review_host_family="${6:-}"
  local rerun_carrier_json="${7:-}"
  local reviewer_role_ref="${8:-}"
  local review_scoping_playbook_ref="${9:-}"
  local review_merge_playbook_ref="${10:-}"
  [[ -n "${root//[[:space:]]/}" && -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" && -n "${exclude_docs//[[:space:]]/}" && -n "${profile_id//[[:space:]]/}" && -n "${review_host_family//[[:space:]]/}" && -n "${rerun_carrier_json//[[:space:]]/}" && -n "${reviewer_role_ref//[[:space:]]/}" && -n "${review_scoping_playbook_ref//[[:space:]]/}" && -n "${review_merge_playbook_ref//[[:space:]]/}" ]] || return 1

  _planveyor_py - "$root" "$base" "$head" "$exclude_docs" "$profile_id" "$review_host_family" "$rerun_carrier_json" "$reviewer_role_ref" "$review_scoping_playbook_ref" "$review_merge_playbook_ref" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

root, base, head, exclude_docs, profile_id, review_host_family, rerun_carrier_json, reviewer_role_ref, review_scoping_playbook_ref, review_merge_playbook_ref = sys.argv[1:11]
root_path = Path(root)
b7 = base[:7]
h7 = head[:7]
rerun_carrier = json.loads(rerun_carrier_json)


def first_backticked_value(line: str) -> str | None:
    match = re.search(r"`([^`]+)`", line)
    if not match:
        return None
    return match.group(1)


def all_backticked_values(line: str) -> list[str]:
    return re.findall(r"`([^`]+)`", line)


def parse_review_target(text: str) -> tuple[str, str, str] | None:
    match = re.search(
        r"- Review target: `RANGE=(?P<base>[0-9a-f]+)\.\.(?P<head>[0-9a-f]+) \(EXCLUDE_DOCS=(?P<exclude>[01])\)`",
        text,
    )
    if not match:
        return None
    return match.group("base"), match.group("head"), match.group("exclude")


def parse_review_host_family(text: str) -> str | None:
    match = re.search(
        r"(?ms)^## Review artifacts\n(?P<body>.*?)(?=^## |\Z)",
        text,
    )
    if not match:
        return None
    artifact_match = re.search(r"docs/(code_reviews|doc_reviews)/[A-Za-z0-9_./-]+\.md", match.group("body"))
    if not artifact_match:
        return None
    return artifact_match.group(1)


def parse_repo_profile(text: str) -> str:
    match = re.search(r"^- Repo profile: `([^`]+)`", text, re.MULTILINE)
    if not match:
        return "" if profile_id == "planveyor" else profile_id
    return match.group(1)


def has_expected_default_context_sources(text: str) -> bool:
    context_markers = list(
        re.finditer(r"(?m)^\*\*Context links \(source of truth\):\*\*$", text)
    )
    if len(context_markers) != 1:
        return False

    context_marker = context_markers[0]
    after_context = text[context_marker.end():]
    meta_match = re.search(r"(?m)^## Meta\b", after_context)
    if not meta_match:
        return False
    context_body = after_context[:meta_match.start()]
    context_lines = context_body.splitlines()

    tick = chr(96)
    expected_ref_literals = (
        f"{tick}{reviewer_role_ref}{tick}",
        f"{tick}{review_scoping_playbook_ref}{tick}",
        f"{tick}{review_merge_playbook_ref}{tick}",
    )
    if any(context_body.count(ref_literal) != 1 for ref_literal in expected_ref_literals):
        return False

    reviewer_lines = [
        line for line in context_lines
        if re.match(r"^\s*-\s*Reviewer role\b", line)
    ]
    if reviewer_lines != [f"- Reviewer role: {tick}{reviewer_role_ref}{tick}"]:
        return False

    shared_playbook_lines = [
        line for line in context_lines
        if re.match(r"^\s*-\s*Shared playbooks\b", line)
    ]
    if shared_playbook_lines != ["- Shared playbooks:"]:
        return False

    shared_index = context_lines.index("- Shared playbooks:")
    nested_playbook_lines: list[str] = []
    for line in context_lines[shared_index + 1:]:
        if re.match(r"^-\s", line):
            break
        if not line.strip():
            continue
        if re.match(r"^\s+-", line):
            nested_playbook_lines.append(line)
            continue
        return False
    expected_playbook_lines = [
        f"  - {tick}{review_scoping_playbook_ref}{tick}",
        f"  - {tick}{review_merge_playbook_ref}{tick}",
    ]
    return nested_playbook_lines == expected_playbook_lines


def parse_rerun_tuple(text: str) -> dict[str, object] | None:
    prior_line = re.search(r"^- Prior review / rerun artifacts: .*$", text, re.MULTILINE)
    rerun_mode_line = re.search(r"^- Rerun mode: .*$", text, re.MULTILINE)
    baseline_line = re.search(r"^- Baseline artifact: .*$", text, re.MULTILINE)
    if not (prior_line and rerun_mode_line and baseline_line):
        return None

    mode = first_backticked_value(rerun_mode_line.group(0)) or ""
    baseline_value = first_backticked_value(baseline_line.group(0)) or ""
    prior_values = all_backticked_values(prior_line.group(0))

    if mode == "N/A (first pass)":
        return {
            "active": False,
            "mode": None,
            "baseline_artifact": None,
            "prior_artifacts": [],
        }

    if mode not in {"incremental", "full"}:
        return None

    if baseline_value in {"N/A (first pass)", "N/A (full rerun; explicit prior artifacts only)"}:
        baseline_value = ""

    if prior_values == ["N/A (first pass)"]:
        prior_values = []

    return {
        "active": True,
        "mode": mode,
        "baseline_artifact": baseline_value or None,
        "prior_artifacts": prior_values,
    }


expected_tuple = {
    "base": base,
    "head": head,
    "exclude_docs": exclude_docs,
    "profile_id": profile_id,
    "review_host_family": review_host_family,
    "rerun": {
        "active": bool(rerun_carrier.get("active")),
        "mode": rerun_carrier.get("mode"),
        "baseline_artifact": rerun_carrier.get("baseline_artifact"),
        "prior_artifacts": rerun_carrier.get("prior_artifacts") or [],
    },
}

candidate_paths = sorted(
    root_path.glob(f"docs/plans/*_reviewer_range_{b7}_{h7}*.md"),
)
for candidate in candidate_paths:
    try:
        text = candidate.read_text(encoding="utf-8")
    except Exception:
        continue

    if profile_id == "default" and not has_expected_default_context_sources(text):
        continue

    parsed_target = parse_review_target(text)
    if parsed_target != (
        expected_tuple["base"],
        expected_tuple["head"],
        expected_tuple["exclude_docs"],
    ):
        # An external scaffold can retain its deterministic filename while its
        # human target line is absent, noncanonical, or drifts. Return that
        # candidate to the publisher: strict full-graph readback will repair
        # the matching authority or fail closed on any real support-payload
        # conflict. Inline carriers retain the old mismatch skip because they
        # do not carry the full tuple.
        if not re.search(
            r'"schema_version"\s*:\s*"review_visual_lane_contract_ref\.v1"',
            text,
        ):
            continue

    candidate_host_family = parse_review_host_family(text)
    if candidate_host_family != expected_tuple["review_host_family"]:
        continue

    if parse_repo_profile(text) != expected_tuple["profile_id"]:
        continue

    candidate_rerun = parse_rerun_tuple(text)
    if candidate_rerun != expected_tuple["rerun"]:
        continue

    print(candidate.relative_to(root_path).as_posix())
    raise SystemExit(0)
PY
}

_planveyor_review_range_rerun_carrier_json() {
  local root="${1:-}"
  [[ -n "${root//[[:space:]]/}" ]] || return 1

  local rerun_mode="${PLANVEYOR_REVIEW_RERUN_MODE:-}"
  local baseline_artifact="${PLANVEYOR_REVIEW_BASELINE_ARTIFACT:-}"
  local prior_artifacts="${PLANVEYOR_REVIEW_PRIOR_ARTIFACTS:-}"

  _planveyor_py - "$root" "$rerun_mode" "$baseline_artifact" "$prior_artifacts" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

root, mode_raw, baseline_raw, prior_raw = sys.argv[1:5]


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def normalize(value: str) -> str:
    return value.strip()


def is_repo_relative_markdown_path(value: str) -> bool:
    if not value:
        return False
    pure = PurePosixPath(value)
    return not pure.is_absolute() and ".." not in pure.parts and value.startswith("docs/") and pure.suffix == ".md"


def validate_pointer(label: str, value: str) -> str:
    if not is_repo_relative_markdown_path(value):
        fail(f"ERROR: {label} must be a repo-relative `docs/*.md` path, got: {value or '<empty>'}")
    fs_path = Path(root, value)
    if not fs_path.exists():
        fail(f"ERROR: {label} does not exist: {value}")
    return value


mode = normalize(mode_raw).lower()
baseline_artifact = normalize(baseline_raw)
prior_artifacts_raw = normalize(prior_raw)

if not any((mode, baseline_artifact, prior_artifacts_raw)):
    print(
        json.dumps(
            {
                "active": False,
                "mode": None,
                "baseline_artifact": None,
                "prior_artifacts": [],
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0)

if mode not in {"incremental", "full"}:
    fail("ERROR: PLANVEYOR_REVIEW_RERUN_MODE must be `incremental` or `full` when explicit rerun carrier is used.")

if baseline_artifact:
    baseline_artifact = validate_pointer("PLANVEYOR_REVIEW_BASELINE_ARTIFACT", baseline_artifact)

if mode == "incremental" and not baseline_artifact:
    fail("ERROR: PLANVEYOR_REVIEW_BASELINE_ARTIFACT is required when PLANVEYOR_REVIEW_RERUN_MODE=incremental.")

prior_artifacts: list[str] = []
seen: set[str] = set()
if prior_artifacts_raw:
    for raw_item in prior_artifacts_raw.split("|"):
        item = normalize(raw_item)
        if not item:
            fail("ERROR: PLANVEYOR_REVIEW_PRIOR_ARTIFACTS must be a `|`-delimited list without empty items.")
        item = validate_pointer("PLANVEYOR_REVIEW_PRIOR_ARTIFACTS item", item)
        if item in seen:
            continue
        seen.add(item)
        prior_artifacts.append(item)

if mode == "full" and not baseline_artifact and not prior_artifacts:
    fail(
        "ERROR: explicit rerun carrier is incomplete: `full` rerun needs "
        "PLANVEYOR_REVIEW_BASELINE_ARTIFACT or PLANVEYOR_REVIEW_PRIOR_ARTIFACTS."
    )

effective_prior_artifacts = prior_artifacts[:] if prior_artifacts else ([baseline_artifact] if baseline_artifact else [])
print(
    json.dumps(
        {
            "active": True,
            "mode": mode,
            "baseline_artifact": baseline_artifact or None,
            "prior_artifacts": effective_prior_artifacts,
        },
        ensure_ascii=False,
    )
)
PY
}

_planveyor_now_utc_iso() { TZ=UTC date "+%Y-%m-%dT%H:%M:%SZ"; }
_planveyor_run_receipt_path() {
  local receipt_key="${1:-}"
  [[ -n "${receipt_key//[[:space:]]/}" ]] || return 1
  local root=""
  root="$(_planveyor_project_root)" || return $?
  echo "${root}/.planveyor.run_receipt.${receipt_key}"
}
_planveyor_receipt_value_sanitize() {
  local value="${1:-}"
  value="${value//$'\r'/ }"
  value="${value//$'\n'/ }"
  value="${value//$'\t'/ }"
  while [[ "$value" == *"  "* ]]; do value="${value//  / }"; done
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}
_planveyor_result_artifact_for_plan() {
  local plan_path="${1:-}"
  local fallback="${2:-stdout receipt}"
  local artifact_rel=""
  artifact_rel="$(_planveyor_plan_review_artifact_path "$plan_path" 2>/dev/null || true)"
  if [[ -n "${artifact_rel//[[:space:]]/}" ]]; then
    echo "$artifact_rel"
  else
    echo "$fallback"
  fi
}
_planveyor_run_receipt_emit() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_run_receipt_emit)" || return $?
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
  # Separate run/verification receipt; `.planveyor.session.*` remains an attach pointer only.
  # Normalized envelope mapping for `.planveyor.run_receipt.*`:
  # - schema_version = runtime_receipt.v1
  # - event_type = run_receipt.<receipt_key>
  # - ts = literal `finished_at` (fallback `started_at` when `finished_at` is blank)
  # - trace_id = literal `thread_id` when available
  # - event_id/span_id = derived from `receipt_key` + `started_at`
  # - parent_span_id = N/A; `parent_thread_id` remains thread-lineage only
  local receipt_key="${1:-}"
  local thread_id="${2:-}"
  local parent_thread_id="${3:-}"
  local launch_surface="${4:-}"
  local pipeline_mode="${5:-}"
  local plan_path="${6:-}"
  local pre_status_line="${7:-}"
  local started_at="${8:-}"
  local finished_at="${9:-}"
  local result_artifact="${10:-stdout receipt}"
  local authority_context="${11:-}"
  [[ -n "${receipt_key//[[:space:]]/}" ]] || return 1

  case "$launch_surface" in
    codex_desktop|codex_cli|codex_exec|collab_subagent) ;;
    *) echo "Invalid launch_surface for run receipt: ${launch_surface}" >&2; return 1 ;;
  esac
  case "$pipeline_mode" in
    manual|manager_router|manager_custom_pipeline|collab|review_only) ;;
    *) echo "Invalid pipeline_mode for run receipt: ${pipeline_mode}" >&2; return 1 ;;
  esac

  if [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
    [[ -n "${authority_context//[[:space:]]/}" ]] || {
      echo "Refusing engaged run receipt without authority context" >&2
      return 1
    }
    authority_context="$(_planveyor_authority_bridge context-canonical --context "$authority_context")" || return $?
    [[ "$authority_context" == "$PLANVEYOR_CTX_JSON" ]] || {
      echo "Refusing run receipt whose authority context differs from this invocation" >&2
      return 1
    }
  elif [[ -n "${authority_context//[[:space:]]/}" ]]; then
    echo "Refusing legacy run receipt with an authority context" >&2
    return 1
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local file_path=""
  file_path="$(_planveyor_run_receipt_path "$receipt_key")" || return 1
  local cwd="$PWD"
  local worktree_id=""
  worktree_id="$(_planveyor_worktree_id 2>/dev/null || true)"

  local thread_id_clean=""
  local parent_thread_id_clean=""
  local plan_path_clean=""
  local pre_status_line_clean=""
  local started_at_clean=""
  local finished_at_clean=""
  local receipt_ts_clean=""
  local receipt_event_type=""
  local receipt_schema_version="runtime_receipt.v1"
  local result_artifact_clean=""
  thread_id_clean="$(_planveyor_receipt_value_sanitize "$thread_id")"
  parent_thread_id_clean="$(_planveyor_receipt_value_sanitize "$parent_thread_id")"
  plan_path_clean="$(_planveyor_receipt_value_sanitize "$plan_path")"
  pre_status_line_clean="$(_planveyor_receipt_value_sanitize "$pre_status_line")"
  started_at_clean="$(_planveyor_receipt_value_sanitize "$started_at")"
  finished_at_clean="$(_planveyor_receipt_value_sanitize "$finished_at")"
  receipt_ts_clean="$finished_at_clean"
  [[ -n "${receipt_ts_clean//[[:space:]]/}" ]] || receipt_ts_clean="$started_at_clean"
  receipt_event_type="run_receipt.${receipt_key}"
  result_artifact_clean="$(_planveyor_receipt_value_sanitize "$result_artifact")"

  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  if ! _planveyor_py_any - "$file_path" "$finished_at_clean" "$receipt_schema_version" \
    "$receipt_event_type" "$receipt_ts_clean" "$thread_id_clean" \
    "$parent_thread_id_clean" "$cwd" "$root" "$worktree_id" "$launch_surface" \
    "$pipeline_mode" "$plan_path_clean" "$pre_status_line_clean" \
    "$started_at_clean" "$result_artifact_clean" "$authority_context" <<'PY'
import errno
import os
from pathlib import Path
import sys
import tempfile

(
    path_raw,
    finished_at,
    schema_version,
    event_type,
    receipt_ts,
    thread_id,
    parent_thread_id,
    cwd,
    repo_root,
    worktree_id,
    launch_surface,
    pipeline_mode,
    plan_path,
    pre_status_line,
    started_at,
    result_artifact,
    authority_context,
) = sys.argv[1:]
path = Path(path_raw)
content = (
    f"# {finished_at}\n"
    f"schema_version={schema_version}\n"
    f"event_type={event_type}\n"
    f"ts={receipt_ts}\n"
    f"thread_id={thread_id}\n"
    f"parent_thread_id={parent_thread_id}\n"
    f"cwd={cwd}\n"
    f"repo_root={repo_root}\n"
    f"worktree_id={worktree_id}\n"
    f"launch_surface={launch_surface}\n"
    f"pipeline_mode={pipeline_mode}\n"
    f"plan_path={plan_path}\n"
    f"pre_status_line={pre_status_line}\n"
    f"started_at={started_at}\n"
    f"finished_at={finished_at}\n"
    f"result_artifact={result_artifact}\n"
    + (f"authority_context={authority_context}\n" if authority_context else "")
)
temp_path: str | None = None
try:
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=str(path.parent),
    )
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)
    temp_path = None
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path.parent, flags)
    try:
        try:
            os.fsync(directory_fd)
        except OSError as exc:
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                raise
    finally:
        os.close(directory_fd)
except OSError:
    if temp_path is not None:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
    raise SystemExit(1)
PY
  then
    echo "Failed to save run receipt: ${file_path}" >&2
    return 1
  fi

  echo "Saved run receipt: ${file_path}" >&2
}

_planveyor_manager_invocation_id() {
  printf '%s_%s_%s\n' "$(TZ=UTC date '+%Y%m%dT%H%M%SZ')" "$$" "${RANDOM}${RANDOM}"
}

_planveyor_manager_invocation_receipt_path() {
  local invocation_id="${1:-}"
  [[ "$invocation_id" =~ '^[A-Za-z0-9][A-Za-z0-9_.-]{7,127}$' ]] || return 1
  local root=""
  root="$(_planveyor_project_root)" || return $?
  printf '%s/.planveyor.manager_runs/%s.json\n' "$root" "$invocation_id"
}

_planveyor_manager_invocation_receipt_mutate() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_manager_invocation_receipt_mutate)" || return $?
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
  local operation="${1:-}"
  local receipt_path="${2:-}"
  local invocation_id="${3:-}"
  shift 3 || true
  local root="$PLANVEYOR_CTX_ROOT"
  local worktree_id=""
  worktree_id="$(_planveyor_worktree_id 2>/dev/null || true)"
  if [[ "$operation" != read ]]; then
    _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  fi
  _planveyor_py_any - "$operation" "$root" "$receipt_path" "$invocation_id" "$worktree_id" "$@" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

operation, root_raw, path_raw, invocation_id, worktree_id, *args = sys.argv[1:]
root = Path(root_raw).resolve()
receipt_root = root / ".planveyor.manager_runs"
expected_path = receipt_root / f"{invocation_id}.json"
path = Path(path_raw)


def fail(reason: str, *, mutation_performed: bool = False) -> None:
    print(json.dumps({
        "ok": False,
        "reason_code": reason,
        "invocation_id": invocation_id or None,
        "receipt_path": str(path) if path_raw else None,
        "mutation_performed": mutation_performed,
    }, sort_keys=True))
    raise SystemExit(125)


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,127}", invocation_id):
    fail("invalid_invocation_id")
if not path.is_absolute():
    path = root / path
try:
    if path.parent.resolve() != receipt_root.resolve() or path.name != expected_path.name:
        fail("invalid_receipt_path")
except OSError:
    fail("invalid_receipt_path")


def open_root() -> int:
    if not receipt_root.exists():
        old_umask = os.umask(0o077)
        try:
            receipt_root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        finally:
            os.umask(old_umask)
    try:
        root_stat = os.lstat(receipt_root)
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            fail("unsafe_receipt_root")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        dir_fd = os.open(receipt_root, flags)
        opened_stat = os.fstat(dir_fd)
        if (opened_stat.st_dev, opened_stat.st_ino) != (
            root_stat.st_dev,
            root_stat.st_ino,
        ):
            os.close(dir_fd)
            fail("receipt_root_replaced")
        os.fchmod(dir_fd, 0o700)
        return dir_fd
    except OSError:
        fail("unsafe_receipt_root")


loaded_identity: tuple[int, int] | None = None

STOP_REASON_CODES = {
    "terminal_status", "queue_empty", "manager_mode_mismatch", "owner_questions_open",
    "oracle_failed", "unknown_status", "dirty_state_blocked", "missing_role_session_id",
    "role_helper_failed", "censor_incomplete", "reviewer_evidence_incomplete",
    "operational_retry", "semantic_blocker", "progress_with_artifact",
    "fixed_blocker_lineage", "historical_context", "real_loop", "unknown",
    "max_iterations_reached", "unknown_command",
}
BLOCKED_REASON_CODES = {
    "manager_mode_rejected", "manager_process_failed", "prompt_body_binding_changed",
    "stop_checkpoint_missing", "stop_checkpoint_invalid", "terminal_readback_failed",
    "compatibility_pointer_write_failed",
}
IMMUTABLE_IDENTITY_FIELDS = (
    "schema", "invocation_id", "receipt_path", "repo_root", "worktree_id",
    "manager_sid", "command", "pipeline_mode", "started_at", "initial_plan",
)


def immutable_identity_digest(payload: dict[str, object]) -> str:
    fields = IMMUTABLE_IDENTITY_FIELDS
    # Legacy receipts predate authority context.  Keep their historical digest
    # byte-compatible while binding a new engaged receipt to its exact compact
    # envelope when that optional field is present.
    if "authority_context" in payload:
        fields = (*fields, "authority_context")
    encoded = json.dumps(
        {key: payload.get(key) for key in fields},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def valid_authority_context(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    schema = value.get("schema_version")
    if schema not in ("planveyor_contract_context.v1", "planveyor_contract_context.v2", "planveyor_contract_context.v3") or value.get("state") != "engaged":
        return False
    if schema in ("planveyor_contract_context.v2", "planveyor_contract_context.v3") and value.get("entry_observation_provenance") not in (
        "observed_local", "inherited_supplied_unverified",
    ):
        return False
    for key in ("project_root", "generation_sha256", "context_sha256"):
        if not isinstance(value.get(key), str) or not str(value.get(key)).strip():
            return False
    runtime_pin = value.get("runtime_pin")
    return isinstance(runtime_pin, dict) and isinstance(runtime_pin.get("pin_sha256"), str)


def valid_source_refs(source_refs: object) -> bool:
    if not isinstance(source_refs, list) or not source_refs or len(source_refs) > 16:
        return False
    for raw_ref in source_refs:
        if not isinstance(raw_ref, str):
            return False
        source_path = raw_ref.split("#", 1)[0]
        if (
            not raw_ref.strip()
            or not source_path
            or len(raw_ref) > 500
            or "\n" in raw_ref
            or "\r" in raw_ref
            or source_path.startswith("/")
            or ".." in Path(source_path).parts
        ):
            return False
    return True


def validate_phase(payload: dict[str, object]) -> None:
    state = payload.get("state")
    reason_code = payload.get("reason_code")
    checkpoint_state = payload.get("stop_checkpoint_state")
    stop_reason = payload.get("stop_reason_code")
    source_refs = payload.get("stop_source_refs")
    pointer_state = payload.get("compatibility_pointer_state")
    for key in ("initial_plan", "active_plan", "final_plan"):
        if payload.get(key) is not None and not isinstance(payload.get(key), str):
            fail("receipt_phase_invalid")
    if checkpoint_state == "missing":
        if stop_reason is not None or source_refs != []:
            fail("stop_checkpoint_invalid")
    elif checkpoint_state == "recorded":
        if stop_reason not in STOP_REASON_CODES or not valid_source_refs(source_refs):
            fail("stop_checkpoint_invalid")
    else:
        fail("stop_checkpoint_invalid")

    if state == "running":
        if (
            reason_code != "manager_process_running"
            or payload.get("active_plan") != payload.get("initial_plan")
            or payload.get("final_plan") is not None
            or payload.get("finished_at") is not None
            or payload.get("manager_exit_code") is not None
            or pointer_state != "not_attempted"
            or payload.get("blocker") is not None
            or payload.get("result_artifact") is not None
        ):
            fail("receipt_phase_invalid")
        return

    if state not in {"completed", "blocked", "interrupted"}:
        fail("receipt_phase_invalid")
    if not isinstance(payload.get("finished_at"), str) or not str(payload.get("finished_at")).strip():
        fail("receipt_phase_invalid")
    if payload.get("manager_exit_code") is not None and not isinstance(
        payload.get("manager_exit_code"), int
    ):
        fail("receipt_phase_invalid")
    if pointer_state not in {"not_attempted", "updated", "write_failed"}:
        fail("receipt_phase_invalid")
    for key in ("oracle_readback", "queue_readback", "worktree_state", "closeout_state"):
        if not isinstance(payload.get(key), dict):
            fail("receipt_phase_invalid")

    expected_reason = {
        "completed": {"manager_process_exited"},
        "interrupted": {"manager_process_interrupted"},
        "blocked": BLOCKED_REASON_CODES,
    }[state]
    if reason_code not in expected_reason:
        fail("receipt_phase_invalid")
    if state == "completed":
        if (
            payload.get("manager_exit_code") != 0
            or checkpoint_state != "recorded"
            or payload.get("blocker") is not None
        ):
            fail("receipt_phase_invalid")
    elif not isinstance(payload.get("blocker"), dict):
        fail("receipt_phase_invalid")
    if reason_code == "manager_process_interrupted":
        exit_code = payload.get("manager_exit_code")
        if not isinstance(exit_code, int) or exit_code < 128:
            fail("receipt_phase_invalid")
    if reason_code == "manager_process_failed" and payload.get("manager_exit_code") in {None, 0}:
        fail("receipt_phase_invalid")
    if reason_code == "stop_checkpoint_missing" and checkpoint_state != "missing":
        fail("receipt_phase_invalid")
    if pointer_state == "write_failed" and (
        state != "blocked" or reason_code != "compatibility_pointer_write_failed"
    ):
        fail("receipt_phase_invalid")
    if reason_code == "compatibility_pointer_write_failed" and pointer_state != "write_failed":
        fail("receipt_phase_invalid")


def load() -> dict[str, object]:
    global loaded_identity
    dir_fd = open_root()
    try:
        current_stat = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
        mode = current_stat.st_mode
        if (
            stat.S_ISLNK(mode)
            or not stat.S_ISREG(mode)
            or stat.S_IMODE(mode) != 0o600
        ):
            fail("unsafe_receipt_path")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path.name, flags, dir_fd=dir_fd)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            opened_stat = os.fstat(handle.fileno())
            if (opened_stat.st_dev, opened_stat.st_ino) != (
                current_stat.st_dev,
                current_stat.st_ino,
            ):
                fail("receipt_replaced_before_readback")
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        fail("receipt_readback_failed")
    finally:
        os.close(dir_fd)
    if not isinstance(payload, dict):
        fail("receipt_readback_failed")
    expected = {
        "schema": "manager_invocation_receipt.v1",
        "invocation_id": invocation_id,
        "receipt_path": str(path),
        "repo_root": str(root),
        "worktree_id": worktree_id,
        "pipeline_mode": "manager_custom_pipeline",
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        fail("immutable_identity_mismatch")
    if (
        payload.get("command") not in {"interactive", "run", "run_q"}
        or not isinstance(payload.get("manager_sid"), str)
        or not str(payload.get("manager_sid")).strip()
        or not isinstance(payload.get("started_at"), str)
        or not str(payload.get("started_at")).strip()
    ):
        fail("immutable_identity_mismatch")
    if payload.get("immutable_identity_sha256") != immutable_identity_digest(payload):
        fail("immutable_identity_mismatch")
    if "authority_context" in payload and not valid_authority_context(payload.get("authority_context")):
        fail("immutable_identity_mismatch")
    validate_phase(payload)
    loaded_identity = (current_stat.st_dev, current_stat.st_ino)
    return payload


def publish(payload: dict[str, object], *, exclusive: bool = False) -> None:
    validate_phase(payload)
    dir_fd = open_root()
    old_umask = os.umask(0o077)
    temp_name = f".{invocation_id}.tmp-{secrets.token_hex(12)}"
    temp_created = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temp_name, flags, 0o600, dir_fd=dir_fd)
        temp_created = True
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            try:
                os.link(
                    temp_name,
                    path.name,
                    src_dir_fd=dir_fd,
                    dst_dir_fd=dir_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                fail("receipt_already_exists")
            os.unlink(temp_name, dir_fd=dir_fd)
            temp_created = False
        else:
            try:
                current_stat = os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError:
                fail("receipt_replaced_before_mutation")
            if (
                loaded_identity is None
                or stat.S_ISLNK(current_stat.st_mode)
                or not stat.S_ISREG(current_stat.st_mode)
                or (current_stat.st_dev, current_stat.st_ino) != loaded_identity
            ):
                fail("receipt_replaced_before_mutation")
            os.replace(
                temp_name,
                path.name,
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            temp_created = False
        os.fsync(dir_fd)
    except OSError:
        fail("receipt_atomic_write_failed")
    finally:
        os.umask(old_umask)
        if temp_created:
            try:
                os.unlink(temp_name, dir_fd=dir_fd)
            except OSError:
                pass
        os.close(dir_fd)


if operation == "seed":
    if len(args) not in {4, 5}:
        fail("internal_error")
    manager_sid, command, initial_plan, started_at, *authority_args = args
    if (
        command not in {"interactive", "run", "run_q"}
        or not manager_sid.strip()
        or not started_at.strip()
    ):
        fail("invalid_seed_identity")
    authority_context: dict[str, object] | None = None
    if authority_args:
        try:
            decoded_authority = json.loads(authority_args[0])
        except (TypeError, ValueError, json.JSONDecodeError):
            fail("invalid_seed_authority_context")
        if not valid_authority_context(decoded_authority):
            fail("invalid_seed_authority_context")
        authority_context = decoded_authority
    payload: dict[str, object] = {
        "schema": "manager_invocation_receipt.v1",
        "invocation_id": invocation_id,
        "receipt_path": str(path),
        "repo_root": str(root),
        "worktree_id": worktree_id,
        "manager_sid": manager_sid,
        "command": command,
        "pipeline_mode": "manager_custom_pipeline",
        "started_at": started_at,
        "initial_plan": initial_plan or None,
        "active_plan": initial_plan or None,
        "final_plan": None,
        "finished_at": None,
        "state": "running",
        "reason_code": "manager_process_running",
        "manager_exit_code": None,
        "stop_checkpoint_state": "missing",
        "stop_reason_code": None,
        "stop_source_refs": [],
        "oracle_readback": {"state": "not_applicable", "reason": "not_finalized"},
        "queue_readback": {"state": "not_applicable", "reason": "not_finalized"},
        "last_commit": None,
        "worktree_state": {"state": "not_evaluated"},
        "closeout_state": {"state": "not_evaluated"},
        "blocker": None,
        "result_artifact": None,
        "compatibility_pointer_state": "not_attempted",
    }
    if authority_context is not None:
        payload["authority_context"] = authority_context
    payload["immutable_identity_sha256"] = immutable_identity_digest(payload)
    publish(payload, exclusive=True)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0)

payload = load()

if operation == "checkpoint":
    if len(args) < 2:
        fail("checkpoint_invalid")
    reason_code, *source_refs = args
    if payload.get("state") != "running":
        fail("checkpoint_not_running")
    if payload.get("stop_checkpoint_state") != "missing":
        fail("checkpoint_already_recorded")
    if reason_code not in STOP_REASON_CODES or not valid_source_refs(source_refs):
        fail("checkpoint_invalid")
    payload["stop_checkpoint_state"] = "recorded"
    payload["stop_reason_code"] = reason_code
    payload["stop_source_refs"] = source_refs
    publish(payload)
elif operation == "finalize":
    if len(args) != 11:
        fail("internal_error")
    (
        state, reason_code, manager_exit_code, active_plan, final_plan,
        oracle_json, queue_json, last_commit, worktree_json, closeout_json,
        result_artifact,
    ) = args
    if payload.get("state") != "running":
        fail("receipt_not_running")
    if state not in {"completed", "blocked", "interrupted"}:
        fail("invalid_terminal_state")
    allowed_reasons = {
        "manager_process_exited", "manager_process_interrupted", *BLOCKED_REASON_CODES,
    }
    if reason_code not in allowed_reasons:
        fail("invalid_terminal_reason")
    try:
        exit_code: int | None = int(manager_exit_code) if manager_exit_code else None
    except (TypeError, ValueError):
        fail("invalid_terminal_readback_manager_exit_code")
    decoded: dict[str, object] = {}
    for label, raw in (
        ("oracle", oracle_json),
        ("queue", queue_json),
        ("worktree", worktree_json),
        ("closeout", closeout_json),
    ):
        try:
            decoded[label] = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            fail(f"invalid_terminal_readback_{label}")
    oracle_readback = decoded["oracle"]
    queue_readback = decoded["queue"]
    worktree_state = decoded["worktree"]
    closeout_state = decoded["closeout"]
    payload.update({
        "active_plan": active_plan or None,
        "final_plan": final_plan or active_plan or None,
        "finished_at": now(),
        "state": state,
        "reason_code": reason_code,
        "manager_exit_code": exit_code,
        "oracle_readback": oracle_readback,
        "queue_readback": queue_readback,
        "last_commit": last_commit or None,
        "worktree_state": worktree_state,
        "closeout_state": closeout_state,
        "blocker": None if state == "completed" else {
            "reason_code": reason_code,
            "stop_reason_code": payload.get("stop_reason_code"),
            "source_refs": payload.get("stop_source_refs", []),
        },
        "result_artifact": result_artifact or None,
    })
    publish(payload)
elif operation == "pointer":
    if len(args) != 1 or args[0] not in {"updated", "write_failed"}:
        fail("invalid_pointer_state")
    if payload.get("state") == "running":
        fail("receipt_not_terminal")
    pointer_state = args[0]
    payload["compatibility_pointer_state"] = pointer_state
    if pointer_state == "write_failed":
        payload["state"] = "blocked"
        payload["reason_code"] = "compatibility_pointer_write_failed"
        payload["blocker"] = {
            "reason_code": "compatibility_pointer_write_failed",
            "stop_reason_code": payload.get("stop_reason_code"),
            "source_refs": payload.get("stop_source_refs", []),
        }
    publish(payload)
elif operation == "read":
    if len(args) > 1:
        fail("internal_error")
    require_terminal = bool(args and args[0] == "terminal")
    if require_terminal and payload.get("state") not in {"completed", "blocked", "interrupted"}:
        fail("receipt_not_terminal")
    if require_terminal:
        required_fields = {
            "initial_plan", "active_plan", "final_plan", "finished_at", "state",
            "reason_code", "manager_exit_code", "stop_checkpoint_state",
            "stop_reason_code", "stop_source_refs", "oracle_readback",
            "queue_readback", "last_commit", "worktree_state", "closeout_state",
            "blocker", "result_artifact", "compatibility_pointer_state",
        }
        if not required_fields.issubset(payload):
            fail("receipt_terminal_fields_missing")
        if payload.get("compatibility_pointer_state") not in {"updated", "write_failed"}:
            fail("receipt_terminal_pointer_state_invalid")
else:
    fail("internal_error")

print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
}

_planveyor_manager_invocation_receipt_seed() {
  local invocation_id="${1:-}"
  local receipt_path="${2:-}"
  local manager_sid="${3:-}"
  local command="${4:-}"
  local initial_plan="${5:-}"
  local started_at="${6:-}"
  local authority_context="${7:-}"
  local current_context=""
  current_context="$(_planveyor_authority_context_for_reader _planveyor_manager_invocation_receipt_seed)" || return $?
  local current_state=""
  current_state="$(_planveyor_authority_context_field "$current_context" state)" || return $?
  if [[ "$current_state" == engaged ]]; then
    [[ -n "${authority_context//[[:space:]]/}" ]] || {
      echo "Refusing engaged manager receipt seed without authority context" >&2
      return 1
    }
    authority_context="$(_planveyor_authority_bridge context-canonical --context "$authority_context")" || return $?
    [[ "$authority_context" == "$current_context" ]] || {
      echo "Refusing manager receipt seed whose authority context differs from this invocation" >&2
      return 1
    }
    _planveyor_manager_invocation_receipt_mutate seed "$receipt_path" "$invocation_id" \
      "$manager_sid" "$command" "$initial_plan" "$started_at" "$authority_context"
    return $?
  fi
  [[ -z "${authority_context//[[:space:]]/}" ]] || {
    echo "Refusing legacy manager receipt seed with an authority context" >&2
    return 1
  }
  _planveyor_manager_invocation_receipt_mutate seed "$receipt_path" "$invocation_id" \
    "$manager_sid" "$command" "$initial_plan" "$started_at"
}

_planveyor_manager_invocation_receipt_checkpoint() {
  local receipt_path="${1:-}"
  local invocation_id="${2:-}"
  local reason_code="${3:-}"
  shift 3 || true
  _planveyor_manager_invocation_receipt_mutate checkpoint "$receipt_path" "$invocation_id" \
    "$reason_code" "$@"
}

_planveyor_manager_invocation_receipt_finalize() {
  local receipt_path="${1:-}"
  local invocation_id="${2:-}"
  shift 2 || true
  _planveyor_manager_invocation_receipt_mutate finalize "$receipt_path" "$invocation_id" "$@"
}

_planveyor_manager_invocation_receipt_pointer() {
  _planveyor_manager_invocation_receipt_mutate pointer "${1:-}" "${2:-}" "${3:-}"
}

_planveyor_manager_invocation_receipt_read() {
  _planveyor_manager_invocation_receipt_mutate read "${1:-}" "${2:-}" "${3:-}"
}

_planveyor_rejected_baseline() {
  local action="${1:-}"
  local plan_path="${2:-}"
  local recovery_plan="${3:-}"
  local root="${4:-$(_planveyor_root)}"
  local tooling_root="${5:-$(_planveyor_root)}"
  _planveyor_py_any_authority_stdin "$action" "$plan_path" "$recovery_plan" "$root" "$tooling_root" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

action, plan_arg, recovery_arg, root_arg, tooling_arg = sys.argv[1:6]
root = Path(root_arg).resolve()
tooling = Path(tooling_arg).resolve()
source_rel = Path(plan_arg).as_posix()
source = (root / source_rel).resolve()
ZERO_OID = "0" * 40
MANIFEST_SCHEMA = "planveyor_rejected_baseline.v1"
CLEANUP_SCHEMA = "planveyor_rejected_baseline_cleanup.v1"


class RecoveryError(RuntimeError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def fail(reason_code: str, message: str) -> None:
    raise RecoveryError(reason_code, message)


tooling_scripts = tooling / "scripts"
if str(tooling_scripts) not in sys.path:
    sys.path.insert(0, str(tooling_scripts))
try:
    from fs_object_identity import (
        ObjectIdentityError,
        ObjectSnapshot,
        snapshot_regular_or_absent,
    )
    from plan_status_oracle import (
        AcceptedRedDurableValidationError,
        AcceptedRedDurableRefResult,
        CurrentOpenBlockerError,
        accepted_red_git_env,
        assert_accepted_red_clean_git_authority_environment,
        accepted_red_topology_open_blocker_ids,
        current_open_blocker_ids,
        parse_accepted_red_recovery_contract,
        resolve_accepted_red_review_path,
        successor_inherited_blocker_ids,
        validate_accepted_red_capture_commit,
        validate_accepted_red_cleanup_candidate,
        validate_accepted_red_durable_ref,
        validate_accepted_red_successor_topology_rebind,
    )
    from review_target_snapshot import (
        HASH_BASIS_SCHEMA_VERSION,
        SnapshotError,
        validate_snapshot_payload,
    )
except (ImportError, OSError) as exc:
    fail("routing_contract_invalid", f"cannot load accepted-red tooling authority: {exc}")


def git_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = accepted_red_git_env()
    if overrides is not None:
        env.update(overrides)
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def git(
    *args: str,
    env: dict[str, str] | None = None,
    check: bool = True,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        input=input_bytes,
        capture_output=True,
        env=git_env(env),
        check=False,
    )
    if check and proc.returncode:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        fail("git_command_failed", f"git {' '.join(args)}: {detail}")
    return proc


def git_text(*args: str, env: dict[str, str] | None = None) -> str:
    return git(*args, env=env).stdout.decode("utf-8", "strict").strip()


def canonical_json(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_oid(data: bytes) -> str:
    proc = git("hash-object", "--stdin", input_bytes=data, check=False)
    if proc.returncode:
        fail("git_command_failed", proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout.decode("ascii", "strict").strip()


def fenced_json(text: str, key: str) -> dict[str, object]:
    for raw in re.findall(r"```json\s*([\s\S]*?)```", text):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get(key), dict):
            return value[key]
    fail("routing_contract_invalid", f"missing {key} JSON")


def path_components_are_symlink_free(rel: str, *, include_leaf: bool = True) -> bool:
    lexical = Path(rel)
    if lexical.is_absolute() or not lexical.parts or any(part in {".", ".."} for part in lexical.parts):
        return False
    current = root
    parts = lexical.parts if include_leaf else lexical.parts[:-1]
    for part in parts:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if stat.S_ISLNK(mode):
            return False
    return True


def repo_rel(path: Path) -> str:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        fail("routing_contract_invalid", f"path escapes repository: {path}")
    if not path_components_are_symlink_free(rel, include_leaf=False):
        fail("routing_contract_invalid", f"path contains a symlinked component: {rel}")
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        fail("routing_contract_invalid", f"path escapes repository: {path}")


def regular_bytes(rel: str) -> tuple[bytes, str]:
    path = root / rel
    if not path.is_file() or path.is_symlink():
        fail("target_missing", f"required regular path is missing: {rel}")
    data = path.read_bytes()
    mode = "100755" if path.stat().st_mode & stat.S_IXUSR else "100644"
    return data, mode


def tree_record(revision: str, rel: str) -> dict[str, object] | None:
    probe = git("cat-file", "-e", f"{revision}:{rel}", check=False)
    if probe.returncode:
        return None
    data = git("show", f"{revision}:{rel}").stdout
    mode = git_text("ls-tree", revision, "--", rel).split()[0]
    return {
        "state": "head",
        "sha256": sha256(data),
        "size_bytes": len(data),
        "mode": mode,
        "blob_oid": git_text("rev-parse", f"{revision}:{rel}"),
        "_bytes": data,
    }


def head_record(rel: str) -> dict[str, object] | None:
    return tree_record("HEAD", rel)


def blob_record_from_bytes(
    rel: str,
    data: bytes,
    mode: str,
    *,
    write: bool = True,
) -> dict[str, object]:
    oid = git_blob_oid(data)
    if write:
        proc = git("hash-object", "-w", "--stdin", input_bytes=data, check=False)
        if proc.returncode:
            fail("git_command_failed", proc.stderr.decode("utf-8", "replace").strip())
        if proc.stdout.decode().strip() != oid:
            fail("git_command_failed", f"Git blob identity changed while writing: {rel}")
    return {
        "path": rel,
        "sha256": sha256(data),
        "size_bytes": len(data),
        "mode": mode,
        "blob_oid": oid,
    }


def blob_record(rel: str) -> dict[str, object]:
    data, mode = regular_bytes(rel)
    return blob_record_from_bytes(rel, data, mode)


def carrier_text(rel: str, revision: str | None = None) -> str:
    if revision is None:
        data, _mode = regular_bytes(rel)
    else:
        record = tree_record(revision, rel)
        if record is None:
            fail("routing_contract_invalid", f"missing carrier at {revision}: {rel}")
        data = record["_bytes"]
    try:
        return data.decode("utf-8", "strict")
    except UnicodeDecodeError:
        fail("routing_contract_invalid", f"carrier is not UTF-8: {rel}")


def run_current_bundle_producer() -> dict[str, object]:
    import contract_authority_context as authority_context
    from contract_authority_children import AuthorityChildLaunchError, python_entry_argv

    helper = tooling / "scripts" / "review_target_snapshot.py"
    entry_args = [source_rel, "--current-bundle", "--project-root", str(root)]
    child_env = git_env()
    try:
        child_context = authority_context.context_for_reader(root)
        if child_context.state == "engaged":
            command = python_entry_argv(child_context, helper, entry_args)
            child_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = authority_context.context_to_json(child_context)
        else:
            command = [sys.executable, "-B", str(helper), *entry_args]
    except (authority_context.ContractAuthorityError, AuthorityChildLaunchError) as exc:
        fail("snapshot_invalid", f"authority child launch was rejected: {exc}")
    proc = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=child_env,
    )
    if proc.returncode:
        fail("snapshot_invalid", proc.stderr.strip() or proc.stdout.strip())
    try:
        snapshot = json.loads(proc.stdout)
    except json.JSONDecodeError:
        fail("snapshot_invalid", "snapshot helper returned invalid JSON")
    if not isinstance(snapshot, dict):
        fail("snapshot_invalid", "snapshot helper returned a non-object payload")
    try:
        return validate_snapshot_payload(snapshot)
    except SnapshotError as exc:
        fail("snapshot_invalid", str(exc))


def retained_target_snapshots(
    targets: list[str],
    *,
    producer_bundle_sha: str,
    review_sha: str,
    snapshot_bridge: dict[str, object] | None,
) -> dict[str, ObjectSnapshot]:
    snapshots = {
        rel: active_target_snapshot(rel, failure_reason="snapshot_invalid")
        for rel in targets
    }
    if any(
        snapshot.state != "regular"
        or snapshot.data is None
        or snapshot.git_mode is None
        for snapshot in snapshots.values()
    ):
        fail("snapshot_invalid", "accepted-red capture targets must be regular files")
    files = [
        {
            "git_mode": snapshots[rel].git_mode,
            "path": rel,
            "sha256": sha256(snapshots[rel].data),
            "size_bytes": len(snapshots[rel].data),
        }
        for rel in targets
    ]
    hash_basis_payload = {
        "algorithm": "sha256",
        "files": files,
        "schema_version": HASH_BASIS_SCHEMA_VERSION,
    }
    local_bundle_sha = sha256(
        json.dumps(
            hash_basis_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if producer_bundle_sha == review_sha and local_bundle_sha == review_sha:
        return snapshots
    if snapshot_bridge is None:
        fail(
            "snapshot_mismatch",
            "fd-anchored target snapshot differs from historical red review",
        )
    if (
        snapshot_bridge.get("review_bundle_sha256") != review_sha
        or snapshot_bridge.get("current_bundle_sha256") != producer_bundle_sha
        or local_bundle_sha != producer_bundle_sha
    ):
        fail(
            "snapshot_bridge_mismatch",
            "accepted-red snapshot bridge does not match current and historical bundle identities",
        )
    expected_bridge_targets = [
        {
            "path": rel,
            "sha256": sha256(snapshots[rel].data),
            "size_bytes": len(snapshots[rel].data),
            "git_mode": snapshots[rel].git_mode,
            "git_blob_oid": git_blob_oid(snapshots[rel].data),
        }
        for rel in targets
    ]
    if snapshot_bridge.get("targets") != expected_bridge_targets:
        fail(
            "snapshot_bridge_mismatch",
            "accepted-red snapshot bridge target inventory differs from fd-anchored snapshots",
        )
    legacy_hash_basis_payload = {
        "algorithm": "sha256",
        "files": [
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
            }
            for item in expected_bridge_targets
        ],
        "schema_version": "review_target_snapshot.hash_basis.v1",
    }
    legacy_bundle_sha = sha256(
        json.dumps(
            legacy_hash_basis_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if legacy_bundle_sha != review_sha:
        fail(
            "snapshot_bridge_mismatch",
            "accepted-red snapshot bridge does not reproduce the historical review identity",
        )
    return snapshots


def parse_source(
    *,
    require_snapshot: bool,
    carrier_commit: str | None = None,
) -> dict[str, object]:
    try:
        assert_accepted_red_clean_git_authority_environment()
    except AcceptedRedDurableValidationError as exc:
        fail("not_accepted_red", str(exc))
    if carrier_commit is None and not source.is_file():
        fail("routing_contract_invalid", f"missing source plan: {source_rel}")
    source_text = carrier_text(source_rel, carrier_commit)
    status_match = re.search(r"^\*\*Status:\*\*\s*(.+?)\s*$", source_text, re.MULTILINE)
    if not status_match or status_match.group(1).strip() != "Superseded":
        fail("not_accepted_red", "source status is not Superseded")
    meta = fenced_json(source_text, "plan_meta")
    scope = meta.get("scope_expansion")
    if not isinstance(scope, dict) or scope.get("state") != "architect_accepted":
        fail("not_accepted_red", "scope expansion is not architect_accepted")
    next_plans = meta.get("next_plans")
    if not isinstance(next_plans, list) or len(next_plans) != 1 or not isinstance(next_plans[0], str):
        fail("not_accepted_red", "accepted-red source must have one successor")
    successor_rel = Path(next_plans[0]).as_posix()
    successor = root / successor_rel
    if carrier_commit is None and not successor.is_file():
        fail("routing_contract_invalid", f"missing successor: {successor_rel}")
    successor_text = carrier_text(successor_rel, carrier_commit)
    successor_meta = fenced_json(successor_text, "plan_meta")
    topology_rebind = False
    if successor_meta.get("parent") != source_rel:
        try:
            validate_accepted_red_successor_topology_rebind(
                root,
                source_rel,
                source_text,
                successor_rel,
                successor_text,
            )
        except AcceptedRedDurableValidationError:
            fail("not_accepted_red", "successor backlink does not match source")
        topology_rebind = True

    stem = source.stem
    draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
    try:
        review_rel = resolve_accepted_red_review_path(
            root,
            source_rel,
            plan_text=source_text,
            carrier_commit=carrier_commit,
        )
    except AcceptedRedDurableValidationError as exc:
        fail("routing_contract_invalid", str(exc))
    draft = root / draft_rel
    if carrier_commit is None and not draft.is_file():
        fail("routing_contract_invalid", "source draft or review is missing")
    draft_meta = fenced_json(carrier_text(draft_rel, carrier_commit), "code_draft_meta")
    if draft_meta.get("plan") != source_rel:
        fail("routing_contract_invalid", "source draft plan identity mismatch")
    targets_raw = draft_meta.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        fail("routing_contract_invalid", "source draft has no targets")
    targets: list[str] = []
    for item in targets_raw:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            fail("routing_contract_invalid", "invalid source target record")
        rel = Path(item["path"]).as_posix()
        repo_rel(root / rel)
        targets.append(rel)
    if len(set(targets)) != len(targets):
        fail("routing_contract_invalid", "duplicate source targets")

    review_text = carrier_text(review_rel, carrier_commit)
    target_match = re.search(
        r"^\*\*Target:\*\*\s*BUNDLE=current bundle_sha256=([0-9a-f]{64})\s*$",
        review_text,
        re.MULTILINE,
    )
    review_status = re.search(r"^\*\*Status:\*\*\s*(.+?)\s*$", review_text, re.MULTILINE)
    if not target_match or not review_status or "❌" not in review_status.group(1):
        fail("not_accepted_red", "source review is not an exact red current-bundle review")
    try:
        current_blockers = (
            accepted_red_topology_open_blocker_ids(review_text)
            if topology_rebind
            else current_open_blocker_ids(review_text)
        )
        inherited_blockers = successor_inherited_blocker_ids(successor_text, review_rel)
    except CurrentOpenBlockerError as exc:
        fail("not_accepted_red", str(exc))
    if inherited_blockers != current_blockers:
        fail(
            "not_accepted_red",
            "successor inherited blocker refs differ from the current-open blocker set",
        )
    if scope.get("source_ref") not in {
        f"{review_rel}#{blocker}" for blocker in current_blockers
    }:
        fail(
            "not_accepted_red",
            "scope_expansion.source_ref is outside the current-open blocker set",
        )
    review_sha = target_match.group(1)
    target_snapshots: dict[str, ObjectSnapshot] | None = None
    if require_snapshot:
        producer_snapshot = run_current_bundle_producer()
        producer_bundle_sha = producer_snapshot.get("bundle_sha256")
        if not isinstance(producer_bundle_sha, str):
            fail("snapshot_invalid", "snapshot helper omitted bundle_sha256")
        target_snapshots = retained_target_snapshots(
            sorted(targets),
            producer_bundle_sha=producer_bundle_sha,
            review_sha=review_sha,
            snapshot_bridge=None,
        )

    routing = [source_rel, draft_rel, review_rel, successor_rel]
    source_stem = source.stem
    prefix = f".planveyor/rejected-baselines/{source_stem}/{review_sha}"
    return {
        "source_plan": source_rel,
        "source_stem": source_stem,
        "draft": draft_rel,
        "review": review_rel,
        "successor": successor_rel,
        "targets": sorted(targets),
        "routing": sorted(routing),
        "review_sha": review_sha,
        "ref": f"refs/planveyor/rejected-baselines/{source_stem}/{review_sha}",
        "manifest_path": f"{prefix}/manifest.json",
        "cleanup_path": f"{prefix}/cleanup.json",
        "_target_snapshots": target_snapshots,
    }


def index_matches_tree(revision: str, targets: list[str]) -> bool:
    return git(
        "diff",
        "--cached",
        "--quiet",
        revision,
        "--",
        *targets,
        check=False,
    ).returncode == 0


def index_matches_head(targets: list[str]) -> bool:
    return index_matches_tree("HEAD", targets)


def committed_carrier_record(rel: str, parent: str) -> dict[str, object]:
    parent_record = tree_record(parent, rel)
    if parent_record is None:
        fail(
            "snapshot_bridge_carrier_uncommitted",
            f"bridge carrier is absent from capture parent: {rel}",
        )
    snapshot = active_target_snapshot(
        rel,
        failure_reason="snapshot_bridge_carrier_uncommitted",
    )
    if (
        snapshot.state != "regular"
        or snapshot.data != parent_record["_bytes"]
        or snapshot.git_mode != parent_record["mode"]
    ):
        fail(
            "snapshot_bridge_carrier_uncommitted",
            f"bridge carrier differs from capture parent: {rel}",
        )
    if not index_matches_tree(parent, [rel]):
        fail(
            "snapshot_bridge_carrier_uncommitted",
            f"bridge carrier index differs from capture parent: {rel}",
        )
    return {
        "path": rel,
        "sha256": parent_record["sha256"],
        "size_bytes": parent_record["size_bytes"],
        "mode": parent_record["mode"],
        "blob_oid": parent_record["blob_oid"],
    }


def temp_index() -> tuple[tempfile.TemporaryDirectory[str], dict[str, str]]:
    temp = tempfile.TemporaryDirectory(prefix="planveyor-rejected-index-")
    env = git_env()
    env["GIT_INDEX_FILE"] = str(Path(temp.name) / "index")
    return temp, env


def update_index_record(env: dict[str, str], record: dict[str, object]) -> None:
    git(
        "update-index",
        "--add",
        "--cacheinfo",
        str(record["mode"]),
        str(record["blob_oid"]),
        str(record["path"]),
        env=env,
    )


def publish_capture_ref(ref: str, commit: str, parent: str) -> None:
    transaction = (
        "start\n"
        f"verify HEAD {parent}\n"
        f"create {ref} {commit}\n"
        "prepare\n"
        "commit\n"
    ).encode("ascii")
    proc = git("update-ref", "--stdin", input_bytes=transaction, check=False)
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        fail(
            "recovery_ref_cas_conflict",
            detail or "capture parent/ref transaction was rejected",
        )


def publish_cleanup_ref(
    ref: str,
    cleanup_commit: str,
    capture_commit: str,
    captured_parent: str,
) -> None:
    transaction = (
        "start\n"
        f"verify HEAD {captured_parent}\n"
        f"update {ref} {cleanup_commit} {capture_commit}\n"
        "prepare\n"
        "commit\n"
    ).encode("ascii")
    proc = git("update-ref", "--stdin", input_bytes=transaction, check=False)
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        fail(
            "recovery_ref_cas_conflict",
            detail or "cleanup parent/ref transaction was rejected",
        )


def active_target_snapshot(
    rel: str,
    *,
    failure_reason: str = "active_checkout_drift",
) -> ObjectSnapshot:
    try:
        return snapshot_regular_or_absent(root, rel)
    except ObjectIdentityError as exc:
        fail(
            failure_reason,
            f"cannot snapshot active target {rel}: {exc.reason_code}",
        )


def current_path_kind(
    record: dict[str, object],
    snapshot: ObjectSnapshot,
    *,
    prefer_head: bool = False,
) -> str:
    captured = (
        snapshot.state == "regular"
        and snapshot.data == record["_bytes"]
        and snapshot.git_mode == record["mode"]
    )
    if captured and not prefer_head:
        return "captured"
    rel = str(record["path"])
    head = head_record(rel)
    if head is None:
        if snapshot.state == "absent":
            return "head"
        return "captured" if captured else "third"
    matches_head = (
        snapshot.state == "regular"
        and snapshot.data == head["_bytes"]
        and snapshot.git_mode == head["mode"]
    )
    if prefer_head and matches_head:
        return "head"
    if captured:
        return "captured"
    if matches_head:
        return "head"
    return "third"


def parse_recovery_contract(
    recovery_rel: str,
    source_targets: list[str],
    *,
    allow_terminal_status: bool = False,
    carrier_commit: str | None = None,
) -> dict[str, object]:
    try:
        return parse_accepted_red_recovery_contract(
            root,
            recovery_rel,
            source_rel,
            source_targets,
            allow_terminal_status=allow_terminal_status,
            carrier_commit=carrier_commit,
        )
    except ValueError as exc:
        fail("recovery_plan_invalid", str(exc))


def is_applicable() -> bool:
    source_stem = Path(source_rel).stem
    ref_prefix = f"refs/planveyor/rejected-baselines/{source_stem}/"
    if git("for-each-ref", "--format=%(refname)", ref_prefix, check=False).stdout.strip():
        return True
    if not source.is_file() or source.is_symlink():
        return False
    source_text = source.read_text(encoding="utf-8")
    status = re.search(r"^\*\*Status:\*\*\s*(.+?)\s*$", source_text, re.MULTILINE)
    if not status or status.group(1).strip() != "Superseded":
        return False
    try:
        meta = fenced_json(source_text, "plan_meta")
    except RecoveryError:
        return False
    scope = meta.get("scope_expansion")
    next_plans = meta.get("next_plans")
    return (
        isinstance(scope, dict)
        and scope.get("state") == "architect_accepted"
        and isinstance(next_plans, list)
        and len(next_plans) == 1
        and isinstance(next_plans[0], str)
    )


def verify(
    *,
    invalid_as_error: bool = False,
    contract_override: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object], str, str, list[dict[str, object]]]:
    contract = (
        dict(contract_override)
        if contract_override is not None
        else parse_source(require_snapshot=False)
    )
    durable = validate_accepted_red_durable_ref(root, contract)
    contract["_durable_result"] = durable
    if durable.state == "missing":
        try:
            producer_snapshot = run_current_bundle_producer()
        except RecoveryError as exc:
            if exc.reason_code != "snapshot_invalid":
                raise
            snapshot_matches = False
        else:
            snapshot_matches = producer_snapshot.get("bundle_sha256") == contract["review_sha"]
        disposition_reason = (
            "accepted_red_current_snapshot"
            if snapshot_matches
            else "accepted_red_snapshot_mismatch_without_durable_ref"
        )
        payload = base_payload(contract, disposition_reason=disposition_reason)
        payload.update(
            durable_capture_state="missing",
            active_checkout_state=(
                "rejected_targets_present" if snapshot_matches else "snapshot_mismatch"
            ),
            recovery_state=(
                "capture_required"
                if snapshot_matches
                else "snapshot_mismatch_without_durable_ref"
            ),
        )
        return payload, contract, "", "", []
    if durable.state == "invalid":
        if invalid_as_error:
            fail("recovery_ref_invalid", durable.reason)
        payload = base_payload(
            contract,
            disposition_reason="accepted_red_snapshot_mismatch_without_valid_durable_ref",
        )
        payload.update(
            durable_capture_state="invalid",
            active_checkout_state="snapshot_mismatch",
            recovery_state="snapshot_mismatch_without_valid_durable_ref",
        )
        return payload, contract, "", "", []
    if durable.state not in {"valid_capture", "valid_cleanup"}:
        fail("recovery_ref_invalid", f"unsupported durable state: {durable.state}")
    if (
        durable.manifest is None
        or durable.recovery_contract is None
        or not durable.capture_commit
    ):
        fail("recovery_ref_invalid", "validated durable result is incomplete")
    manifest = dict(durable.manifest)
    recovery_contract = dict(durable.recovery_contract)
    capture_commit = durable.capture_commit
    cleanup_commit = durable.cleanup_commit
    targets = [dict(record) for record in durable.targets]
    routing = [dict(record) for record in durable.routing]
    for record in routing:
        data, mode = regular_bytes(str(record["path"]))
        if sha256(data) != record["sha256"] or mode != record["mode"]:
            fail("routing_carrier_drift", f"routing carrier changed: {record['path']}")

    snapshots = {
        str(record["path"]): active_target_snapshot(str(record["path"]))
        for record in targets
    }
    kinds = {
        str(record["path"]): current_path_kind(
            record,
            snapshots[str(record["path"])],
            prefer_head=durable.state == "valid_cleanup",
        )
        for record in targets
    }
    overlap = set(str(item) for item in recovery_contract["recovery_targets"])
    if all(kind == "captured" for kind in kinds.values()):
        checkout_state = "rejected_targets_present"
    elif all(kind == "head" for kind in kinds.values()):
        checkout_state = "clean"
    elif all(
        kind == "head"
        or (
            kind == "third"
            and rel in overlap
            and snapshots[rel].state == "regular"
        )
        for rel, kind in kinds.items()
    ):
        checkout_state = "recovery_owned_overlap"
    else:
        checkout_state = "drifted"

    payload = base_payload(
        contract,
        disposition_reason="accepted_red_durable_capture",
    )
    payload.update(
        recovery_plan=manifest.get("recovery_plan"),
        recovery_code_draft=recovery_contract["recovery_code_draft"],
        recovery_targets=recovery_contract["recovery_targets"],
        recovery_contract_state=durable.recovery_contract_state,
        captured_parent=manifest.get("captured_parent"),
        capture_commit=capture_commit,
        cleanup_commit=cleanup_commit or None,
        durable_capture_state="captured",
        active_checkout_state=checkout_state,
        recovery_state="cleanup_required",
    )
    if durable.state == "valid_cleanup":
        if checkout_state not in {"clean", "recovery_owned_overlap"}:
            fail("active_checkout_drift", "cleanup receipt exists but checkout is not clean/recovery-owned")
        payload.update(
            durable_capture_state="cleanup_recorded",
            recovery_state="completed",
            closeout_kind="accepted_red_recovered",
            bundle_ok=True,
        )
    return payload, contract, capture_commit, cleanup_commit, targets


def base_payload(
    contract: dict[str, object],
    *,
    disposition_reason: str,
) -> dict[str, object]:
    return {
        "schema": "planveyor_plan_bundle_closeout.v1",
        "plan": contract["source_plan"],
        "terminal_disposition": "accepted_red_supersession",
        "delivery_green": False,
        "staging_policy": "forbidden",
        "durable_capture_required": True,
        "terminal_disposition_reason": disposition_reason,
        "recovery_ref": contract["ref"],
        "recovery_manifest_path": contract["manifest_path"],
        "recovery_cleanup_path": contract["cleanup_path"],
        "successor_plan": contract["successor"],
        "review_bundle_sha256": contract["review_sha"],
        "bundle_ok": False,
        "closeout_kind": "accepted_red_pending",
    }


def capture() -> dict[str, object]:
    active_contract = parse_source(require_snapshot=False)
    durable = validate_accepted_red_durable_ref(root, active_contract)
    if durable.state == "invalid":
        fail("recovery_ref_invalid", durable.reason)
    if durable.state != "missing":
        existing, _contract, _capture, _cleanup, _targets = verify(
            invalid_as_error=True,
        )
        return existing
    parent = git_text("rev-parse", "HEAD")
    targets = list(active_contract["targets"])
    recovery_rel = Path(recovery_arg).as_posix() if recovery_arg else ""
    recovery_contract = parse_recovery_contract(recovery_rel, targets)
    bridged = recovery_contract.get("snapshot_bridge") is not None
    frozen_carrier_records: dict[str, dict[str, object]] = {}
    if bridged:
        contract = parse_source(
            require_snapshot=False,
            carrier_commit=parent,
        )
        targets = list(contract["targets"])
        recovery_contract = parse_recovery_contract(
            recovery_rel,
            targets,
            carrier_commit=parent,
        )
        if recovery_contract.get("snapshot_bridge") is None:
            fail(
                "snapshot_bridge_carrier_uncommitted",
                "capture parent does not contain the active snapshot bridge",
            )
        carrier_paths = [
            *list(contract["routing"]),
            recovery_rel,
            str(recovery_contract["recovery_code_draft"]),
        ]
        frozen_carrier_records = {
            rel: committed_carrier_record(rel, parent)
            for rel in carrier_paths
        }
    else:
        contract = active_contract
    if not index_matches_tree(parent, targets):
        fail(
            "rejected_target_staged",
            "rejected target index entries differ from capture parent",
        )
    producer_snapshot = run_current_bundle_producer()
    producer_bundle_sha = producer_snapshot.get("bundle_sha256")
    if not isinstance(producer_bundle_sha, str):
        fail("snapshot_invalid", "snapshot helper omitted bundle_sha256")
    target_snapshots = retained_target_snapshots(
        targets,
        producer_bundle_sha=producer_bundle_sha,
        review_sha=str(contract["review_sha"]),
        snapshot_bridge=recovery_contract.get("snapshot_bridge"),
    )
    target_records = [
        blob_record_from_bytes(
            rel,
            target_snapshots[rel].data,
            target_snapshots[rel].git_mode,
            write=not bridged,
        )
        for rel in targets
    ]
    routing_records = (
        [
            dict(frozen_carrier_records[rel])
            for rel in contract["routing"]
        ]
        if bridged
        else [blob_record(rel) for rel in contract["routing"]]
    )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "source_plan": source_rel,
        "recovery_plan": recovery_rel,
        "recovery_code_draft": recovery_contract["recovery_code_draft"],
        "recovery_targets": recovery_contract["recovery_targets"],
        "historical_review": contract["review"],
        "review_target": f"BUNDLE=current bundle_sha256={contract['review_sha']}",
        "review_bundle_sha256": contract["review_sha"],
        "successor_plan": contract["successor"],
        "captured_parent": parent,
        "recovery_ref": contract["ref"],
        "recovery_manifest_path": contract["manifest_path"],
        "recovery_cleanup_path": contract["cleanup_path"],
        "targets": target_records,
        "routing_carriers": routing_records,
    }
    if bridged:
        manifest["snapshot_bridge"] = recovery_contract["snapshot_bridge"]
        manifest["recovery_plan_blob_oid"] = frozen_carrier_records[recovery_rel][
            "blob_oid"
        ]
        manifest["recovery_code_draft_blob_oid"] = frozen_carrier_records[
            str(recovery_contract["recovery_code_draft"])
        ]["blob_oid"]
        for rel, expected in frozen_carrier_records.items():
            if committed_carrier_record(rel, parent) != expected:
                fail(
                    "snapshot_bridge_carrier_uncommitted",
                    f"bridge carrier changed during capture admission: {rel}",
                )
        if git_text("rev-parse", "HEAD") != parent:
            fail(
                "recovery_ref_cas_conflict",
                "HEAD changed during capture admission",
            )
        for rel, expected in zip(targets, target_records, strict=True):
            written = blob_record_from_bytes(
                rel,
                target_snapshots[rel].data,
                target_snapshots[rel].git_mode,
            )
            if written != expected:
                fail(
                    "git_command_failed",
                    f"target blob identity changed while writing: {rel}",
                )
    manifest_data = canonical_json(manifest)
    proc = git(
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=manifest_data,
        check=False,
    )
    if proc.returncode:
        fail("git_command_failed", proc.stderr.decode("utf-8", "replace").strip())
    manifest_record = {
        "path": contract["manifest_path"],
        "mode": "100644",
        "blob_oid": proc.stdout.decode().strip(),
    }
    temp, env = temp_index()
    try:
        git("read-tree", parent, env=env)
        for record in [*target_records, *routing_records, manifest_record]:
            update_index_record(env, record)
        tree = git_text("write-tree", env=env)
    finally:
        temp.cleanup()
    proc = git(
        "commit-tree",
        tree,
        "-p",
        parent,
        input_bytes=f"planveyor rejected baseline capture: {source.stem}\n".encode(),
        check=False,
    )
    if proc.returncode:
        fail("git_command_failed", proc.stderr.decode("utf-8", "replace").strip())
    commit = proc.stdout.decode().strip()
    try:
        validate_accepted_red_capture_commit(root, commit, contract)
    except (
        AcceptedRedDurableValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        fail("recovery_ref_invalid", f"candidate capture validation failed: {exc}")
    publish_capture_ref(str(contract["ref"]), commit, parent)
    payload, _contract, _capture, _cleanup, _targets = verify(
        invalid_as_error=True,
        contract_override=contract,
    )
    return payload


def restore_target(record: dict[str, object]) -> dict[str, object]:
    rel = str(record["path"])
    path = root / rel
    head = head_record(rel)
    if head is None:
        if os.path.lexists(path):
            path.unlink()
        return {"path": rel, "state": "absent"}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.planveyor-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(head["_bytes"])
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o755 if head["mode"] == "100755" else 0o644)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return {
        "path": rel,
        "state": "head",
        "sha256": head["sha256"],
        "size_bytes": head["size_bytes"],
        "mode": head["mode"],
        "blob_oid": head["blob_oid"],
    }


def cleanup() -> dict[str, object]:
    try:
        payload, contract, capture_commit, cleanup_commit, targets = verify(
            invalid_as_error=True,
        )
    except RecoveryError as exc:
        if exc.reason_code == "active_checkout_drift":
            fail("rejected_target_drift", str(exc))
        raise
    if cleanup_commit:
        return payload
    if not capture_commit:
        fail("capture_required", "durable capture is missing")
    parent = str(payload["captured_parent"])
    if git_text("rev-parse", "HEAD") != parent:
        fail("head_drift", "active HEAD differs from captured parent")
    target_paths = [str(record["path"]) for record in targets]
    if not index_matches_head(target_paths):
        fail("rejected_target_staged", "rejected target index entries differ from HEAD")
    snapshots = {
        str(record["path"]): active_target_snapshot(
            str(record["path"]),
            failure_reason="rejected_target_drift",
        )
        for record in targets
    }
    kinds = {
        str(record["path"]): current_path_kind(
            record,
            snapshots[str(record["path"])],
        )
        for record in targets
    }
    third = [rel for rel, kind in kinds.items() if kind == "third"]
    if third:
        fail("rejected_target_drift", f"third-state rejected targets: {', '.join(third)}")
    final_records = [restore_target(record) for record in targets]
    readback_snapshots = {
        str(record["path"]): active_target_snapshot(
            str(record["path"]),
            failure_reason="cleanup_readback_failed",
        )
        for record in targets
    }
    if any(
        current_path_kind(
            record,
            readback_snapshots[str(record["path"])],
            prefer_head=True,
        )
        != "head"
        for record in targets
    ):
        fail("cleanup_readback_failed", "rejected target cleanup readback failed")
    durable = contract.get("_durable_result")
    if (
        not isinstance(durable, AcceptedRedDurableRefResult)
        or durable.manifest is None
        or durable.recovery_contract is None
    ):
        fail("recovery_ref_invalid", "validated durable state is incomplete")
    manifest = dict(durable.manifest)
    recovery_contract = dict(durable.recovery_contract)
    routing_readback = []
    for record in manifest["routing_carriers"]:
        data, mode = regular_bytes(str(record["path"]))
        if sha256(data) != record["sha256"] or mode != record["mode"]:
            fail("routing_carrier_drift", f"routing carrier changed: {record['path']}")
        routing_readback.append(dict(record))
    receipt = {
        "schema": CLEANUP_SCHEMA,
        "source_plan": source_rel,
        "recovery_plan": manifest["recovery_plan"],
        "recovery_code_draft": manifest["recovery_code_draft"],
        "recovery_targets": manifest["recovery_targets"],
        "recovery_ref": contract["ref"],
        "review_bundle_sha256": contract["review_sha"],
        "capture_commit": capture_commit,
        "captured_parent": parent,
        "cleanup_head": parent,
        "targets": final_records,
        "routing_carriers": routing_readback,
    }
    receipt_data = canonical_json(receipt)
    proc = git(
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=receipt_data,
        check=False,
    )
    if proc.returncode:
        fail("git_command_failed", proc.stderr.decode("utf-8", "replace").strip())
    receipt_record = {
        "path": contract["cleanup_path"],
        "mode": "100644",
        "blob_oid": proc.stdout.decode().strip(),
    }
    temp, env = temp_index()
    try:
        git("read-tree", capture_commit, env=env)
        update_index_record(env, receipt_record)
        tree = git_text("write-tree", env=env)
    finally:
        temp.cleanup()
    proc = git(
        "commit-tree",
        tree,
        "-p",
        capture_commit,
        input_bytes=f"planveyor rejected baseline cleanup: {source.stem}\n".encode(),
        check=False,
    )
    if proc.returncode:
        fail("git_command_failed", proc.stderr.decode("utf-8", "replace").strip())
    receipt_commit = proc.stdout.decode().strip()
    try:
        validate_accepted_red_cleanup_candidate(
            root,
            receipt_commit,
            capture_commit,
            contract,
            manifest,
            recovery_contract,
            durable.recovery_contract_state,
        )
    except (
        AcceptedRedDurableValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        fail("recovery_ref_invalid", f"candidate cleanup validation failed: {exc}")
    publish_cleanup_ref(
        str(contract["ref"]),
        receipt_commit,
        capture_commit,
        parent,
    )
    result, _contract, _capture, _cleanup, _targets = verify(invalid_as_error=True)
    return result


try:
    if action == "capture":
        result = capture()
    elif action == "verify":
        result, _contract, _capture, _cleanup, _targets = verify()
    elif action == "cleanup":
        result = cleanup()
    elif action == "classify":
        result, _contract, _capture, _cleanup, _targets = verify()
    elif action == "applicable":
        if not is_applicable():
            raise SystemExit(3)
        result = {
            "schema": "planveyor_rejected_baseline_applicability.v1",
            "applicable": True,
            "source_plan": source_rel,
        }
    else:
        fail("unsupported_action", f"unsupported rejected-baseline action: {action}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
except RecoveryError as exc:
    print(
        json.dumps(
            {
                "schema": "planveyor_rejected_baseline_error.v1",
                "state": "blocked",
                "reason_code": exc.reason_code,
                "message": str(exc),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    raise SystemExit(2)
PY
}

planveyor_plan_bundle() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_bundle)" || return $?
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
  local mode="print"
  case "${1:-}" in
    --print) mode="print"; shift ;;
    --check) mode="check"; shift ;;
    --preflight) mode="preflight"; shift ;;
    --scope-check) mode="scope-check"; shift ;;
    --stage) mode="stage"; shift ;;
    --commit-ready) mode="commit-ready"; shift ;;
    --commit-exact) mode="commit-exact"; shift ;;
    --closeout-json) mode="closeout-json"; shift ;;
    --capture-rejected) mode="capture-rejected"; shift ;;
    --verify-rejected) mode="verify-rejected"; shift ;;
    --cleanup-rejected) mode="cleanup-rejected"; shift ;;
  esac

  local plan_path=""
  local recovery_plan=""
  local docs_closeout_json=""
  local preflight_json=""
  local message_file=""
  local message_file_count=0
  local message_auto_count=0
  while (( $# > 0 )); do
    case "${1:-}" in
      --recovery-plan)
        shift
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_plan_bundle --capture-rejected --recovery-plan <PLAN_PATH> <SOURCE_PLAN>" >&2
          return 1
        }
        recovery_plan="$1"
        ;;
      --docs-closeout-json)
        shift
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_plan_bundle [--print|--check|--preflight|--scope-check|--stage|--commit-ready|--commit-exact|--closeout-json|--capture-rejected|--verify-rejected|--cleanup-rejected] <PLAN_PATH>" >&2
          return 1
        }
        docs_closeout_json="$1"
        ;;
      --preflight-json)
        shift
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_plan_bundle --commit-exact --preflight-json <path|-> (--message-auto|--message-file <path>) <PLAN_PATH>" >&2
          return 1
        }
        preflight_json="$1"
        ;;
      --message-file)
        shift
        [[ -n "${1:-}" && "${1:-}" != -* ]] || {
          echo "Usage: planveyor_plan_bundle --commit-exact --preflight-json <path|-> (--message-auto|--message-file <path>) <PLAN_PATH>" >&2
          return 1
        }
        message_file="$1"
        (( message_file_count += 1 ))
        ;;
      --message-auto)
        (( message_auto_count += 1 ))
        ;;
      -*)
        echo "Usage: planveyor_plan_bundle [--print|--check|--preflight|--scope-check|--stage|--commit-ready|--commit-exact|--closeout-json|--capture-rejected|--verify-rejected|--cleanup-rejected] <PLAN_PATH>" >&2
        return 1
        ;;
      *)
        [[ -z "$plan_path" ]] || {
          echo "Usage: planveyor_plan_bundle [--print|--check|--preflight|--scope-check|--stage|--commit-ready|--commit-exact|--closeout-json|--capture-rejected|--verify-rejected|--cleanup-rejected] <PLAN_PATH>" >&2
          return 1
        }
        plan_path="$1"
        ;;
    esac
    shift
  done
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_plan_bundle [--print|--check|--preflight|--scope-check|--stage|--commit-ready|--commit-exact|--closeout-json|--capture-rejected|--verify-rejected|--cleanup-rejected] <PLAN_PATH>" >&2
    return 1
  }

  if [[ "$mode" == "scope-check" && ( -n "$recovery_plan" || -n "$docs_closeout_json" || -n "$preflight_json" || "$message_file_count" -ne 0 || "$message_auto_count" -ne 0 ) ]]; then
    echo "recovery/closeout/preflight/message options are unavailable for --scope-check" >&2
    return 1
  fi

  local root="$(_planveyor_project_root)" || return $?
  local plan_fs="$plan_path"
  [[ "$plan_fs" == /* ]] || plan_fs="${root}/${plan_fs}"
  [[ -f "$plan_fs" ]] || {
    echo "Missing plan: ${plan_fs}" >&2
    return 1
  }

  local tooling_root=""
  tooling_root="$(_planveyor_closeout_tooling_root 2>/dev/null || true)"
  [[ -n "${tooling_root//[[:space:]]/}" ]] || {
    echo "Cannot resolve one complete tooling root for plan bundle" >&2
    return 1
  }

  if [[ -n "$recovery_plan" && "$mode" != "capture-rejected" ]]; then
    echo "--recovery-plan is supported only with --capture-rejected" >&2
    return 1
  fi

  if [[ "$mode" == "capture-rejected" || "$mode" == "verify-rejected" || "$mode" == "cleanup-rejected" ]]; then
    [[ -z "$docs_closeout_json" && -z "$preflight_json" && -z "$message_file" && "$message_file_count" -eq 0 && "$message_auto_count" -eq 0 ]] || {
      echo "closeout/preflight/message options are unavailable for rejected-baseline lifecycle modes" >&2
      return 1
    }
    local rejected_action="${mode%-rejected}"
    _planveyor_rejected_baseline "$rejected_action" "$plan_path" "$recovery_plan" "$root" "$tooling_root"
    return $?
  fi

  # All plan-resident reviewer risk support pairs are exact-bundle members even
  # when their compact receipt is historical and therefore invisible to the
  # current-lane selector.  Keep this shared Python authority ahead of every
  # ordinary/delegated mutation branch; zsh transports the JSON result but does
  # not parse plan JSON or reimplement the support contract.
  local risk_support_manifest=""
  risk_support_manifest="$(_planveyor_py_any_authority_stdin "$plan_fs" "$root" "$tooling_root" <<'PY'
import json
import sys
from pathlib import Path

plan_fs_arg, root_arg, tooling_root_arg = sys.argv[1:4]
root = Path(root_arg).resolve()
for script_dir in (root / "scripts", Path(tooling_root_arg).resolve() / "scripts"):
    while str(script_dir) in sys.path:
        sys.path.remove(str(script_dir))
    sys.path.insert(0, str(script_dir))

import plan_lint

manifest = plan_lint.collect_plan_risk_lane_support_refs(
    Path(plan_fs_arg),
    project_root=root,
)
print(json.dumps({
    "records": [{"ref": ref, "sha256": sha256} for ref, sha256 in manifest.records],
    "diagnostics": [
        {"code": diagnostic.code, "message": diagnostic.message}
        for diagnostic in manifest.diagnostics
    ],
}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
PY
)"
  local risk_support_manifest_rc=$?
  if [[ "$risk_support_manifest_rc" -ne 0 ]]; then
    echo "Unable to read shared plan risk-support manifest" >&2
    return "$risk_support_manifest_rc"
  fi

  # The all-history manifest above is byte-membership only.  A live
  # BUNDLE=current review additionally needs the single strict current-proof
  # reader in plan_lint; transport its verdict rather than recreating Target or
  # support parsing in zsh.
  local current_review_proof=""
  current_review_proof="$(_planveyor_py_any_authority_stdin "$plan_fs" "$root" "$tooling_root" <<'PY'
import json
import sys
from pathlib import Path

plan_fs_arg, root_arg, tooling_root_arg = sys.argv[1:4]
root = Path(root_arg).resolve()
for script_dir in (root / "scripts", Path(tooling_root_arg).resolve() / "scripts"):
    while str(script_dir) in sys.path:
        sys.path.remove(str(script_dir))
    sys.path.insert(0, str(script_dir))

import plan_lint

print(json.dumps(
    plan_lint.preflight_current_review_proof(Path(plan_fs_arg), project_root=root).as_dict(),
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
))
PY
)"
  local current_review_proof_rc=$?
  if [[ "$current_review_proof_rc" -ne 0 ]]; then
    echo "Unable to read canonical current review proof" >&2
    return "$current_review_proof_rc"
  fi

  # Strict-N-A parents may be inspected before their child graph exists, but
  # every mutating/delegated lifecycle branch must stop before it can reach a
  # helper that stages, creates a temporary index, or commits.  The same
  # oracle readback also rejects an invalid/missing authority carrier before
  # delegated mutation.  zsh transports the canonical reader; it does not
  # reparse the plan or recreate the admission predicate.
  if [[ "$mode" == "stage" || "$mode" == "commit-ready" || "$mode" == "commit-exact" ]]; then
    _planveyor_py_any_authority_stdin "$plan_fs" "$root" "$tooling_root" "$risk_support_manifest" <<'PY' >&2
import json
import re
import sys
from pathlib import Path

plan_fs_arg, root_arg, tooling_root_arg, risk_support_manifest_raw = sys.argv[1:5]
root = Path(root_arg).resolve()
for script_dir in (root / "scripts", Path(tooling_root_arg).resolve() / "scripts"):
    while str(script_dir) in sys.path:
        sys.path.remove(str(script_dir))
    sys.path.insert(0, str(script_dir))

import plan_lint
import plan_status_oracle

plan_path = Path(plan_fs_arg)
plan_text = plan_path.read_text(encoding="utf-8")
readback = plan_status_oracle.machine_authority_decision_readback(plan_path, plan_text)
child_state = plan_status_oracle.decomposition_child_state(plan_text, root=root)
if readback.state in {"invalid", "missing"}:
    print(
        f"machine_authority_decision_{readback.reason_code}: {readback.reason}",
    )
    raise SystemExit(2)
strict_na_parent = (
    readback.state == "not_applicable"
    and readback.ref_state == "not_required"
)
if strict_na_parent and (
    child_state.state != "queue_ready"
    or not child_state.canonical_planning_child_paths
):
    print(f"decomposition_children_missing: {child_state.reason}")
    raise SystemExit(2)

if strict_na_parent:
    try:
        risk_support_manifest = json.loads(risk_support_manifest_raw)
    except json.JSONDecodeError as exc:
        print(f"risk_lane_support_manifest_invalid: {exc}")
        raise SystemExit(2)
    records = risk_support_manifest.get("records") if isinstance(risk_support_manifest, dict) else None
    if not isinstance(records, list):
        print("risk_lane_support_manifest_invalid: records must be a list")
        raise SystemExit(2)
    live_reviews = plan_lint.extract_live_review_artifact_refs(plan_text.splitlines())
    if len(live_reviews) != 1:
        print("strict N-A parent requires exactly one live parent review for risk-support membership")
        raise SystemExit(2)
    review_rel = live_reviews[0][1]
    review_path = root / review_rel
    # docs/plans/README.md keeps risk support under the plan-stem root in
    # docs/code_reviews/assets/ whatever the live review route.
    support_prefixes = (
        f"{Path(review_rel).parent.as_posix()}/assets/{review_path.stem}/",
        f"docs/code_reviews/assets/{plan_path.stem}/",
    )
    durable_receipt_re = re.compile(r"docs/reviews/[A-Za-z0-9_.-]+\.json\Z")
    for record in records:
        support_ref = record.get("ref") if isinstance(record, dict) else None
        if not isinstance(support_ref, str):
            print("risk_lane_support_manifest_invalid: record ref must be a string")
            raise SystemExit(2)
        if not (support_ref.startswith(support_prefixes) or durable_receipt_re.fullmatch(support_ref)):
            print(
                "strict N-A parent risk support is outside the live parent review-assets "
                f"root, the plan risk-support root or durable review receipts: {support_ref}"
            )
            raise SystemExit(2)
PY
    local strict_na_candidate_gate_rc=$?
    if [[ "$strict_na_candidate_gate_rc" -ne 0 ]]; then
      return "$strict_na_candidate_gate_rc"
    fi
  fi

  if [[ "$mode" == "stage" || "$mode" == "commit-ready" || "$mode" == "commit-exact" ]]; then
    _planveyor_py_any - "$risk_support_manifest" <<'PY' >&2
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except (IndexError, json.JSONDecodeError) as exc:
    print(json.dumps({
        "state": "blocked",
        "reason_code": "risk_lane_support_manifest_invalid",
        "message": f"Shared plan risk-support manifest transport is invalid: {exc}",
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(2)

diagnostics = payload.get("diagnostics")
if not isinstance(diagnostics, list):
    print(json.dumps({
        "state": "blocked",
        "reason_code": "risk_lane_support_manifest_invalid",
        "message": "Shared plan risk-support manifest lacks diagnostics list.",
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(2)
if diagnostics:
    print(json.dumps({
        "state": "blocked",
        "reason_code": "risk_lane_support_manifest_invalid",
        "diagnostics": diagnostics,
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(2)
PY
    local risk_support_gate_rc=$?
    if [[ "$risk_support_gate_rc" -ne 0 ]]; then
      return "$risk_support_gate_rc"
    fi
    _planveyor_py_any - "$current_review_proof" <<'PY' >&2
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except (IndexError, json.JSONDecodeError) as exc:
    print(json.dumps({
        "state": "blocked",
        "reason_code": "current_review_proof_transport_invalid",
        "message": f"Canonical current review proof transport is invalid: {exc}",
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(2)

if payload.get("state") == "blocked":
    print(json.dumps({
        "state": "blocked",
        "reason_code": payload.get("reason_code") or "current_review_proof_blocked",
        "message": payload.get("message") or "Canonical current review proof is blocked.",
        "diagnostics": payload.get("diagnostics") or [],
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(2)
PY
    local current_review_proof_gate_rc=$?
    if [[ "$current_review_proof_gate_rc" -ne 0 ]]; then
      return "$current_review_proof_gate_rc"
    fi
  fi

  if [[ "$mode" == "closeout-json" ]]; then
    local rejected_payload=""
    rejected_payload="$(_planveyor_rejected_baseline classify "$plan_path" "" "$root" "$tooling_root" 2>&1)"
    local rejected_classify_rc=$?
    if [[ "$rejected_classify_rc" -eq 0 && -n "$rejected_payload" ]]; then
      print -r -- "$rejected_payload"
      return 0
    fi
    _planveyor_rejected_baseline applicable "$plan_path" "" "$root" "$tooling_root" >/dev/null 2>&1
    local rejected_applicable_rc=$?
    if [[ "$rejected_applicable_rc" -eq 0 || "$rejected_applicable_rc" -eq 2 ]]; then
      _planveyor_py_any - "$rejected_payload" <<'PY' >&2
import json
import sys

try:
    cause = json.loads(sys.argv[1])
except json.JSONDecodeError:
    cause = {"message": sys.argv[1]}
print(json.dumps({
    "schema": "planveyor_rejected_baseline_error.v1",
    "state": "blocked",
    "reason_code": "accepted_red_closeout_invalid_carrier",
    "message": "accepted-red closeout is blocked because its recovery carrier is invalid",
    "cause": cause,
}, ensure_ascii=False, sort_keys=True))
PY
      return 2
    fi
  fi

  if [[ "$mode" == "stage" || "$mode" == "commit-ready" || "$mode" == "commit-exact" ]]; then
    _planveyor_rejected_baseline applicable "$plan_path" "" "$root" "$tooling_root" >/dev/null 2>&1
    local rejected_applicable_rc=$?
    if [[ "$rejected_applicable_rc" -eq 0 || "$rejected_applicable_rc" -eq 2 ]]; then
      local rejected_guard_payload=""
      rejected_guard_payload="$(_planveyor_rejected_baseline classify "$plan_path" "" "$root" "$tooling_root" 2>&1)"
      local rejected_classify_rc=$?
      local rejected_invalid_state=1
      if [[ "$rejected_classify_rc" -eq 0 ]]; then
        _planveyor_py_any - "$rejected_guard_payload" <<'PY' >/dev/null 2>&1
import json
import sys

payload = json.loads(sys.argv[1])
raise SystemExit(0 if payload.get("durable_capture_state") == "invalid" else 1)
PY
        rejected_invalid_state=$?
      fi
      if [[ "$rejected_classify_rc" -eq 0 && "$rejected_invalid_state" -ne 0 ]]; then
        echo '{"schema":"planveyor_rejected_baseline_error.v1","state":"blocked","reason_code":"staging_forbidden","message":"accepted-red supersession is evidence-only and cannot be staged or committed as delivery"}' >&2
      else
        _planveyor_py_any - "$rejected_guard_payload" <<'PY' >&2
import json
import sys

try:
    cause = json.loads(sys.argv[1])
except json.JSONDecodeError:
    cause = {"message": sys.argv[1]}
print(json.dumps({
    "schema": "planveyor_rejected_baseline_error.v1",
    "state": "blocked",
    "reason_code": "staging_forbidden_invalid_carrier",
    "message": "accepted-red staging is forbidden because its recovery carrier is invalid",
    "cause": cause,
}, ensure_ascii=False, sort_keys=True))
PY
      fi
      return 2
    fi
  fi

  if [[ "$mode" == "commit-exact" ]]; then
    local message_selector_count=$(( message_file_count + message_auto_count ))
    [[ -n "$preflight_json" && -z "$docs_closeout_json" && "$message_file_count" -le 1 && "$message_auto_count" -le 1 && "$message_selector_count" -eq 1 ]] || {
      echo "Usage: planveyor_plan_bundle --commit-exact --preflight-json <path|-> (--message-auto|--message-file <path>) <PLAN_PATH>" >&2
      return 1
    }
    local capture_helper="$(_planveyor_script followups_capture.py)"
    [[ -f "$capture_helper" ]] || { echo "Missing helper: ${capture_helper}" >&2; return 1; }
    if (( message_auto_count == 1 )); then
      _planveyor_py_any "$capture_helper" commit-exact --project-root "$root" --plan-ref "$plan_path" \
        --preflight-json "$preflight_json" --message-auto
    else
      _planveyor_py_any "$capture_helper" commit-exact --project-root "$root" --plan-ref "$plan_path" \
        --preflight-json "$preflight_json" --message-file "$message_file"
    fi
    return $?
  fi

  if [[ -n "$docs_closeout_json" ]]; then
    [[ "$mode" == "stage" || "$mode" == "commit-ready" ]] || {
      echo "--docs-closeout-json is supported only with --stage|--commit-ready" >&2
      return 1
    }
    [[ -z "$preflight_json" && -z "$message_file" && "$message_file_count" -eq 0 && "$message_auto_count" -eq 0 ]] || {
      echo "preflight/message options are supported only with --commit-exact" >&2
      return 1
    }
    local capture_helper="$(_planveyor_script followups_capture.py)"
    [[ -f "$capture_helper" ]] || { echo "Missing helper: ${capture_helper}" >&2; return 1; }
    _planveyor_py_any "$capture_helper" "$mode" --project-root "$root" --plan-ref "$plan_path" \
      --docs-closeout-json "$docs_closeout_json"
    return $?
  fi

  if [[ -n "$preflight_json" || -n "$message_file" || "$message_file_count" -ne 0 || "$message_auto_count" -ne 0 ]]; then
    echo "preflight/message options are supported only with --commit-exact" >&2
    return 1
  fi

  _planveyor_py_any_authority_stdin "$mode" "$plan_fs" "$root" "$tooling_root" "$risk_support_manifest" "$current_review_proof" <<'PY'
import json
import re
import shlex
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

mode, plan_fs_arg, root_arg, tooling_root_arg, risk_support_manifest_raw, current_review_proof_raw = sys.argv[1:7]
root = Path(root_arg).resolve()
plan_fs = Path(plan_fs_arg).resolve()
root_script_dir = root / "scripts"
tooling_script_dir = Path(tooling_root_arg).resolve() / "scripts"
for script_dir in (root_script_dir, tooling_script_dir):
    while str(script_dir) in sys.path:
        sys.path.remove(str(script_dir))
    sys.path.insert(0, str(script_dir))

import plan_lint
import plan_status_oracle
import review_artifact_lint
import review_visual_lane_contract

CODE_DRAFT_RE = re.compile(
    r"(?:/[A-Za-z0-9_./-]*/docs/code_drafts/[A-Za-z0-9_./-]+__code_draft\.md|docs/code_drafts/[A-Za-z0-9_./-]+__code_draft\.md)"
)
REVIEW_RE = re.compile(
    r"(?:/[A-Za-z0-9_./-]*/docs/(?:code_reviews|doc_reviews)/[A-Za-z0-9_./-]+\.md|docs/(?:code_reviews|doc_reviews)/[A-Za-z0-9_./-]+\.md)"
)
ASSET_RE = re.compile(
    r"(?:/[A-Za-z0-9_./-]*/docs/(?:code_reviews|doc_reviews)/assets/[A-Za-z0-9_./-]+|docs/(?:code_reviews|doc_reviews)/assets/[A-Za-z0-9_./-]+)"
)
REVIEW_JSON_RE = re.compile(
    r"(?:/[A-Za-z0-9_./-]*/docs/reviews/[A-Za-z0-9_./-]+\.json|docs/reviews/[A-Za-z0-9_./-]+\.json)"
)
TRANSIENT_RECEIPT_MARKERS = (
    "command output",
    "debug-only",
    "debug only",
    "transient",
    "local sanity",
    "not checked in",
    "not checked-in",
    "not a checked-in artifact",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, title: str) -> str:
    match = re.search(
        rf"^##[ \t]+{re.escape(title)}\s*$([\s\S]*?)(?=^##[ \t]+|\Z)",
        text,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


def resolve_path(raw: str, *, strip: bool = True) -> Path:
    # strip=True applies markdown/prose cleanup (whitespace + surrounding
    # backticks) for review/plan/code-draft lanes. strip=False preserves the
    # complete literal metadata path (target/deleted_paths), including any
    # leading/trailing backticks, so identity is not mutated before lookup.
    if strip:
        raw = raw.strip().strip("`")
    path = Path(raw)
    if mode == "scope-check":
        lexical_path = path if path.is_absolute() else root / path
        if any(part.is_symlink() for part in (lexical_path, *lexical_path.parents)):
            errors.append(f"Unsafe symlink bundle input: {raw}")
    return path.resolve() if path.is_absolute() else (root / raw).resolve()


def durable_review_json_refs(text: str):
    refs = OrderedDict()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        context = " ".join(lines[max(0, index - 1) : index + 2]).lower()
        if any(marker in context for marker in TRANSIENT_RECEIPT_MARKERS):
            continue
        for raw in REVIEW_JSON_RE.findall(line):
            refs.setdefault(raw.strip("`'\""), None)
    return list(refs.keys())


def repo_root_for(path: Path):
    anchor = path if path.exists() else path.parent
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    cwd = anchor if anchor.is_dir() else anchor.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None
    value = result.stdout.strip()
    return Path(value).resolve() if value else None


def repo_rel(path: Path, repo_root: Path):
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return None


def git_ref_has_path(repo_root: Path, ref: str, rel_path: str) -> bool:
    ref_value = str(ref or "").strip()
    if not ref_value:
        return False
    result = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{ref_value}:{rel_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def staged_rel_paths(repo_root: Path):
    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--cached", "--name-only", "-z", "--"],
        capture_output=True,
        check=True,
    )
    output = result.stdout.decode("utf-8", errors="surrogateescape")
    return [item for item in output.split("\x00") if item]


def diff_rel_paths(repo_root: Path, rel_paths, *, cached: bool):
    if not rel_paths:
        return []
    cmd = ["git", "--literal-pathspecs", "-C", str(repo_root), "diff"]
    if cached:
        cmd.append("--cached")
    cmd.extend(["--name-only", "-z", "--", *rel_paths])
    result = subprocess.run(cmd, capture_output=True, check=True)
    output = result.stdout.decode("utf-8", errors="surrogateescape")
    return sorted({item for item in output.split("\x00") if item})


def untracked_rel_paths(repo_root: Path, rel_paths):
    if not rel_paths:
        return []
    result = subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "-C",
            str(repo_root),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *rel_paths,
        ],
        capture_output=True,
        check=True,
    )
    output = result.stdout.decode("utf-8", errors="surrogateescape")
    return sorted({item for item in output.split("\x00") if item})


def commit_skeleton(repo_root: str, rel_paths):
    root_part = shlex.quote(repo_root)
    paths_part = " ".join(shlex.quote(path) for path in rel_paths)
    return f'git -C {root_part} commit -m "<message>" -- {paths_part}'


plan_text = read_text(plan_fs)
try:
    plan_display = str(plan_fs.relative_to(root))
except ValueError:
    plan_display = str(plan_fs)
machine_authority_readback = plan_status_oracle.machine_authority_decision_readback(plan_fs, plan_text)
child_state = plan_status_oracle.decomposition_child_state(plan_text, root=root)
strict_na_parent = (
    machine_authority_readback.state == "not_applicable"
    and machine_authority_readback.ref_state == "not_required"
)
status_lines = plan_lint.extract_status_lines(plan_text.splitlines())
status_value = status_lines[0][1] if len(status_lines) == 1 else None
strict_na_candidate = (
    strict_na_parent
    and child_state.state == "missing"
    and (
        plan_lint.is_deferred_early_intake_child_graph_gap(child_state, status_value, plan_text)
        or plan_lint.is_deferred_decomposition_materialization_child_graph_gap(
            child_state,
            status_value,
            plan_text,
            plan_text.splitlines(),
        )
    )
)
errors = []
if mode == "scope-check":
    lexical_plan = Path(plan_fs_arg).absolute()
    if any(part.is_symlink() for part in (lexical_plan, *lexical_plan.parents)):
        errors.append("Unsafe symlink origin plan input")
machine_authority_readback_blocked = machine_authority_readback.state in {"invalid", "missing"}
if machine_authority_readback_blocked:
    errors.append(
        "machine_authority_decision_"
        f"{machine_authority_readback.reason_code}: {machine_authority_readback.reason}"
    )
risk_support_manifest_clean = True
try:
    risk_support_manifest = json.loads(risk_support_manifest_raw)
except json.JSONDecodeError as exc:
    risk_support_manifest = None
    risk_support_manifest_clean = False
    errors.append(f"Shared plan risk-support manifest transport is invalid: {exc}")
if isinstance(risk_support_manifest, dict):
    risk_support_diagnostics = risk_support_manifest.get("diagnostics")
    risk_support_records = risk_support_manifest.get("records")
    if not isinstance(risk_support_diagnostics, list) or not isinstance(risk_support_records, list):
        risk_support_manifest_clean = False
        errors.append("Shared plan risk-support manifest has invalid records/diagnostics shape")
        risk_support_records = []
    else:
        for diagnostic in risk_support_diagnostics:
            if not isinstance(diagnostic, dict):
                risk_support_manifest_clean = False
                errors.append("Shared plan risk-support manifest contains invalid diagnostic")
                continue
            code = diagnostic.get("code")
            message = diagnostic.get("message")
            if not isinstance(code, str) or not isinstance(message, str):
                risk_support_manifest_clean = False
                errors.append("Shared plan risk-support manifest contains invalid diagnostic fields")
                continue
            risk_support_manifest_clean = False
            errors.append(f"Risk-lane support manifest {code}: {message}")
else:
    risk_support_records = []
    if risk_support_manifest is not None:
        risk_support_manifest_clean = False
        errors.append("Shared plan risk-support manifest must be a JSON object")
try:
    current_review_proof = json.loads(current_review_proof_raw)
except json.JSONDecodeError as exc:
    current_review_proof = None
    errors.append(f"Canonical current review proof transport is invalid: {exc}")
scope_selected_support = {"state": "not_selected", "error_code": None, "message": None, "diagnostics": []}
if mode == "scope-check":
    # These input authorities must run independently of the proof reader's
    # early output-debt returns. Never use the adapter's filtered projection.
    selection = plan_lint.select_plan_risk_lane_snapshot(plan_fs)
    scope_selected_support["error_code"] = selection.error_code
    scope_selected_support["message"] = selection.message
    if selection.error_code is not None:
        scope_selected_support["state"] = "invalid"
        errors.append(f"Risk-lane selector {selection.error_code}: {selection.message}")
    elif selection.snapshot is None and selection.payload is None:
        pass  # No selection is explicitly unvalidated, even with no diagnostics.
    elif not isinstance(selection.snapshot, str) or not selection.snapshot or not isinstance(selection.payload, dict):
        scope_selected_support["state"] = "invalid"
        errors.append("Risk-lane selector selection_shape_invalid: snapshot/payload must be present together")
    else:
        diagnostics = plan_lint.preflight_selected_risk_lane_support(plan_fs, selection, project_root=root)
        scope_selected_support["diagnostics"] = [
            {"code": diagnostic.code, "message": diagnostic.message} for diagnostic in diagnostics
        ]
        invalid_diagnostics = [
            diagnostic for diagnostic in diagnostics
            if diagnostic.code != "current_review_proof_producer_mismatch"
        ]
        if invalid_diagnostics:
            scope_selected_support["state"] = "invalid"
            errors.extend(
                f"Selected risk-lane support {diagnostic.code}: {diagnostic.message}"
                for diagnostic in invalid_diagnostics
            )
        else:
            scope_selected_support["state"] = "stale_producer" if diagnostics else "validated"

if not isinstance(current_review_proof, dict):
    errors.append("Canonical current review proof must be a JSON object")
elif mode == "scope-check":
    proof_debt_codes = {
        "current_review_proof_target_ambiguous",
        "current_review_proof_target_invalid",
        "missing_plan_resident_risk_lane",
        "current_review_proof_compact_snapshot_invalid",
        "current_review_proof_projection_mismatch",
        "current_review_proof_producer_mismatch",
    }
    proof_state = current_review_proof.get("state")
    proof_code = current_review_proof.get("reason_code")
    proof_diagnostics = current_review_proof.get("diagnostics")
    if (
        proof_state not in {"planned", "not_current", "current_green", "blocked"}
        or not isinstance(current_review_proof.get("message"), str)
        or not isinstance(proof_diagnostics, list)
        or any(
            not isinstance(diagnostic, dict)
            or set(diagnostic) != {"code", "message"}
            or not isinstance(diagnostic.get("code"), str)
            or not isinstance(diagnostic.get("message"), str)
            for diagnostic in (proof_diagnostics if isinstance(proof_diagnostics, list) else [])
        )
        or (proof_state != "blocked" and proof_code is not None)
    ):
        errors.append("Canonical current review proof shape_invalid: unknown state or malformed fields")
    else:
        # Secondary diagnostics remain input failures in every proof state,
        # including planned/not_current with a null primary reason.
        errors.extend(
            f"Canonical current review proof diagnostic {diagnostic['code']}: {diagnostic['message']}"
            for diagnostic in proof_diagnostics if diagnostic["code"] not in proof_debt_codes
        )
        if proof_state == "blocked" and (
            not isinstance(proof_code, str)
            or proof_code not in proof_debt_codes
            or scope_selected_support["state"] == "invalid"
            or not risk_support_manifest_clean
        ):
            errors.append(f"Canonical current review proof {proof_code}: {current_review_proof.get('message')}")
elif current_review_proof.get("state") == "blocked":
    reason_code = current_review_proof.get("reason_code") or "current_review_proof_blocked"
    message = current_review_proof.get("message") or "Canonical current review proof is blocked."
    errors.append(f"Canonical current review proof {reason_code}: {message}")
live_review_refs = plan_lint.extract_live_review_artifact_refs(plan_text.splitlines())
live_review_rel_path = None
if len(live_review_refs) == 1:
    live_review_rel_path = live_review_refs[0][1]
elif not live_review_refs:
    errors.append("Missing explicit live review artifact path in ## Review artifacts")
else:
    errors.append(
        "Multiple live review artifact paths in ## Review artifacts; "
        "fail closed until the plan is restamped to one live route."
    )
review_range_base_ref = None
review_range_match = re.search(r"Review target:\s*`?RANGE=([0-9A-Fa-f]{7,40})\.\.[^`\s)]+", plan_text)
if review_range_match:
    review_range_base_ref = review_range_match.group(1)

plan_base = plan_fs.stem
expected_draft_name = f"{plan_base}__code_draft.md"
code_draft_fs = None
if not strict_na_parent and not machine_authority_readback_blocked:
    draft_candidates = [resolve_path(raw) for raw in CODE_DRAFT_RE.findall(plan_text)]
    for candidate in draft_candidates:
        if candidate.name == expected_draft_name:
            code_draft_fs = candidate
            break
    if code_draft_fs is None:
        fallback = root / "docs" / "code_drafts" / expected_draft_name
        if fallback.exists():
            code_draft_fs = fallback.resolve()

draft_text = ""
if (
    not strict_na_parent
    and not machine_authority_readback_blocked
    and (code_draft_fs is None or not code_draft_fs.exists())
):
    errors.append(f"Missing code draft for plan: {expected_draft_name}")
    code_draft_fs = (root / "docs" / "code_drafts" / expected_draft_name).resolve()

entries = OrderedDict()


def add_entry(raw: str, source: str, *, strip: bool = True):
    abs_path = resolve_path(raw, strip=strip)
    key = str(abs_path)
    if key not in entries:
        entries[key] = {"path": abs_path, "sources": []}
    if source not in entries[key]["sources"]:
        entries[key]["sources"].append(source)
    return entries[key]


def strict_na_risk_support_is_allowed(support_ref: str) -> bool:
    if not live_review_rel_path:
        return False
    support_path = resolve_path(support_ref)
    try:
        support_rel = support_path.relative_to(root).as_posix()
    except ValueError:
        return False
    review_rel = live_review_rel_path
    review_path = resolve_path(review_rel)
    # docs/plans/README.md keeps risk support under the plan-stem root in
    # docs/code_reviews/assets/ whatever the live review route.
    expected_asset_prefixes = (
        f"{Path(review_rel).parent.as_posix()}/assets/{review_path.stem}/",
        f"docs/code_reviews/assets/{plan_fs.stem}/",
    )
    if support_rel.startswith(expected_asset_prefixes):
        return support_path.is_file()
    return bool(re.fullmatch(r"docs/reviews/[A-Za-z0-9_.-]+\.json", support_rel)) and support_path.is_file()


if (risk_support_manifest_clean or mode == "scope-check") and isinstance(risk_support_records, list):
    for record in risk_support_records:
        if not isinstance(record, dict):
            risk_support_manifest_clean = False
            errors.append("Shared plan risk-support manifest contains invalid record")
            continue
        support_ref = record.get("ref")
        support_sha = record.get("sha256")
        if not isinstance(support_ref, str) or not support_ref or not isinstance(support_sha, str) or not support_sha:
            risk_support_manifest_clean = False
            errors.append("Shared plan risk-support manifest contains invalid record fields")
            continue
        if strict_na_parent and not strict_na_risk_support_is_allowed(support_ref):
            errors.append(
                "strict N-A parent risk support is outside the live parent review-assets "
                f"root, the plan risk-support root or durable review receipts: {support_ref}"
            )
            continue
        entry = add_entry(support_ref, "plan_risk_support")
        entry.setdefault("plan_risk_support_hashes", []).append(support_sha)


if code_draft_fs is not None and code_draft_fs.exists():
    draft_text = read_text(code_draft_fs)
    meta = None
    for block in re.findall(r"```json\s*(\{.*?\})\s*```", draft_text, re.DOTALL):
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        if "code_draft_meta" in payload:
            meta = payload["code_draft_meta"]
            break
    if meta is None:
        errors.append(f"Missing valid code_draft_meta JSON in {code_draft_fs}")
    elif not isinstance(meta, dict):
        errors.append(f"Invalid code_draft_meta object in {code_draft_fs}")
    else:
        meta_plan = meta.get("plan")
        if meta_plan != plan_display:
            errors.append(
                f"code_draft_meta.plan mismatch in {code_draft_fs}: expected {plan_display!r}, got {meta_plan!r}"
            )
        targets = meta.get("targets") or []
        if not isinstance(targets, list) or not targets:
            errors.append(f"Empty code_draft_meta.targets in {code_draft_fs}")
        for item in targets:
            if not isinstance(item, dict) or not item.get("path"):
                errors.append(f"Invalid target entry in {code_draft_fs}: {item!r}")
                continue
            add_entry(item["path"], "target", strip=False)
        deleted_paths = meta.get("deleted_paths") or []
        if not isinstance(deleted_paths, list):
            errors.append(f"Invalid code_draft_meta.deleted_paths in {code_draft_fs}: expected list")
        if isinstance(deleted_paths, list):
            for item in deleted_paths:
                if not isinstance(item, dict) or not item.get("path"):
                    errors.append(f"Invalid deleted_path entry in {code_draft_fs}: {item!r}")
                    continue
                raw_path = str(item.get("path") or "")
                is_review_only = item.get("review_only") is True or str(item.get("kind") or "").strip().lower() == "review_only"
                base_ref = str(item.get("base_ref") or "").strip()
                deletion_ref = str(item.get("deletion_ref") or item.get("deleted_ref") or "").strip()
                if is_review_only and (not base_ref or not deletion_ref):
                    errors.append(
                        "Review-only code_draft_meta.deleted_paths entry requires base_ref and deletion_ref: "
                        f"{raw_path}"
                    )
                entry = add_entry(raw_path, "deleted_path", strip=False)
                entry.setdefault("deleted_path_items", []).append(item)

add_entry(str(plan_fs), "plan")
if code_draft_fs is not None:
    add_entry(str(code_draft_fs), "code_draft")

if strict_na_parent:
    if child_state.state != "queue_ready" or not child_state.canonical_planning_child_paths:
        if not (strict_na_candidate and mode in {"print", "preflight", "scope-check"}):
            errors.append(f"decomposition_children_missing: {child_state.reason}")
    else:
        for child_rel in child_state.canonical_planning_child_paths:
            add_entry(child_rel, "decomposition_child_plan")
            child_draft_rel = f"docs/code_drafts/{Path(child_rel).stem}__code_draft.md"
            child_draft_fs = root / child_draft_rel
            add_entry(child_draft_rel, "decomposition_child_code_draft")
            if not child_draft_fs.is_file():
                errors.append(f"Missing child code draft for strict N-A parent: {child_draft_rel}")
                continue
            try:
                child_draft_meta = plan_status_oracle._machine_authority_strict_code_draft_meta(
                    read_text(child_draft_fs)
                )
            except (OSError, UnicodeDecodeError, plan_status_oracle.MachineAuthorityDecisionError) as exc:
                errors.append(f"Invalid child code draft for strict N-A parent {child_draft_rel}: {exc}")
                continue
            if child_draft_meta.get("plan") != child_rel:
                errors.append(
                    "child code_draft_meta.plan mismatch for strict N-A parent: "
                    f"expected {child_rel!r}, got {child_draft_meta.get('plan')!r}"
                )
                continue
            # The parent never imports child implementation targets, but each
            # child planning carrier must still be lintable enough to prove it
            # is a real code draft rather than an empty or malformed stub.
            child_targets = child_draft_meta.get("targets")
            if not isinstance(child_targets, list) or not child_targets:
                errors.append(
                    "Empty child code_draft_meta.targets for strict N-A parent: "
                    f"{child_draft_rel}"
                )
                continue
            for target in child_targets:
                if not isinstance(target, dict) or not isinstance(target.get("path"), str) or not target["path"].strip():
                    errors.append(
                        "Invalid child code_draft_meta.target entry for strict N-A parent: "
                        f"{child_draft_rel}: {target!r}"
                    )
                    break
            child_deleted_paths = child_draft_meta.get("deleted_paths") or []
            if not isinstance(child_deleted_paths, list):
                errors.append(
                    "Invalid child code_draft_meta.deleted_paths for strict N-A parent: "
                    f"{child_draft_rel}"
                )
            else:
                for deleted_path in child_deleted_paths:
                    if (
                        not isinstance(deleted_path, dict)
                        or not isinstance(deleted_path.get("path"), str)
                        or not deleted_path["path"].strip()
                    ):
                        errors.append(
                            "Invalid child code_draft_meta.deleted_path entry for strict N-A parent: "
                            f"{child_draft_rel}: {deleted_path!r}"
                        )
                        break

review_section = section(plan_text, "Review artifacts")
review_artifacts = REVIEW_RE.findall(review_section)
if not review_artifacts:
    errors.append("Missing explicit review artifact path in ## Review artifacts")
elif strict_na_parent and live_review_rel_path:
    # The strict parent has one planning review. Historical review mentions do
    # not widen its derived planning bundle.
    review_artifacts = [live_review_rel_path]

review_artifact_abs = []
for raw in review_artifacts:
    add_entry(raw, "review_artifact")
    review_artifact_abs.append(resolve_path(raw))

review_text_by_path = OrderedDict()
for review_path in review_artifact_abs:
    if review_path.exists():
        review_text = read_text(review_path)
        review_text_by_path[review_path] = review_text
        for asset_path in ASSET_RE.findall(review_text):
            if strict_na_parent:
                resolved_asset = resolve_path(asset_path)
                try:
                    review_rel = review_path.relative_to(root).as_posix()
                    asset_rel = resolved_asset.relative_to(root).as_posix()
                except ValueError:
                    review_rel = ""
                    asset_rel = ""
                expected_prefix = (
                    f"{Path(review_rel).parent.as_posix()}/assets/{review_path.stem}/"
                    if review_rel
                    else ""
                )
                in_review_root = bool(expected_prefix) and asset_rel.startswith(expected_prefix)
                # The review names its risk support literally; support already
                # admitted from the plan above keeps the plan risk-support root.
                asset_entry = entries.get(str(resolved_asset))
                admitted_support = asset_entry is not None and "plan_risk_support" in asset_entry["sources"]
                if not (in_review_root or admitted_support):
                    errors.append(
                        "strict N-A parent review asset is outside its matching review-assets root "
                        f"and is not declared risk support: {asset_path}"
                    )
                    continue
                if not resolved_asset.is_file():
                    errors.append(
                        "strict N-A parent review asset must be a regular file: "
                        f"{asset_path}"
                    )
            add_entry(asset_path, "review_asset")

review_closeout_by_repo_rel = OrderedDict()
if live_review_rel_path:
    live_review_path = resolve_path(live_review_rel_path)
    if live_review_path.exists():
        review_closeout = review_artifact_lint.classify_same_file_rerun_closeout(
            plan_fs,
            live_review_path,
            project_root=root,
        )
        live_review_root = repo_root_for(live_review_path)
        live_review_repo_rel = repo_rel(live_review_path, live_review_root) if live_review_root else None
        if live_review_repo_rel is not None:
            review_closeout_by_repo_rel[live_review_repo_rel] = review_closeout
    else:
        review_closeout = None

carrier_texts = [(plan_fs, plan_text)]
if code_draft_fs is not None:
    carrier_texts.append((code_draft_fs, draft_text))
carrier_texts.extend(review_text_by_path.items())
for carrier_path, carrier_text in carrier_texts:
    for receipt_ref in durable_review_json_refs(carrier_text):
        add_entry(receipt_ref, "durable_receipt")
    visual_refs, visual_ref_errors = review_visual_lane_contract.referenced_full_payload_refs(carrier_text)
    for visual_ref_error in visual_ref_errors:
        errors.append(
            f"Invalid explicit review visual lane support ref in {carrier_path}: {visual_ref_error}"
        )
    for visual_ref in visual_refs:
        # The helper extracts only a literal ref-v1 field.  Never scan the
        # containing asset directory: adjacent support files are not bundle
        # members merely because they share a basename.
        add_entry(visual_ref, "review_visual_lane_support")

groups = OrderedDict()
problem_count = 0

for item in entries.values():
    path = item["path"]
    item["exists"] = path.exists()
    item["repo_root"] = repo_root_for(path)
    item["repo_rel"] = repo_rel(path, item["repo_root"]) if item["repo_root"] else None
    item["problems"] = []
    if mode == "scope-check" and item["exists"] and not path.is_file():
        item["problems"].append("non-regular-path")
    item["planned_missing_review_artifact"] = (
        (mode in {"preflight", "scope-check"} or (mode == "print" and strict_na_candidate))
        and not item["exists"]
        and "review_artifact" in item["sources"]
        and (mode != "scope-check" or set(item["sources"]) == {"review_artifact"})
    )
    item["missing_declared_review_artifact_receipt"] = None
    if not item["exists"] and "review_artifact" in item["sources"] and not item["planned_missing_review_artifact"]:
        item["missing_declared_review_artifact_receipt"] = OrderedDict(
            [
                ("origin_plan", plan_display),
                ("declared_review_artifact", item["repo_rel"] or str(item["path"])),
                ("receipt_state", "missing"),
                ("blocker_code", "missing_declared_review_artifact"),
                ("next_owner", "Reviewer"),
            ]
        )
    item["represented_deletion"] = "deleted_path" in item["sources"]
    deletion_target_is_tracked = False
    if item["represented_deletion"] and item["repo_root"] is not None and item["repo_rel"]:
        deletion_items = item.get("deleted_path_items") or []
        review_only_items = [
            deletion_item
            for deletion_item in deletion_items
            if deletion_item.get("review_only") is True
            or str(deletion_item.get("kind") or "").strip().lower() == "review_only"
        ]
        for deletion_item in review_only_items:
            base_ref = str(deletion_item.get("base_ref") or "").strip()
            deletion_ref = str(deletion_item.get("deletion_ref") or deletion_item.get("deleted_ref") or "").strip()
            if not base_ref or not deletion_ref:
                item["problems"].append("missing-review-only-deletion-contract")
                continue
            if git_ref_has_path(item["repo_root"], base_ref, item["repo_rel"]):
                deletion_target_is_tracked = True
            else:
                item["problems"].append("missing-deletion-base-ref")
            if git_ref_has_path(item["repo_root"], deletion_ref, item["repo_rel"]):
                item["problems"].append("deletion-ref-still-has-path")
        if not review_only_items:
            deletion_target_is_tracked = git_ref_has_path(item["repo_root"], "HEAD", item["repo_rel"])
            if not deletion_target_is_tracked and review_range_base_ref:
                deletion_target_is_tracked = git_ref_has_path(
                    item["repo_root"],
                    review_range_base_ref,
                    item["repo_rel"],
                )
    if (
        not item["exists"]
        and not item["planned_missing_review_artifact"]
        and not item["represented_deletion"]
    ):
        item["problems"].append("missing-path")
    if item["represented_deletion"] and not deletion_target_is_tracked:
        item["problems"].append("missing-deletion-target")
    if item["repo_root"] is None:
        item["problems"].append("no-git-root")
        group_key = "<no-git-root>"
    else:
        group_key = str(item["repo_root"])
        if item["repo_rel"] is None:
            item["problems"].append("outside-git-root")
        if "durable_receipt" in item["sources"] and item["repo_rel"] is not None:
            tracked_check = subprocess.run(
                [
                    "git",
                    "-C",
                    str(item["repo_root"]),
                    "ls-files",
                    "--error-unmatch",
                    "--",
                    item["repo_rel"],
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if item["exists"] and tracked_check.returncode != 0:
                item["problems"].append("untracked-durable-receipt")
    if "durable_receipt" in item["sources"] and item["problems"]:
        display = item["repo_rel"] if item["repo_rel"] else str(item["path"])
        errors.append(
            "Durable docs/reviews/*.json receipt reference is not closeout-ready: "
            f"{display}. Operator action: commit the receipt as an explicit durable bundle member, "
            "mark the reference transient/debug-only/not checked in, or remove the stale durable reference."
        )
    review_closeout = review_closeout_by_repo_rel.get(item["repo_rel"]) if item["repo_rel"] else None
    if mode != "scope-check" and review_closeout is not None and review_closeout.state in {"current_red", "needs_reviewer_rerun", "stale_red_after_fix"}:
        display = item["repo_rel"] if item["repo_rel"] else str(item["path"])
        closeout_problem_by_state = {
            "current_red": "current-review-red",
            "needs_reviewer_rerun": "needs-reviewer-rerun",
            "stale_red_after_fix": "reviewer-same-file-rewrite-required",
        }
        closeout_problem = closeout_problem_by_state[review_closeout.state]
        item["problems"].append(closeout_problem)
        errors.append(
            "Live review artifact is not closeout-ready for same-file review lifecycle: "
            f"{display}. state={review_closeout.state}; reason={review_closeout.reason}"
        )
    groups.setdefault(group_key, []).append(item)
    problem_count += len(item["problems"])

if mode == "scope-check":
    # Project only diagnostic fields, never a closeout/route/commit envelope.
    payload = {
        "schema": "planveyor_plan_bundle_scope.v1",
        "plan": plan_display,
        "scope_ok": not bool(errors or problem_count),
        "errors": list(errors),
        "path_problems": OrderedDict(),
        "repo_roots": [],
        "support": {
            "historical": {
                "state": "validated" if risk_support_manifest_clean else "invalid",
                "diagnostics": risk_support_manifest.get("diagnostics", []) if isinstance(risk_support_manifest, dict) else [],
            },
            "selected": scope_selected_support,
        },
        "completion": {
            "current_review_proof": {
                **{
                    key: current_review_proof.get(key) if isinstance(current_review_proof, dict)
                    and isinstance(current_review_proof.get(key), str) else None
                    for key in ("state", "reason_code", "message")
                },
                "diagnostics": [
                    {key: diagnostic.get(key) if isinstance(diagnostic.get(key), str) else None
                     for key in ("code", "message")}
                    for diagnostic in current_review_proof.get("diagnostics", [])
                    if isinstance(diagnostic, dict)
                ] if isinstance(current_review_proof, dict)
                and isinstance(current_review_proof.get("diagnostics"), list) else [],
            },
            "review_artifacts": [],
        },
    }
    for group_key, items in groups.items():
        problems = OrderedDict(
            (item["repo_rel"] or str(item["path"]), list(item["problems"]))
            for item in items if item["problems"]
        )
        payload["path_problems"].update(problems)
        payload["repo_roots"].append({
            "repo_root": None if group_key == "<no-git-root>" else group_key,
            "bundle_paths": sorted({item["repo_rel"] for item in items if item["repo_rel"]}),
            "path_problems": problems,
        })
    for review_path in review_artifact_abs:
        review_root = repo_root_for(review_path)
        closeout = review_closeout_by_repo_rel.get(repo_rel(review_path, review_root)) if review_root else None
        payload["completion"]["review_artifacts"].append({
            "path": str(review_path.relative_to(root)) if review_path.is_relative_to(root) else str(review_path),
            "state": closeout.state if closeout is not None else "planned",
            "reason": closeout.reason if closeout is not None else "Declared first review is not materialized.",
        })
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(0 if payload["scope_ok"] else 1)

if mode == "closeout-json":
    payload = OrderedDict()
    payload["plan"] = plan_display
    payload["bundle_ok"] = not bool(errors or problem_count)
    payload["errors"] = list(errors)
    payload["review_artifact_receipts"] = []
    payload["path_problems"] = OrderedDict()
    payload["repo_roots"] = []

    closeout_kinds = []
    for group_key, items in groups.items():
        rel_paths = sorted({item["repo_rel"] for item in items if item["repo_rel"]})
        repo_payload = OrderedDict()
        repo_payload["repo_root"] = None if group_key == "<no-git-root>" else group_key
        repo_payload["bundle_paths"] = rel_paths
        repo_payload["path_problems"] = OrderedDict()
        for item in items:
            if item.get("missing_declared_review_artifact_receipt"):
                payload["review_artifact_receipts"].append(item["missing_declared_review_artifact_receipt"])
            if item["problems"]:
                display = item["repo_rel"] if item["repo_rel"] else str(item["path"])
                repo_payload["path_problems"][display] = list(item["problems"])

        if group_key == "<no-git-root>":
            repo_payload["closeout_kind"] = "needs_rerun"
            repo_payload["reasons"] = ["bundle_contains_path_without_git_root"]
            repo_payload["staged_bundle_paths"] = []
            repo_payload["staged_extra_paths"] = []
            repo_payload["unstaged_bundle_paths"] = []
            repo_payload["untracked_bundle_paths"] = []
            repo_payload["commit_skeleton"] = None
            payload["repo_roots"].append(repo_payload)
            closeout_kinds.append("needs_rerun")
            continue

        repo_root = Path(group_key)
        staged_paths = sorted(set(staged_rel_paths(repo_root)))
        staged_bundle_paths = [path for path in staged_paths if path in rel_paths]
        staged_extra_paths = [path for path in staged_paths if path not in rel_paths]
        unstaged_bundle_paths = diff_rel_paths(repo_root, rel_paths, cached=False)
        untracked_bundle_paths = untracked_rel_paths(repo_root, rel_paths)
        pending_unstaged = sorted(set(unstaged_bundle_paths) | set(untracked_bundle_paths))

        reasons = []
        if staged_extra_paths:
            closeout_kind = "staged_mismatch"
            reasons.append("unrelated_staged_paths_present")
        elif staged_bundle_paths and pending_unstaged:
            closeout_kind = "needs_rerun"
            reasons.append("bundle_split_between_staged_and_unstaged")
        elif staged_bundle_paths:
            closeout_kind = "commit_ready"
            reasons.append("exact_bundle_staged")
        elif pending_unstaged:
            closeout_kind = "staged_empty"
            reasons.append("bundle_has_unstaged_delta")
        else:
            closeout_kind = "already_materialized"
            reasons.append("no_pending_bundle_delta")

        repo_payload["closeout_kind"] = closeout_kind
        repo_payload["reasons"] = reasons
        repo_payload["staged_bundle_paths"] = staged_bundle_paths
        repo_payload["staged_extra_paths"] = staged_extra_paths
        repo_payload["unstaged_bundle_paths"] = unstaged_bundle_paths
        repo_payload["untracked_bundle_paths"] = untracked_bundle_paths
        repo_payload["commit_skeleton"] = (
            commit_skeleton(group_key, rel_paths) if rel_paths else None
        )
        payload["repo_roots"].append(repo_payload)
        closeout_kinds.append(closeout_kind)

    if errors or problem_count:
        closeout_kind = "needs_rerun"
    elif any(kind == "staged_mismatch" for kind in closeout_kinds):
        closeout_kind = "staged_mismatch"
    elif any(kind == "needs_rerun" for kind in closeout_kinds):
        closeout_kind = "needs_rerun"
    elif any(kind == "staged_empty" for kind in closeout_kinds):
        closeout_kind = "staged_empty"
    elif any(kind == "commit_ready" for kind in closeout_kinds):
        closeout_kind = "commit_ready"
    else:
        closeout_kind = "already_materialized"

    payload["closeout_kind"] = closeout_kind
    payload["commit_ready"] = closeout_kind == "commit_ready"
    payload["already_materialized"] = closeout_kind == "already_materialized"
    payload["rerun_recommended"] = closeout_kind in {
        "staged_empty",
        "staged_mismatch",
        "needs_rerun",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(0)

print(f"Bundle: {plan_display}")
for group_key, items in groups.items():
    print(f"[repo] {group_key}")
    for item in items:
        display = item["repo_rel"] if item["repo_rel"] else str(item["path"])
        if item["problems"]:
            status = "+".join(item["problems"]).upper()
        elif item.get("planned_missing_review_artifact"):
            status = "PLANNED"
        else:
            status = "OK"
        sources = ",".join(item["sources"])
        print(f"  - {status:<24} {display} [{sources}]")

if errors:
    print("Errors:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)

print(
    f"Summary: {len(entries)} path(s), {len(groups)} repo root(s), {problem_count + len(errors)} issue(s)"
)

if errors or problem_count:
    sys.exit(1)

real_group_count = sum(1 for group_key in groups if group_key != "<no-git-root>")

if mode == "preflight":
    print(f"Preflight guard passed across {real_group_count} repo root(s).")
    sys.exit(0)

if mode == "commit-ready":
    commit_problems = 0
    for group_key, items in groups.items():
        if group_key == "<no-git-root>":
            continue
        rel_paths = sorted({item["repo_rel"] for item in items if item["repo_rel"]})
        if not rel_paths:
            continue
        print(f"Commit-ready [{group_key}]")
        print(f"  {commit_skeleton(group_key, rel_paths)}")
        staged_paths = sorted(set(staged_rel_paths(Path(group_key))))
        extras = [path for path in staged_paths if path not in rel_paths]
        if extras:
            commit_problems += len(extras)
            print("  Offending staged paths:")
            for path in extras:
                print(f"    - {path}")
        else:
            print("  Staged set matches explicit bundle.")
    if commit_problems:
        sys.exit(1)
    print(f"Commit-ready guard passed across {real_group_count} repo root(s).")
    sys.exit(0)

if mode == "stage":
    for group_key, items in groups.items():
        if group_key == "<no-git-root>":
            continue
        rel_paths = [item["repo_rel"] for item in items if item["repo_rel"]]
        if not rel_paths:
            continue
        subprocess.run(["git", "--literal-pathspecs", "-C", group_key, "add", "--", *rel_paths], check=True)
    print(f"Staged explicit bundle across {real_group_count} repo root(s).")
PY
}

_planveyor_review_receipt_emit() {
  local plan_path="$1"
  [[ -n "${plan_path//[[:space:]]/}" ]] || return 0

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local artifact_rel=""
  artifact_rel="$(_planveyor_plan_review_artifact_path "$plan_path" 2>/dev/null || true)"
  [[ -n "${artifact_rel//[[:space:]]/}" ]] || return 0

  local artifact_fs="$artifact_rel"
  [[ "$artifact_fs" == /* ]] || artifact_fs="${root}/${artifact_fs}"
  [[ -f "$artifact_fs" ]] || return 0

  local target_value=""
  target_value="$(rg -m1 '^\*\*(Review target|Target|Range):\*\*' "$artifact_fs" 2>/dev/null | sed -E 's/^\*\*(Review target|Target|Range):\*\*[[:space:]]*//' | tr -d '\r')"

  local status_value=""
  status_value="$(rg -m1 '^\*\*Status:\*\*' "$artifact_fs" 2>/dev/null | sed -E 's/^\*\*Status:\*\*[[:space:]]*//' | tr -d '\r')"

  local summary_line=""
  summary_line="$(rg -m1 '^(OK:|Findings:|Verdict:)' "$artifact_fs" 2>/dev/null | tr -d '\r')"

  echo "Review receipt:" >&2
  echo "  artifact: ${artifact_rel}" >&2
  [[ -n "${target_value//[[:space:]]/}" ]] && echo "  target: ${target_value}" >&2
  [[ -n "${status_value//[[:space:]]/}" ]] && echo "  verdict: ${status_value}" >&2
  [[ -n "${summary_line//[[:space:]]/}" ]] && echo "  summary: ${summary_line}" >&2
}

planveyor_plan_status_oracle() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_status_oracle)" || return $?
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
  # Standalone status oracle entrypoint (shared truth for wrappers + Manager).
  # Usage:
  #   planveyor_plan_status_oracle docs/plans/<...>.md
  #   planveyor_plan_status_oracle --json docs/plans/<...>.md
  local plan_path=""
  local -a oracle_args
  oracle_args=()
  while (( $# > 0 )); do
    case "${1:-}" in
      --json|--current-state)
        oracle_args+=("$1")
        ;;
      --manager-mode)
        oracle_args+=("$1")
        shift
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_plan_status_oracle [--json] [--manager-mode <mode>] <PLAN_PATH>" >&2
          return 1
        }
        oracle_args+=("$1")
        ;;
      -*)
        echo "Usage: planveyor_plan_status_oracle [--json] [--manager-mode <mode>] <PLAN_PATH>" >&2
        return 1
        ;;
      *)
        [[ -z "$plan_path" ]] || {
          echo "Usage: planveyor_plan_status_oracle [--json] [--manager-mode <mode>] <PLAN_PATH>" >&2
          return 1
        }
        plan_path="$1"
        ;;
    esac
    shift
  done
  [[ -n "${plan_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_plan_status_oracle [--json] [--manager-mode <mode>] <PLAN_PATH>" >&2
    return 1
  }

  local root="$(_planveyor_project_root)" || return $?
  local plan_fs="$plan_path"
  [[ "$plan_fs" == /* ]] || plan_fs="${root}/${plan_fs}"
  [[ -f "$plan_fs" ]] || { echo "Missing plan: $plan_fs" >&2; return 1; }
  local oracle_py="$(_planveyor_script plan_status_oracle.py)"
  [[ -f "$oracle_py" ]] || { echo "Missing status oracle: $oracle_py" >&2; return 1; }

  _planveyor_py_any "$oracle_py" "$plan_fs" "${oracle_args[@]}"
}

_planveyor_plan_set_header_status() {
  # Best-effort: replace the single header **Status:** line value, preserving any leading "> ".
  local plan_path="$1"
  local new_status="$2"
  [[ -f "$plan_path" ]] || return 1
  [[ -n "${new_status//[[:space:]]/}" ]] || return 1

  local status_line=""
  status_line="$(planveyor_status_line "$plan_path" 2>/dev/null)" || return 1
  local line_no="${status_line%%:*}"
  [[ "$line_no" == <-> ]] || return 1

  _planveyor_py_any - "$plan_path" "$line_no" "$new_status" <<'PY'
from __future__ import annotations

import re
import sys

plan_path, line_no_s, new_status = sys.argv[1], sys.argv[2], sys.argv[3]
line_no = int(line_no_s)

lines = open(plan_path, "r", encoding="utf-8").read().splitlines()
idx = line_no - 1
if idx < 0 or idx >= len(lines):
    raise SystemExit(1)

pattern = re.compile(r"^(?P<prefix>\s*(?:>\s*)?\*\*Status:\*\*\s*).*$")
match = pattern.match(lines[idx])
if not match:
    raise SystemExit(1)

lines[idx] = f"{match.group('prefix')}{new_status}  "
open(plan_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

# --- Codex output noise (optional) ---
# If Codex floods the terminal, prefer config flags (they affect `codex exec` output):
# - `hide_agent_reasoning=true` (hide "reasoning" events)
# - `model_reasoning_summary="none"` (disable summaries)
# - `model_verbosity="low"` (shorter final outputs)
# NOTE: `--config` values are TOML. Do NOT quote booleans (use `true`, not `"true"`).
# If your Codex version ignores `hide_agent_reasoning`, see openai/codex issue #7090.
#
# Load order contract:
# 1. `session_init.zsh` exposes init-time artifact/session helpers used by runtime wrappers.
# 2. `role_runtime.zsh` materializes status-driven role/Manager runtime entrypoints.
# 3. `docs_finalize.zsh` keeps memory-finalize wrappers separate from the main runtime surface.

# Raw local Claude calls do not pass through `_planveyor_codex`.  Keep their final
# same-context revalidation in one facade helper so each launch, init, and
# resume sink has the identical authority boundary.
_planveyor_authority_before_raw_claude_launch() {
  _planveyor_authority_before_effect
}

# --- Session init (new sessions; no resume) ---
_planveyor_source_module "session_init.zsh" || return 1

# --- Role runners (status-driven) ---
_planveyor_source_module "role_runtime.zsh" || return 1

# --- Doc-finalization helpers (memory-dump; use before switching sessions) ---
_planveyor_source_module "docs_finalize.zsh" || return 1

# --- Back-compat aliases (deprecated; prefer planveyor_*) ---
codex_arch() { planveyor_arch "$@"; }
codex_arch_initial() { planveyor_arch_initial "$@"; }
codex_coder() { planveyor_coder "$@"; }
claude_planner() { planveyor_planner "$@"; }
claude_reviewer() { planveyor_reviewer "$@"; }
codex_manager() { planveyor_manager "$@"; }
codex_manager_collab() { planveyor_manager_collab "$@"; }
codex_manager_custom_pipeline() { planveyor_manager_custom_pipeline "$@"; }

# --- Convenience: open interactive sessions (no prompt injection) ---
planveyor_arch_resume() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_resume)" || return $?
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
  local sid; sid="$(planveyor_session architect)" || return 1
  _planveyor_session_authority_resume_validate architect "$sid" || return $?
  pushd "$root" >/dev/null || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || {
    local profile_rc=$?
    popd >/dev/null || true
    return $profile_rc
  }
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  _planveyor_codex resume "${codex_profile_args[@]}" "$sid"
  local resume_rc=$?
  popd >/dev/null || return 1
  return "$resume_rc"
}

_planveyor_latest_codex_sid_for_cwd_prefix() {
  # Returns the most recent sid for sessions whose cwd starts with prefix.
  local cwd_prefix="${1:-}"
  [[ -n "${cwd_prefix//[[:space:]]/}" ]] || return 1

  local root="$(_planveyor_root)"
  local codex_home="$(_planveyor_codex_home_effective)"
  local out="" sid=""

  out="$(_planveyor_py_any "$(_planveyor_codex_session_stats_script)" --list --codex-home "$codex_home" --limit 1 --days 30 --cwd-prefix "$cwd_prefix" 2>/dev/null || true)"
  sid="$(printf '%s\n' "$out" | awk -F $'\t' 'NR==2 {print $1; exit}')"

  if [[ -z "${sid//[[:space:]]/}" ]]; then
    out="$(_planveyor_py_any "$(_planveyor_codex_session_stats_script)" --list --codex-home "$codex_home" --limit 1 --days 30 --cwd-prefix "$cwd_prefix" --null-sessions 2>/dev/null || true)"
    sid="$(printf '%s\n' "$out" | awk -F $'\t' 'NR==2 {print $1; exit}')"
  fi

  [[ -n "${sid//[[:space:]]/}" ]] || return 1
  echo "$sid"
}

_planveyor_arch_track_tui() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_arch_track_tui)" || return $?
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
  local session_key="${1:-}"
  local prompt_rel="${2:-}"
  local phase_id="${3:-}"
  local phase_was_supplied=0
  [[ -n "${phase_id//[[:space:]]/}" ]] && phase_was_supplied=1
  [[ -n "${session_key//[[:space:]]/}" ]] || return 1
  [[ -n "${prompt_rel//[[:space:]]/}" ]] || return 1

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tooling_root=""
  tooling_root="$(_planveyor_root)" || return $?
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local prompt_file="$prompt_rel"
  [[ "$prompt_file" == /* ]] || prompt_file="$tooling_root/$prompt_file"

  local session_file="$root/.planveyor.session.${session_key}"
  local sid=""
  if [[ -e "$session_file" || -L "$session_file" ]]; then
    [[ -f "$session_file" && ! -L "$session_file" ]] || {
      echo "Invalid session pointer (expected a regular file): ${session_file}" >&2
      return 1
    }
    sid="$(planveyor_session "$session_key")" || return $?
    [[ "$sid" == "<SESSION_ID>" ]] && sid=""
  fi

  # An existing track pointer may not silently become either a resume or a
  # fresh provider launch.  In engaged mode it must be bound to this exact
  # track key by a successful init receipt before any provider side effect.
  if [[ -n "${sid//[[:space:]]/}" ]]; then
    _planveyor_session_authority_resume_validate "$session_key" "$sid" || return $?
  fi

  pushd "$root" >/dev/null || return 1

  if [[ -n "${sid//[[:space:]]/}" && "$sid" == *"-"* ]]; then
    echo "Resuming ${session_key} (sid=${sid})" >&2
    _planveyor_codex resume "${codex_profile_args[@]}" "$sid"
    local rc=$?
    popd >/dev/null || return 1
    return $rc
  fi

  # A fresh track start may only name one of the finite, known track phases.
  # The caller's path is an identity hint for legacy two-argument calls; it is
  # never read or forwarded to the provider.  Public callers pass the phase
  # explicitly, so their prompt path remains non-authoritative too.
  if (( phase_was_supplied )); then
    case "$phase_id" in
      track_process_roles|track_process_collab|track_innovations) ;;
      *)
        echo "ERROR: unsupported fresh Architect track phase: ${phase_id}" >&2
        popd >/dev/null || return 1
        return 1
        ;;
    esac
  else
    case "${prompt_file##*/}" in
      architect_track_process_roles.md) phase_id="track_process_roles" ;;
      architect_track_process_collab.md) phase_id="track_process_collab" ;;
      architect_track_innovations.md) phase_id="track_innovations" ;;
      *)
        echo "ERROR: unsupported fresh Architect track prompt: ${prompt_file}" >&2
        popd >/dev/null || return 1
        return 1
        ;;
    esac
  fi

  local launch_prompt=""
  local prompt_tmp=""
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect "$phase_id")" || {
    local body_rc=$?
    popd >/dev/null || return 1
    return $body_rc
  }
  local saved_umask=""
  saved_umask="$(umask)"
  umask 077
  prompt_tmp="$(mktemp "${TMPDIR:-/tmp}/planveyor.arch-track.XXXXXX")"
  local tmp_rc=$?
  umask "$saved_umask"
  if (( tmp_rc != 0 )) || [[ -z "${prompt_tmp//[[:space:]]/}" ]]; then
    popd >/dev/null || return 1
    return 1
  fi
  chmod 600 "$prompt_tmp" || {
    rm -f "$prompt_tmp" >/dev/null 2>&1 || true
    popd >/dev/null || return 1
    return 1
  }
  printf '%s\n' "$prompt_body" > "$prompt_tmp" || {
    rm -f "$prompt_tmp" >/dev/null 2>&1 || true
    popd >/dev/null || return 1
    return 1
  }
  launch_prompt="$prompt_tmp"

  local before_sid=""
  before_sid="$(_planveyor_latest_codex_sid_for_cwd_prefix "$root" 2>/dev/null || true)"

  # Start the same receipt lifecycle used by role init before the TUI starts.
  # In engaged mode a capture failure is a hard pre-provider failure; legacy
  # callers retain their historical best-effort behavior.
  local provider_home_state="$(_planveyor_init_run_provider_home_state codex)"
  local capture_dir=""
  capture_dir="$(_planveyor_init_run_capture_begin architect 2>/dev/null || true)"
  if [[ "$PLANVEYOR_CTX_STATE" == "engaged" && -z "${capture_dir//[[:space:]]/}" ]]; then
    echo "Unable to prepare engaged Architect track init receipt." >&2
    rm -f "$prompt_tmp" >/dev/null 2>&1 || true
    popd >/dev/null || true
    return 1
  fi
  local track_meta="runner=codex profile=${codex_profile} provider_home_state=${provider_home_state} launch_surface=architect_track_tui phase=${phase_id}"

  echo "Starting new ${session_key} TUI session (prompt=${prompt_rel})" >&2
  _planveyor_codex "${codex_profile_args[@]}" --prompt-file "$launch_prompt"
  local rc=$?
  [[ -z "${prompt_tmp//[[:space:]]/}" ]] || rm -f "$prompt_tmp" >/dev/null 2>&1 || true

  local after_sid=""
  local captured_sid=""
  after_sid="$(_planveyor_latest_codex_sid_for_cwd_prefix "$root" 2>/dev/null || true)"
  if [[ -n "${after_sid//[[:space:]]/}" && "$after_sid" != "$before_sid" ]]; then
    captured_sid="$after_sid"
  fi

  # TUI output stays attached to the terminal, so the receipt intentionally
  # records an empty captured stream while its metadata records the real exit
  # status and SID.  Finalize publishes an engaged pointer only after the
  # receipt is atomically visible and receipt validation succeeds.
  local capture_rc=0
  if [[ -n "${capture_dir//[[:space:]]/}" ]]; then
    _planveyor_init_run_capture_finalize "$capture_dir" architect "$session_key" codex "$codex_profile" "$provider_home_state" "" "$rc" "$captured_sid" "" "" "" "" "" "" "" "$track_meta" || capture_rc=$?
  fi

  # Legacy init receipts do not publish a pointer themselves.  Preserve that
  # route, but never report success if its explicit session write fails.
  local session_rc=0
  if [[ "$PLANVEYOR_CTX_STATE" != "engaged" && "$rc" == "0" && "$capture_rc" == "0" && -n "${captured_sid//[[:space:]]/}" ]]; then
    planveyor_session_set "$session_key" "$captured_sid" "$track_meta" || session_rc=$?
  fi

  popd >/dev/null || return 1

  (( rc == 0 )) || return "$rc"
  (( capture_rc == 0 )) || return "$capture_rc"
  (( session_rc == 0 )) || return "$session_rc"
  if [[ -z "${captured_sid//[[:space:]]/}" ]]; then
    if [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
      echo "Could not capture a new SID for ${session_key}; no receipt-bound pointer was published." >&2
      return 1
    fi
    echo "NOTE: Could not detect a new SID for ${session_key}; set it manually: planveyor_session_set ${session_key} <SESSION_ID>" >&2
  fi
  return 0
}

planveyor_arch_process_roles_tui() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_process_roles_tui)" || return $?
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
  local prompt_file; prompt_file="$(_planveyor_prompt_file_for_role_phase architect track_process_roles)" || return 1
  _planveyor_arch_track_tui "architect_process_roles" "$prompt_file" track_process_roles
}
planveyor_arch_process_collab_tui() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_process_collab_tui)" || return $?
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
  local prompt_file; prompt_file="$(_planveyor_prompt_file_for_role_phase architect track_process_collab)" || return 1
  _planveyor_arch_track_tui "architect_process_collab" "$prompt_file" track_process_collab
}
planveyor_arch_innovations_tui() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_innovations_tui)" || return $?
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
  local prompt_file; prompt_file="$(_planveyor_prompt_file_for_role_phase architect track_innovations)" || return 1
  _planveyor_arch_track_tui "architect_innovations" "$prompt_file" track_innovations
}

planveyor_arch_roles_resume() { planveyor_arch_process_roles_tui "$@"; }
planveyor_arch_collab_resume() { planveyor_arch_process_collab_tui "$@"; }
planveyor_arch_inno_resume() { planveyor_arch_innovations_tui "$@"; }

planveyor_coder_resume() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_coder_resume)" || return $?
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
  local sid; sid="$(planveyor_session coder)" || return 1
  _planveyor_session_authority_resume_validate coder "$sid" || return $?
  pushd "$root" >/dev/null || return 1
  local runner=""
  runner="$(planveyor_runner coder 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode coder main)" || {
    local profile_rc=$?
    popd >/dev/null || true
    return $profile_rc
  }
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  case "$runner" in
    codex) _planveyor_codex resume "${codex_profile_args[@]}" "$sid" ;;
    *) echo "Unsupported coder runner: ${runner} (use: planveyor_runner_set coder codex)" >&2; popd >/dev/null || return 1; return 1 ;;
  esac
  local resume_rc=$?
  popd >/dev/null || return 1
  return "$resume_rc"
}

planveyor_planner_resume() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_planner_resume)" || return $?
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
  local sid; sid="$(planveyor_session planner)" || return 1
  _planveyor_session_authority_resume_validate planner "$sid" || return $?
  pushd "$root" >/dev/null || return 1
  local runner=""
  runner="$(planveyor_runner planner 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode planner main)" || {
    local profile_rc=$?
    popd >/dev/null || true
    return $profile_rc
  }
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  case "$runner" in
    codex) _planveyor_codex resume "${codex_profile_args[@]}" "$sid" ;;
    claude)
      _planveyor_authority_before_raw_claude_launch || {
        local guard_rc=$?
        popd >/dev/null || return 1
        return "$guard_rc"
      }
      _planveyor_claude_direct_run -r "$sid" --permission-mode acceptEdits
      ;;
    *) echo "Unsupported planner runner: ${runner} (use: planveyor_runner_set planner codex|claude)" >&2; popd >/dev/null || return 1; return 1 ;;
  esac
  local resume_rc=$?
  popd >/dev/null || return 1
  return "$resume_rc"
}

_planveyor_reviewer_resume_for_session_key() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_reviewer_resume_for_session_key)" || return $?
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
  local runner="${2:-}"
  session_key="$(_planveyor_normalize_session_key "$session_key")" || return 1
  local root=""
  root="$(_planveyor_project_root)" || return $?
  [[ -n "${runner//[[:space:]]/}" ]] || runner="$(planveyor_runner reviewer 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  local codex_profile=""
  local -a codex_profile_args
  codex_profile_args=()
  if [[ "$runner" == "codex" ]]; then
    codex_profile="$(_planveyor_profile_for_role_mode reviewer main)" || return $?
    [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  fi
  local sid=""
  if [[ "$runner" == "codex" ]]; then
    # Read and validate the existing pointer before the ensure helper can clone
    # a rollout or rewrite it.  An engaged resume never manufactures a SID.
    sid="$(planveyor_session "$session_key" 2>/dev/null || true)"
    if [[ -n "${sid//[[:space:]]/}" ]]; then
      _planveyor_session_authority_resume_validate "$session_key" "$sid" || return $?
    elif [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
      echo "Refusing engaged reviewer resume without a receipt-bound session id" >&2
      return 1
    fi
    sid="$(_planveyor_session_sid_ensure_in_effective_codex_home "$session_key" "$codex_profile")" || return 1
  else
    sid="$(planveyor_session "$session_key")" || return 1
  fi
  _planveyor_session_authority_resume_validate "$session_key" "$sid" || return $?
  pushd "$root" >/dev/null || return 1
  case "$runner" in
    codex)
      if [[ -n "${codex_profile//[[:space:]]/}" ]] && ! _planveyor_codex_session_model_matches_profile "$sid" "$codex_profile"; then
        local actual_model=""
        actual_model="$(_planveyor_codex_session_stat_value "$sid" model 2>/dev/null || true)"
        local expected_model=""
        expected_model="$(_planveyor_codex_expected_model_for_profile "$codex_profile")" || {
          local model_rc=$?
          popd >/dev/null || true
          return $model_rc
        }
        echo "Stored reviewer session sid=${sid} uses stale model ${actual_model:-unknown}; expected ${expected_model}. Run planveyor_reviewer to start a fresh reviewer session." >&2
        popd >/dev/null || return 1
        return 1
      fi
      _planveyor_codex resume "${codex_profile_args[@]}" "$sid"
      ;;
    claude)
      _planveyor_authority_before_raw_claude_launch || {
        local guard_rc=$?
        popd >/dev/null || return 1
        return "$guard_rc"
      }
      _planveyor_claude_direct_run -r "$sid" --permission-mode acceptEdits
      ;;
    *) echo "Unsupported reviewer runner: ${runner} (use: planveyor_runner_set reviewer codex|claude)" >&2; popd >/dev/null || return 1; return 1 ;;
  esac
  local resume_rc=$?
  popd >/dev/null || return 1
  return "$resume_rc"
}

planveyor_reviewer_resume() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_resume)" || return $?
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
  local runner=""
  runner="$(planveyor_runner reviewer 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  _planveyor_reviewer_resume_for_session_key reviewer "$runner"
}

planveyor_reviewer_code_risk_resume() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_code_risk_resume)" || return $?
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
  local runner=""
  runner="$(planveyor_runner reviewer 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  _planveyor_reviewer_resume_for_session_key reviewer_code_risk "$runner"
}

planveyor_reviewer_code_contracts_resume() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_reviewer_code_contracts_resume)" || return $?
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
  local runner=""
  runner="$(planveyor_runner reviewer 2>/dev/null || true)"
  [[ -n "${runner//[[:space:]]/}" ]] || runner="codex"
  _planveyor_reviewer_resume_for_session_key reviewer_code_contracts "$runner"
}

planveyor_manager_resume() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_manager_resume)" || return $?
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
  local sid; sid="$(planveyor_session manager)" || return 1
  _planveyor_session_authority_resume_validate manager "$sid" || return $?
  pushd "$root" >/dev/null || return 1
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode manager main)" || {
    local profile_rc=$?
    popd >/dev/null || true
    return $profile_rc
  }
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  _planveyor_codex resume "${codex_profile_args[@]}" "$sid"
  local resume_rc=$?
  popd >/dev/null || return 1
  return "$resume_rc"
}

# --- Convenience: services wrappers ---
# Backward-compatible aliases (legacy names).

# --- Migrations / gates (helpers for "before push") ---
_planveyor_sha7() { echo "${1}" | tr -d '\r' | head -c 7; }


planveyor_doc_lint() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_doc_lint)" || return $?
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
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  local project_root="" runtime_root="" lint_root="" lint_script=""
  project_root="$(_planveyor_project_root)" || return $?
  runtime_root="$(_planveyor_root)" || return $?
  lint_root="$runtime_root"
  case "$content_profile_id" in
    target-local) lint_root="$project_root" ;;
    default|planveyor) ;;
    *)
      echo "Unsupported content profile for doc lint: ${content_profile_id}" >&2
      return 1
      ;;
  esac
  lint_script="$(_planveyor_script doc_lint.py)" || return $?
  [[ -f "$lint_script" ]] || { echo "Missing doc-lint runtime script: ${lint_script}" >&2; return 1; }
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  pushd "$lint_root" >/dev/null || return 1
  local -a lint_args
  lint_args=(
    --content-profile-id "$content_profile_id" \
    --root AGENTS.md \
    --root docs/roles \
    --root docs/playbooks \
    --root docs/guides \
    --root docs/arch.md \
    --check-code-refs --code-refs-scope repo
  )
  [[ "$content_profile_id" != target-local ]] || lint_args+=(--product-root "$project_root")
  env PYTHONDONTWRITEBYTECODE=1 "$pybin" -B "$lint_script" "${lint_args[@]}"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_review_range_init() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_review_range_init)" || return $?
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
  # Creates a review-only plan for BASE..HEAD (does NOT start Reviewer).
  # Every --force-new is intentionally stripped before positional parsing.
  local base="" head="" exclude_docs="1" force_new="0"
  local -a raw_args
  raw_args=()
  while (( $# > 0 )); do
    case "${1:-}" in
      --force-new) force_new="1"; shift ;;
      *) raw_args+=("$1"); shift ;;
    esac
  done
  set -- "${raw_args[@]}"
  if [[ $# -eq 0 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
  elif [[ $# -eq 1 ]]; then
    if [[ "$1" == "0" || "$1" == "1" ]]; then
      exclude_docs="$1"
      base="$(_planveyor_get_range_base)" || return 1
      head="$(_planveyor_get_range_head)" || return 1
    else
      echo "Usage: planveyor_review_range_init [--force-new] [EXCLUDE_DOCS=1|0] | planveyor_review_range_init [--force-new] <BASE_SHA> <HEAD_SHA> [EXCLUDE_DOCS=1|0]" >&2
      return 1
    fi
  else
    base="${1:-}"
    head="${2:-}"
    exclude_docs="${3:-1}"
    [[ -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || {
      echo "Usage: planveyor_review_range_init [--force-new] <BASE_SHA> <HEAD_SHA> [EXCLUDE_DOCS=1|0]" >&2
      return 1
    }
  fi

  local engine_path=""
  engine_path="$(_planveyor_script review_range_scaffold_engine.py)" || return 1
  [[ -f "$engine_path" ]] || {
    echo "planveyor_review_range_init: missing source scaffold engine" >&2
    return 1
  }
  local engine_python=""
  engine_python="$(_planveyor_authority_python 2>/dev/null || true)"
  [[ -n "${engine_python//[[:space:]]/}" ]] || engine_python="$(_planveyor_get_pybin)" || return 1
  local review_range_timestamp=""
  review_range_timestamp="$(date +%y%m%d_%H%M)" || return 1
  [[ "$review_range_timestamp" =~ '^[0-9]{6}_[0-9]{4}$' ]] || {
    echo "planveyor_review_range_init: invalid source scaffold timestamp" >&2
    return 1
  }
  if [[ "$PLANVEYOR_CTX_STATE" == engaged ]]; then
    _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  fi
  local engine_result=""
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  engine_result="$(_PLANVEYOR_AUTHORITY_CONTEXT_V1="$PLANVEYOR_CTX_JSON" _planveyor_python_dispatch "$engine_python" -B "$engine_path" --content-profile-id "$content_profile_id" \
    --root "$PLANVEYOR_CTX_ROOT" --base "$base" --head "$head" --exclude-docs "$exclude_docs" --force-new "$force_new" --timestamp "$review_range_timestamp")" || {
      echo "planveyor_review_range_init: source scaffold engine failed" >&2
      return 1
    }
  [[ "$engine_result" == docs/plans/*.md && "$engine_result" != *$'\n'* && -f "$PLANVEYOR_CTX_ROOT/$engine_result" ]] || {
    echo "planveyor_review_range_init: source scaffold engine returned an invalid plan path" >&2
    return 1
  }

  pushd "$PLANVEYOR_CTX_ROOT" >/dev/null || return 1
  local generated_machine_authority_json=""
  generated_machine_authority_json="$(planveyor_plan_status_oracle --json "$engine_result")" || {
    popd >/dev/null || true
    return 1
  }
  _planveyor_py - "$generated_machine_authority_json" <<'PY' || {
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("machine_authority_decision_state") != "not_applicable":
    raise SystemExit("generated review-range plan lacks a valid N-A machine-authority carrier")
if payload.get("machine_authority_decision_ref_state") != "valid":
    raise SystemExit("generated review-range draft lacks a validated N-A machine-authority ref")
PY
    popd >/dev/null || true
    return 1
  }
  planveyor_plan_set "$engine_result"
  local plan_set_rc=$?
  popd >/dev/null || return 1
  [[ $plan_set_rc -eq 0 ]] || return $plan_set_rc
  # engaged_public_json_to_path_abi_correction: both states emit one path.
  print -r -- "$engine_result"
}

planveyor_review_range_start() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_review_range_start)" || return $?
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
  # Creates a review-only plan for BASE..HEAD and starts Reviewer on it.
  # Usage:
  #   planveyor_review_range_start                   # uses saved range; EXCLUDE_DOCS=1
  #   planveyor_review_range_start 0|1              # uses saved range; set EXCLUDE_DOCS
  #   planveyor_review_range_start BASE HEAD [0|1]  # explicit range
  local plan_path=""
  plan_path="$(planveyor_review_range_init "$@")" || return 1
  [[ -n "${plan_path//[[:space:]]/}" ]] || return 1
  planveyor_reviewer
}

planveyor_ai_gate() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_ai_gate)" || return $?
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
  # Delegates policy and verdict semantics to scripts/ai_gate.py.
  local root=""
  local gate_script=""

  root="$(_planveyor_project_root)" || return $?
  gate_script="$(_planveyor_script ai_gate.py)" || return 1
  [[ -f "$gate_script" ]] || {
    echo "Missing AI gate script: ${gate_script}" >&2
    return 1
  }

  pushd "$root" >/dev/null || return 1
  _planveyor_py_any -B "$gate_script" --project-root "$root" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_ai_gate_smoke() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_ai_gate_smoke)" || return $?
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
  local receipt_path=""

  while (( $# > 0 )); do
    case "${1:-}" in
      --receipt-path)
        shift
        receipt_path="${1:-}"
        [[ -n "${receipt_path//[[:space:]]/}" ]] || {
          echo "Usage: planveyor_ai_gate_smoke --receipt-path <path>" >&2
          return 1
        }
        ;;
      --help|-h)
        echo "Usage: planveyor_ai_gate_smoke --receipt-path <path>"
        return 0
        ;;
      *)
        echo "Usage: planveyor_ai_gate_smoke --receipt-path <path>" >&2
        return 1
        ;;
    esac
    shift
  done

  [[ -n "${receipt_path//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_ai_gate_smoke --receipt-path <path>" >&2
    return 1
  }

  local caller_root=""
  local receipt_target=""
  caller_root="$(_planveyor_project_root)" || return $?
  receipt_target="$receipt_path"
  if [[ "$receipt_target" != /* ]]; then
    receipt_target="${caller_root}/${receipt_target}"
  fi
  local receipt_dir="${receipt_target:h}"
  mkdir -p "$receipt_dir" || return 1
  receipt_target="${receipt_dir:A}/${receipt_target:t}"

  local tmp_parent="${TMPDIR:-/tmp}"
  local tmpdir=""
  tmpdir="$(mktemp -d "${tmp_parent%/}/planveyor-ai-gate-smoke.XXXXXX")" || return 1
  local fixture_repo="${tmpdir}/repo"
  local policy_path="${tmpdir}/policy.json"
  local gate_script=""
  gate_script="$(_planveyor_script ai_gate.py)" || return 1
  [[ -f "$gate_script" ]] || {
    echo "Missing AI gate script: ${gate_script}" >&2
    command rm -rf "$tmpdir" 2>/dev/null || true
    return 1
  }

  local rc=0
  command git init -q "$fixture_repo" >/dev/null 2>&1 || rc=$?
  if (( rc == 0 )); then
    command git -C "$fixture_repo" config user.name "Test User" >/dev/null 2>&1 || rc=$?
  fi
  if (( rc == 0 )); then
    command git -C "$fixture_repo" config user.email "test""@""example"".""com" >/dev/null 2>&1 || rc=$?
  fi
  if (( rc == 0 )); then
    print -r -- "base" > "${fixture_repo}/README.md" || rc=$?
  fi
  if (( rc == 0 )); then
    command git -C "$fixture_repo" add README.md >/dev/null 2>&1 || rc=$?
  fi
  if (( rc == 0 )); then
    command git -C "$fixture_repo" commit -q -m "Initial commit" >/dev/null 2>&1 || rc=$?
  fi
  if (( rc == 0 )); then
    mkdir -p "${fixture_repo}/scripts" || rc=$?
  fi
  if (( rc == 0 )); then
    print -r -- "print('ai gate smoke')" > "${fixture_repo}/scripts/smoke.py" || rc=$?
  fi
  if (( rc == 0 )); then
    command git -C "$fixture_repo" add scripts/smoke.py >/dev/null 2>&1 || rc=$?
  fi
  if (( rc == 0 )); then
    command git -C "$fixture_repo" commit -q -m "AI-assisted: add smoke helper" >/dev/null 2>&1 || rc=$?
  fi
  if (( rc == 0 )); then
    cat > "$policy_path" <<'JSON' || rc=$?
{
  "schema_version": "ai_gate_policy.v1",
  "verdict_defaults": {
    "unconfirmed_detection": "WARN",
    "missing_optional_scanner": "WARN",
    "scanner_error": "WARN",
    "satd_candidate": "WARN"
  },
  "detection": {
    "author_markers": [
      "openai",
      "anthropic",
      "copilot",
      "cursor",
      "assistant",
      "bot",
      "gpt",
      "claude"
    ],
    "message_markers": [
      "ai-assisted",
      "ai assisted",
      "chatgpt",
      "codex",
      "claude",
      "copilot",
      "cursor",
      "generated-by",
      "generated by",
      "llm",
      "model:"
    ],
    "session_markers": [
      "session sid",
      "codex session",
      "trace_id",
      "thread id",
      "parent thread id"
    ]
  },
  "security_scans": {
    "gitleaks": {
      "enabled": false,
      "required": false
    },
    "semgrep": {
      "enabled": false,
      "required": false,
      "config": ""
    }
  },
  "path_rules": {
    "allow": [
      "scripts/**"
    ],
    "block": [
      ".github/workflows/**",
      "secrets/**",
      "*.pem",
      "*.key"
    ],
    "warn_outside_allowlist": true
  },
  "diff_limits": {
    "max_changed_files_warn": 20,
    "max_changed_files_block": 60,
    "max_lines_added_warn": 600,
    "max_lines_added_block": 1800
  },
  "satd_candidates": {
    "warn_on_any": true,
    "warn_on_blocker_signal": true
  }
}
JSON
  fi
  if (( rc == 0 )); then
    _planveyor_py_any -B "$gate_script" \
      --project-root "$fixture_repo" \
      --range "HEAD~1..HEAD" \
      --policy "$policy_path" \
      --receipt-path "$receipt_target"
    rc=$?
  fi

  if [[ -n "${tmpdir//[[:space:]]/}" && "$tmpdir" == */planveyor-ai-gate-smoke.* && -d "$tmpdir" ]]; then
    command rm -rf "$tmpdir" 2>/dev/null || true
  fi
  return $rc
}

planveyor_arch_merge_notes_start() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_merge_notes_start)" || return $?
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
  # Creates/updates a merge-notes draft for BASE..HEAD via Architect session.
  # Usage:
  #   planveyor_arch_merge_notes_start                     # uses saved range
  #   planveyor_arch_merge_notes_start OUT_PATH            # uses saved range
  #   planveyor_arch_merge_notes_start BASE HEAD [OUT_PATH]
  local base=""
  local head=""
  local out_path=""

  if [[ $# -eq 0 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
  elif [[ $# -eq 1 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
    out_path="${1:-}"
  else
    base="${1:-}"
    head="${2:-}"
    out_path="${3:-}"
    [[ -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || {
      echo "Usage: planveyor_arch_merge_notes_start [OUT_PATH] | planveyor_arch_merge_notes_start <BASE_SHA> <HEAD_SHA> [OUT_PATH]" >&2
      return 1
    }
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect merge_notes)" || return $?
  local sid; sid="$(_planveyor_architect_session_sid_ensure_local_or_init)" || return 1
  local pybin; pybin="$(_planveyor_get_pybin 2>/dev/null || true)"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local ts; ts="$(date +%y%m%d_%H%M)"
  local b7; b7="$(_planveyor_sha7 "$base")"
  local h7; h7="$(_planveyor_sha7 "$head")"

  if [[ -z "${out_path//[[:space:]]/}" ]]; then
    out_path="docs/reviews/${ts}_merge_notes_range_${b7}_${h7}.md"
  fi

  pushd "$root" >/dev/null || return 1
  mkdir -p docs/reviews
  _planveyor_copy_review_template_if_missing "$out_path" "reviews" "_template_merge_notes.md" || {
    popd >/dev/null || return 1
    return 1
  }

  { echo "ROLE=Architect"; echo "BASE=${base}"; echo "HEAD=${head}"; echo "OUT=${out_path}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_arch_plan_harvest_start() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_plan_harvest_start)" || return $?
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
  # Creates/updates plan-harvest report for BASE..HEAD via Architect session.
  # Usage:
  #   planveyor_arch_plan_harvest_start                     # uses saved range
  #   planveyor_arch_plan_harvest_start OUT_PATH            # uses saved range
  #   planveyor_arch_plan_harvest_start BASE HEAD [OUT_PATH]
  local base=""
  local head=""
  local out_path=""

  if [[ $# -eq 0 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
  elif [[ $# -eq 1 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
    out_path="${1:-}"
  else
    base="${1:-}"
    head="${2:-}"
    out_path="${3:-}"
    [[ -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || {
      echo "Usage: planveyor_arch_plan_harvest_start [OUT_PATH] | planveyor_arch_plan_harvest_start <BASE_SHA> <HEAD_SHA> [OUT_PATH]" >&2
      return 1
    }
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect plan_harvest)" || return $?
  local sid; sid="$(_planveyor_architect_session_sid_ensure_local_or_init)" || return 1
  local pybin; pybin="$(_planveyor_get_pybin 2>/dev/null || true)"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local ts; ts="$(date +%y%m%d_%H%M)"
  local b7; b7="$(_planveyor_sha7 "$base")"
  local h7; h7="$(_planveyor_sha7 "$head")"
  local range="${base}..${head}"
  local followups_out="docs/followups/${ts}_followups_range_${b7}_${h7}.md"

  if [[ -z "${out_path//[[:space:]]/}" ]]; then
    out_path="docs/reviews/${ts}_plan_harvest_range_${b7}_${h7}.md"
  fi

  pushd "$root" >/dev/null || return 1
  mkdir -p docs/reviews
  mkdir -p docs/followups
  _planveyor_copy_review_template_if_missing "$out_path" "reviews" "_template_plan_harvest.md" || {
    popd >/dev/null || return 1
    return 1
  }
  if [[ ! -f "$followups_out" ]]; then
    cp "docs/followups/_template_followups_backlog.md" "$followups_out"
  fi

  { echo "ROLE=Architect"; echo "BASE=${base}"; echo "HEAD=${head}"; echo "RANGE=${range}"; echo "OUT=${out_path}"; echo "FOLLOWUPS_OUT=${followups_out}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_arch_post_merge_audit_start() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_post_merge_audit_start)" || return $?
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
  # Creates/updates post-merge audit report for BASE..HEAD via Architect session.
  # Usage:
  #   planveyor_arch_post_merge_audit_start                     # uses saved range
  #   planveyor_arch_post_merge_audit_start AUDIT_PATH          # uses saved range
  #   planveyor_arch_post_merge_audit_start BASE HEAD [AUDIT_PATH]
  local base=""
  local head=""
  local audit_path=""

  if [[ $# -eq 0 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
  elif [[ $# -eq 1 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
    audit_path="${1:-}"
  else
    base="${1:-}"
    head="${2:-}"
    audit_path="${3:-}"
    [[ -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || {
      echo "Usage: planveyor_arch_post_merge_audit_start [AUDIT_PATH] | planveyor_arch_post_merge_audit_start <BASE_SHA> <HEAD_SHA> [AUDIT_PATH]" >&2
      return 1
    }
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect post_merge_audit)" || return $?
  local sid; sid="$(_planveyor_architect_session_sid_ensure_local_or_init)" || return 1
  local pybin; pybin="$(_planveyor_get_pybin 2>/dev/null || true)"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local ts; ts="$(date +%y%m%d_%H%M)"
  local b7; b7="$(_planveyor_sha7 "$base")"
  local h7; h7="$(_planveyor_sha7 "$head")"

  if [[ -z "${audit_path//[[:space:]]/}" ]]; then
    audit_path="docs/reviews/${ts}_post_merge_audit_range_${b7}_${h7}.md"
  fi

  pushd "$root" >/dev/null || return 1
  mkdir -p docs/reviews
  _planveyor_copy_review_template_if_missing "$audit_path" "reviews" "_template_post_merge_audit.md" || {
    popd >/dev/null || return 1
    return 1
  }

  { echo "ROLE=Architect"; echo "BASE=${base}"; echo "HEAD=${head}"; echo "AUDIT=${audit_path}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_arch_canon_sweep_start() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_arch_canon_sweep_start)" || return $?
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
  # Runs canon sweep (docs-only) for BASE..HEAD via Architect session.
  # Usage:
  #   planveyor_arch_canon_sweep_start           # uses saved range
  #   planveyor_arch_canon_sweep_start BASE HEAD
  local base=""
  local head=""
  if [[ $# -eq 0 ]]; then
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
  else
    base="${1:-}"
    head="${2:-}"
    [[ -n "${base//[[:space:]]/}" && -n "${head//[[:space:]]/}" ]] || {
      echo "Usage: planveyor_arch_canon_sweep_start | planveyor_arch_canon_sweep_start <BASE_SHA> <HEAD_SHA>" >&2
      return 1
    }
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local prompt_body=""
  prompt_body="$(_planveyor_role_prompt_body architect canon_sweep)" || return $?
  local sid; sid="$(_planveyor_architect_session_sid_ensure_local_or_init)" || return 1
  local pybin; pybin="$(_planveyor_get_pybin 2>/dev/null || true)"
  local codex_profile=""
  codex_profile="$(_planveyor_profile_for_role_mode architect main)" || return $?
  local -a codex_profile_args
  codex_profile_args=()
  [[ -n "${codex_profile//[[:space:]]/}" ]] && codex_profile_args=(-p "$codex_profile")
  local range="${base}..${head}"

  pushd "$root" >/dev/null || return 1
  { echo "ROLE=Architect"; echo "BASE=${base}"; echo "HEAD=${head}"; echo "RANGE=${range}"; [[ -n "${pybin//[[:space:]]/}" ]] && echo "PYBIN=${pybin}"; printf '%s\n' "$prompt_body"; } \
    | _planveyor_with_role_env architect "$pybin" _planveyor_codex exec -c 'approval_policy="never"' --sandbox workspace-write "${codex_profile_args[@]}" \
        resume "${sid}" -
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_hygiene_list() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_hygiene_list)" || return $?
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
  # Prints full touched-doc inventory for cleanup (legacy optional helper; no deletion).
  # Usage:
  #   planveyor_docs_hygiene_list                # uses saved range
  #   planveyor_docs_hygiene_list BASE HEAD
  #   planveyor_docs_hygiene_list BASE..HEAD     # legacy
  local range=""
  if [[ $# -eq 0 ]]; then
    local base="" head=""
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
    range="${base}..${head}"
  elif [[ $# -eq 1 && "${1}" == *".."* ]]; then
    range="${1}"
  elif [[ $# -ge 2 ]]; then
    range="${1}..${2}"
  else
    echo "Usage: planveyor_docs_hygiene_list | planveyor_docs_hygiene_list <BASE_SHA> <HEAD_SHA> | planveyor_docs_hygiene_list <BASE..HEAD>" >&2
    return 1
  fi
  local root=""
  root="$(_planveyor_project_root)" || return $?
  pushd "$root" >/dev/null || return 1

  echo "[planveyor] Range: ${range}" >&2
  echo "" >&2

  local -a touched_files present_files missing_files
  touched_files=("${(@f)$(git diff --name-only "$range" -- docs/plans docs/followups docs/code_drafts docs/code_reviews docs/doc_reviews docs/reviews docs/snapshots 2>/dev/null | rg -i '\.(md|png|jpe?g|webp)$' || true)}")
  touched_files=("${(@)touched_files:#}")

  local f
  for f in "${touched_files[@]}"; do
    if [[ -f "$f" ]]; then
      present_files+=("$f")
    else
      missing_files+=("$f")
    fi
  done

  if (( ${#present_files} > 0 )); then
    echo "[planveyor] Docs touched in range (present on disk):" >&2
    for f in ${(on)present_files}; do
      local label=""
      if [[ "$f" == docs/plans/* ]]; then
        local status_line=""
        status_line="$(_planveyor_plan_status_line_lenient "$f" 2>/dev/null || true)"
        local status_value=""
        status_value="$(_planveyor_extract_status_value "$status_line" 2>/dev/null || true)"
        status_value="${status_value#"${status_value%%[![:space:]]*}"}"
        status_value="${status_value%"${status_value##*[![:space:]]}"}"
        label="plans (${status_value:-UNCONFIRMED})"
      elif [[ "$f" == docs/code_reviews/assets/* ]]; then
        label="code_reviews/assets"
      elif [[ "$f" == docs/code_reviews/* ]]; then
        label="code_reviews"
      elif [[ "$f" == docs/doc_reviews/* ]]; then
        label="doc_reviews"
      elif [[ "$f" == docs/reviews/* ]]; then
        label="reviews"
      elif [[ "$f" == docs/snapshots/* ]]; then
        label="snapshots"
      elif [[ "$f" == docs/followups/* ]]; then
        label="followups"
      elif [[ "$f" == docs/code_drafts/* ]]; then
        label="code_drafts"
      else
        label="docs"
      fi
      printf '  - %-32s %s\n' "$label" "$f" >&2
    done
    echo "" >&2
  else
    echo "[planveyor] Docs touched in range (present on disk): none" >&2
    echo "" >&2
  fi

  if (( ${#missing_files} > 0 )); then
    echo "[planveyor] Docs touched in range (missing on disk; likely already deleted/cleaned):" >&2
    for f in ${(on)missing_files}; do
      local label=""
      if [[ "$f" == docs/plans/* ]]; then
        label="plans"
      elif [[ "$f" == docs/code_reviews/assets/* ]]; then
        label="code_reviews/assets"
      elif [[ "$f" == docs/code_reviews/* ]]; then
        label="code_reviews"
      elif [[ "$f" == docs/doc_reviews/* ]]; then
        label="doc_reviews"
      elif [[ "$f" == docs/reviews/* ]]; then
        label="reviews"
      elif [[ "$f" == docs/snapshots/* ]]; then
        label="snapshots"
      elif [[ "$f" == docs/followups/* ]]; then
        label="followups"
      elif [[ "$f" == docs/code_drafts/* ]]; then
        label="code_drafts"
      else
        label="docs"
      fi
      printf '  - %-32s %s\n' "$label" "$f" >&2
    done
    echo "" >&2
  fi

  echo "[planveyor] Next (manual):" >&2
  echo "  - перенести знания в канон (canon sweep)" >&2
  echo "  - проверить ссылки: planveyor_doc_lint" >&2
  echo "  - если cleanup идёт вне pipeline или после handoff появились новые doc-only коммиты: сначала прогнать central archive: planveyor_docs_hygiene_archive --range \"${range}\" --apply" >&2
  echo "  - затем получить report-only candidates (авто-матчинг plan↔review/assets): planveyor_docs_hygiene_suggest" >&2
  echo "  - optional cleanup позже: fresh archive/suggest, выбранный git rm и отдельный cleanup commit (см. $(_planveyor_playbooks_root)/post_merge_docs_hygiene.md)" >&2
  popd >/dev/null || return 1
}

planveyor_docs_hygiene_suggest() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_hygiene_suggest)" || return $?
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
  # Prints optional `git rm -r ...` candidates (no deletion).
  # Usage:
  #   planveyor_docs_hygiene_suggest                         # uses saved range
  #   planveyor_docs_hygiene_suggest --range BASE..HEAD
  #   planveyor_docs_hygiene_suggest BASE HEAD
  #   planveyor_docs_hygiene_suggest BASE..HEAD              # legacy
  #   planveyor_docs_hygiene_suggest --include-followups     # include Done followups in rm list
  #   planveyor_docs_hygiene_suggest --include-snapshots      # include snapshots referenced by Done plans
  #   planveyor_docs_hygiene_suggest --verbose                # show low-signal diagnostics
  #   planveyor_docs_hygiene_suggest --fix-missing-blocks dry-run|apply
  local include_followups="0"
  local include_snapshots="0"
  local verbose="0"
  local fix_missing_blocks=""
  local explicit_range=""
  while [[ $# -gt 0 ]]; do
    case "${1}" in
      --include-followups) include_followups="1"; shift ;;
      --include-snapshots) include_snapshots="1"; shift ;;
      --verbose) verbose="1"; shift ;;
      --fix-missing-blocks)
        shift
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_docs_hygiene_suggest [--range BASE..HEAD] [--include-followups] [--include-snapshots] [--verbose] [--fix-missing-blocks dry-run|apply] | planveyor_docs_hygiene_suggest <BASE_SHA> <HEAD_SHA> | planveyor_docs_hygiene_suggest <BASE..HEAD>" >&2
          return 1
        }
        case "${1}" in
          dry-run|apply) fix_missing_blocks="${1}"; shift ;;
          *)
            echo "Usage: planveyor_docs_hygiene_suggest [--range BASE..HEAD] [--include-followups] [--include-snapshots] [--verbose] [--fix-missing-blocks dry-run|apply] | planveyor_docs_hygiene_suggest <BASE_SHA> <HEAD_SHA> | planveyor_docs_hygiene_suggest <BASE..HEAD>" >&2
            return 1
            ;;
        esac
        ;;
      --range)
        shift
        [[ -n "${1:-}" ]] || {
          echo "Usage: planveyor_docs_hygiene_suggest [--range BASE..HEAD] [--include-followups] [--include-snapshots] [--verbose] [--fix-missing-blocks dry-run|apply] | planveyor_docs_hygiene_suggest <BASE_SHA> <HEAD_SHA> | planveyor_docs_hygiene_suggest <BASE..HEAD>" >&2
          return 1
        }
        explicit_range="${1}"
        shift
        ;;
      *) break ;;
    esac
  done

  local range=""
  if [[ -n "$explicit_range" && $# -gt 0 ]]; then
    echo "Usage: planveyor_docs_hygiene_suggest [--range BASE..HEAD] [--include-followups] [--include-snapshots] [--verbose] [--fix-missing-blocks dry-run|apply] | planveyor_docs_hygiene_suggest <BASE_SHA> <HEAD_SHA> | planveyor_docs_hygiene_suggest <BASE..HEAD>" >&2
    return 1
  elif [[ -n "$explicit_range" ]]; then
    range="$explicit_range"
  elif [[ $# -eq 0 ]]; then
    local base="" head=""
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
    range="${base}..${head}"
  elif [[ $# -eq 1 && "${1}" == *".."* ]]; then
    range="${1}"
  elif [[ $# -ge 2 ]]; then
    range="${1}..${2}"
  else
    echo "Usage: planveyor_docs_hygiene_suggest [--range BASE..HEAD] [--include-followups] [--include-snapshots] [--verbose] [--fix-missing-blocks dry-run|apply] | planveyor_docs_hygiene_suggest <BASE_SHA> <HEAD_SHA> | planveyor_docs_hygiene_suggest <BASE..HEAD>" >&2
    return 1
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  pushd "$root" >/dev/null || return 1
  local -a extra_args=()
  [[ "$include_followups" == "1" ]] && extra_args+=(--include-followups)
  [[ "$include_snapshots" == "1" ]] && extra_args+=(--include-snapshots)
  [[ "$verbose" == "1" ]] && extra_args+=(--verbose)
  [[ -n "$fix_missing_blocks" ]] && extra_args+=(--fix-missing-blocks "$fix_missing_blocks")

  _planveyor_py "$(_planveyor_script docs_hygiene_suggest.py)" --range "$range" "${extra_args[@]}"
  local rc=$?
  if (( rc == 0 )); then
    echo "[planveyor] IMPORTANT: this is a report-only handoff; suggested git rm is not semantic closeout." >&2
    echo "[planveyor] Before any later Owner git rm, run fresh central archive:" >&2
    echo "  planveyor_docs_hygiene_archive --range \"${range}\" --apply" >&2
  fi
  popd >/dev/null || return 1
  return $rc
}

planveyor_followups_triage() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_followups_triage)" || return $?
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
  # Triage/import inbox followups into cluster masters.
  #
  # Usage:
  #   planveyor_followups_triage --all --dry-run
  #   planveyor_followups_triage --all --apply
  #   planveyor_followups_triage --range BASE..HEAD --dry-run
  #   planveyor_followups_triage --range BASE..HEAD --apply
  #   planveyor_followups_triage --file docs/followups/<inbox>.md --apply
  #   planveyor_followups_triage BASE HEAD --dry-run
  #   planveyor_followups_triage BASE..HEAD --apply
  #   planveyor_followups_triage --dry-run              # uses saved BASE/HEAD
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  local use_all="0"
  local use_file="0"
  local -a forwarded_args=()
  local arg=""
  for arg in "$@"; do
    if [[ "$arg" == "--all" ]]; then
      use_all="1"
      continue
    fi
    if [[ "$arg" == "--file" ]]; then
      use_file="1"
    fi
    forwarded_args+=("$arg")
  done
  set -- "${forwarded_args[@]}"

  if [[ "$use_file" == "1" ]]; then
    pushd "$root" >/dev/null || return 1
    _planveyor_python_dispatch "$pybin" "$(_planveyor_script followups_triage.py)" "$@"
    local rc=$?
    popd >/dev/null || return 1
    return $rc
  fi

  local range=""
  if [[ "$use_all" == "1" ]]; then
    range=""
  elif [[ "${1:-}" == "--range" ]]; then
    shift
    range="${1:-}"
    shift || true
  elif [[ $# -ge 2 && "${1}" != --* && "${2}" != --* ]]; then
    range="${1}..${2}"
    shift 2
  elif [[ $# -ge 1 && "${1}" != --* && "${1}" == *".."* ]]; then
    range="${1}"
    shift
  else
    local base="" head=""
    base="$(_planveyor_get_range_base)" || return 1
    head="$(_planveyor_get_range_head)" || return 1
    range="${base}..${head}"
  fi

  pushd "$root" >/dev/null || return 1
  if [[ "$use_all" == "1" ]]; then
    _planveyor_python_dispatch "$pybin" "$(_planveyor_script followups_triage.py)" --all "$@"
  else
    [[ -n "${range//[[:space:]]/}" ]] || {
      echo "Usage: planveyor_followups_triage [--all] | [--file docs/followups/<inbox>.md] | [--range BASE..HEAD|BASE HEAD] [--dry-run|--apply]" >&2
      popd >/dev/null || return 1
      return 1
    }
    _planveyor_python_dispatch "$pybin" "$(_planveyor_script followups_triage.py)" --range "$range" "$@"
  fi
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_followups_lint() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_followups_lint)" || return $?
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
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  _planveyor_python_dispatch "$pybin" "$(_planveyor_script followups_lint.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_followups_apply() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_followups_apply)" || return $?
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
  # V2 has one durable row writer.  This wrapper deliberately forwards only
  # the frozen manifest; it does not synthesize rows or mutate queue state.
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  _planveyor_python_dispatch "$pybin" "$(_planveyor_script followups_apply.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_followups_reconcile() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_followups_reconcile)" || return $?
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
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  _planveyor_python_dispatch "$pybin" "$(_planveyor_script followups_reconcile.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_followups_promote() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_followups_promote)" || return $?
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
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  _planveyor_python_dispatch "$pybin" "$(_planveyor_script followups_promote.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_process_improvements_promote() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_process_improvements_promote)" || return $?
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
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  _planveyor_python_dispatch "$pybin" "$(_planveyor_script process_improvements_promote.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_process_improvements_reconcile() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_process_improvements_reconcile)" || return $?
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
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  _planveyor_python_dispatch "$pybin" "$(_planveyor_script process_improvements_reconcile.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_followups_query() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_followups_query)" || return $?
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
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  _planveyor_python_dispatch "$pybin" "$(_planveyor_script followups_query.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

_planveyor_rollout_packet_helper_run() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_rollout_packet_helper_run)" || return $?
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
  local subcommand="${1:-}"
  [[ -n "${subcommand//[[:space:]]/}" ]] || {
    echo "Usage: _planveyor_rollout_packet_helper_run <create|show|import-instructions|lint|ack|query|reconcile|inbox|adoption-plan|outcome-set> [args...]" >&2
    return 1
  }
  shift || true

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tooling_root="$(_planveyor_root)"
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script rollout_packet.py)" \
    --repo-root "$root" \
    --tooling-root "$tooling_root" \
    "$subcommand" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_rollout_packet_create() {
  # Create a source-local rollout packet skeleton in docs/rollout_packets/.
  #
  # Usage:
  #   planveyor_rollout_packet_create <target_repo> <topic_slug> [--source-plan docs/plans/<...>.md] [--target-kind plan_adoption] [--queue-after-import yes|no] [--dry-run]
  _planveyor_rollout_packet_helper_run create "$@"
}

planveyor_rollout_packet_show() {
  # Show a source-local rollout packet summary or raw content.
  #
  # Usage:
  #   planveyor_rollout_packet_show docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md [--raw]
  _planveyor_rollout_packet_helper_run show "$@"
}

planveyor_rollout_packet_import_instructions() {
  # Print target-local import instructions from an existing source-local packet.
  #
  # Usage:
  #   planveyor_rollout_packet_import_instructions docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md [--print-target-plan-seed]
  _planveyor_rollout_packet_helper_run import-instructions "$@"
}

planveyor_rollout_packet_lint() {
  # Run read-only grammar lint for source-local rollout packets.
  #
  # Usage:
  #   planveyor_rollout_packet_lint --all [--json]
  #   planveyor_rollout_packet_lint docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md [--json]
  _planveyor_rollout_packet_helper_run lint "$@"
}

planveyor_rollout_packet_ack() {
  # Record a source-side packet receipt acknowledgement/status transition.
  #
  # Usage:
  #   planveyor_rollout_packet_ack --packet docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md --status imported --target-plan docs/plans/<...>.md
  #   planveyor_rollout_packet_ack --packet docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md --status superseded --reason "..."
  _planveyor_rollout_packet_helper_run ack "$@"
}

planveyor_rollout_packet_query() {
  # List source-local rollout packets with receipt/outcome readback fields.
  #
  # Usage:
  #   planveyor_rollout_packet_query [--status open|imported|superseded|cancelled|all] [--json]
  _planveyor_rollout_packet_helper_run query "$@"
}

planveyor_rollout_packet_reconcile() {
  # Report stale or inconsistent source-local rollout packets and target outcomes without mutation.
  #
  # Usage:
  #   planveyor_rollout_packet_reconcile --report [--older-than-days 7] [--target-root "${PLANVEYOR_TARGET_ROOT:-$HOME/planveyor}" --target-repo planveyor] [--json]
  _planveyor_rollout_packet_helper_run reconcile "$@"
}

planveyor_shared_docs_mirror_drift() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_shared_docs_mirror_drift)" || return $?
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
  # Compare the exact shared process-doc mirror set without writing target files.
  #
  # Usage:
  #   planveyor_shared_docs_mirror_drift --target-root "${PLANVEYOR_TARGET_ROOT:-$HOME/planveyor}" --json
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script shared_docs_mirror_drift.py)" --content-profile-id "$content_profile_id" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_mirror_strict_gate() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_mirror_strict_gate)" || return $?
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
  # Fail closed on exact shared process-doc mirror drift without writing target files.
  #
  # Usage:
  #   planveyor_mirror_strict_gate --target-root "${PLANVEYOR_TARGET_ROOT:-$HOME/planveyor}" --json
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script shared_docs_mirror_drift.py)" --content-profile-id "$content_profile_id" --fail-on-drift "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

_planveyor_upstream_request_helper_run() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader _planveyor_upstream_request_helper_run)" || return $?
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
  local subcommand="${1:-}"
  [[ -n "${subcommand//[[:space:]]/}" ]] || {
    echo "Usage: _planveyor_upstream_request_helper_run <show|import|ack|query> [args...]" >&2
    return 1
  }
  shift || true

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local tooling_root="$(_planveyor_root)"
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  _planveyor_python_dispatch "$pybin" "$(_planveyor_script upstream_request.py)" \
    --repo-root "$root" \
    --tooling-root "$tooling_root" \
    "$subcommand" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_upstream_request_show() {
  # Show a source-local upstream request packet summary or raw content.
  #
  # Usage:
  #   planveyor_upstream_request_show docs/upstream_packets/<YYMMDD_HHMM>_<origin_repo>_<topic>.md [--raw]
  _planveyor_upstream_request_helper_run show "$@"
}

planveyor_upstream_request_import() {
  # Import an open upstream request into source-local process improvements.
  #
  # Usage:
  #   planveyor_upstream_request_import --packet docs/upstream_packets/<YYMMDD_HHMM>_<origin_repo>_<topic>.md [--owner Architect] [--promotion-class canon_update]
  _planveyor_upstream_request_helper_run import "$@"
}

planveyor_upstream_request_ack() {
  # Record source-side decision/execution refs on an imported upstream request.
  #
  # Usage:
  #   planveyor_upstream_request_ack --packet docs/upstream_packets/<YYMMDD_HHMM>_<origin_repo>_<topic>.md --source-decision-ref docs/plans/<...> [--source-execution-ref docs/plans/<...>] [--dry-run]
  _planveyor_upstream_request_helper_run ack "$@"
}

planveyor_upstream_request_query() {
  # List source-local upstream requests by explicit fields.
  #
  # Usage:
  #   planveyor_upstream_request_query [--status open|imported|decided|superseded|cancelled|all] [--origin-repo <sibling>] [--json]
  _planveyor_upstream_request_helper_run query "$@"
}

planveyor_rollout_packet_inbox() {
  # List source packets addressed to the current target repo.
  #
  # Usage:
  #   planveyor_rollout_packet_inbox [--target-repo <repository-id>] [--status open] [--include-untracked] [--json]
  _planveyor_rollout_packet_helper_run inbox "$@"
}

planveyor_rollout_packet_adoption_plan() {
  # Create a target-local adoption plan from matching source packets.
  #
  # Usage:
  #   planveyor_rollout_packet_adoption_plan [--target-repo <repository-id>] [--status open] [--include-untracked] [--out docs/plans/<...>.md]
  _planveyor_rollout_packet_helper_run adoption-plan "$@"
}

planveyor_rollout_packet_outcome_set() {
  # Record one canonical target-local outcome in a generated structured carrier.
  #
  # Usage:
  #   planveyor_rollout_packet_outcome_set --target-plan docs/plans/<...>.md --packet-id <id> --packet-path docs/rollout_packets/<...>.md --outcome <canonical-or-alias>
  _planveyor_rollout_packet_helper_run outcome-set "$@"
}

planveyor_rollout_packet_harvest() {
  # Alias for the target-local packet inbox -> adoption-plan step.
  #
  # Usage:
  #   planveyor_rollout_packet_harvest [--target-repo <repository-id>] [--status open] [--include-untracked] [--out docs/plans/<...>.md]
  planveyor_rollout_packet_adoption_plan "$@"
}

planveyor_docs_index_build() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_index_build)" || return $?
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
  # Build local docs retrieval index (SQLite FTS5) for canon/followups/plans (derived cache).
  #
  # Usage:
  #   planveyor_docs_index_build canon [--db PATH] [--root docs] [--chunk-target-tokens N] [--force-rebuild]
  #   planveyor_docs_index_build followups [--db PATH] [--root docs] [--force-rebuild]
  #   planveyor_docs_index_build plans [--db PATH] [--root docs] [--chunk-target-tokens N] [--force-rebuild]
  #   planveyor_docs_index_build all [--db PATH] [--root docs] [--chunk-target-tokens N] [--force-rebuild]
  local corpus="${1:-}"
  [[ -n "${corpus//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_docs_index_build <canon|followups|plans|all> [--db PATH] [--root docs] [--chunk-target-tokens N] [--force-rebuild]" >&2
    return 1
  }
  shift || true

  local -a args
  args=("$@")
  local has_db=0
  local arg=""
  for arg in "${args[@]}"; do
    if [[ "$arg" == "--db" || "$arg" == --db=* ]]; then
      has_db=1
      break
    fi
  done
  if (( has_db == 0 )); then
    args+=(--db "$(_planveyor_docs_index_db_default)")
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  local rc=0
  if [[ "$corpus" == "all" ]]; then
    # `--force-rebuild` drops tables; when building all corpuses into one DB we must
    # drop only once (before the first corpus), otherwise later runs would erase earlier corpuses.
    local -a args_no_force
    args_no_force=("${args[@]:#--force-rebuild}")

    PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_index_build.py)" --corpus canon "${args[@]}" || rc=$?
    if (( rc != 0 )); then
      popd >/dev/null || return 1
      return $rc
    fi
    PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_index_build.py)" --corpus followups "${args_no_force[@]}" || rc=$?
    if (( rc != 0 )); then
      popd >/dev/null || return 1
      return $rc
    fi
    PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_index_build.py)" --corpus plans "${args_no_force[@]}" || rc=$?
    popd >/dev/null || return 1
    return $rc
  fi

  if [[ "$corpus" != "canon" && "$corpus" != "followups" && "$corpus" != "plans" ]]; then
    echo "ERROR: unsupported corpus: ${corpus} (expected: canon|followups|plans|all)" >&2
    popd >/dev/null || return 1
    return 1
  fi

  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_index_build.py)" --corpus "$corpus" "${args[@]}"
  rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_db() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_db)" || return $?
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
  # Print default docs retrieval index DB path (derived cache).
  echo "$(_planveyor_docs_index_db_default)"
}

planveyor_docs_retrieve_log() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_retrieve_log)" || return $?
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
  local raw="${PLANVEYOR_DOCS_RETRIEVE_LOG:-.tmp/planveyor_docs_retrieve_queries.jsonl}"
  local raw_lc="${(L)raw}"
  if [[ "$raw_lc" == "0" || "$raw_lc" == "off" || "$raw_lc" == "false" || "$raw_lc" == "no" || "$raw_lc" == "disable" || "$raw_lc" == "disabled" ]]; then
    echo "disabled"
    return 0
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  if [[ "$raw" == /* ]]; then
    echo "$raw"
    return 0
  fi
  echo "${root}/${raw}"
}

planveyor_docs_retrieve_outcome_log() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_retrieve_outcome_log)" || return $?
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
  local raw="${PLANVEYOR_DOCS_RETRIEVE_OUTCOME_LOG:-.tmp/planveyor_docs_retrieve_outcomes.jsonl}"
  local raw_lc="${(L)raw}"
  if [[ "$raw_lc" == "0" || "$raw_lc" == "off" || "$raw_lc" == "false" || "$raw_lc" == "no" || "$raw_lc" == "disable" || "$raw_lc" == "disabled" ]]; then
    echo "disabled"
    return 0
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  if [[ "$raw" == /* ]]; then
    echo "$raw"
    return 0
  fi
  echo "${root}/${raw}"
}

planveyor_docs_retrieve_read_log() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_retrieve_read_log)" || return $?
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
  local raw="${PLANVEYOR_DOCS_RETRIEVE_READ_LOG:-.tmp/planveyor_docs_retrieve_reads.jsonl}"
  local raw_lc="${(L)raw}"
  if [[ "$raw_lc" == "0" || "$raw_lc" == "off" || "$raw_lc" == "false" || "$raw_lc" == "no" || "$raw_lc" == "disable" || "$raw_lc" == "disabled" ]]; then
    echo "disabled"
    return 0
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  if [[ "$raw" == /* ]]; then
    echo "$raw"
    return 0
  fi
  echo "${root}/${raw}"
}

planveyor_docs_retrieve_outcome() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_retrieve_outcome)" || return $?
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
  # Append an explicit outcome row for a docs_retrieve query event.
  #
  # Usage:
  #   planveyor_docs_retrieve_outcome --event-id <event_id> --outcome used --opened-file docs/foo.md --cited-file docs/foo.md --note "used for plan"
  #   planveyor_docs_retrieve_outcome --latest --outcome miss
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_retrieve_outcome.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_retrieve_metrics() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_retrieve_metrics)" || return $?
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
  # Summarize docs_retrieve query, outcome, and read/open logs.
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_retrieve_metrics.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_retrieve() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_retrieve)" || return $?
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
  # Query docs retrieval index (SQLite FTS5). Output includes jump hint `path:start_line`.
  #
  # Usage:
  #   planveyor_docs_retrieve canon [--db PATH] [--k N|--all] [--format text|md|json|--md] [--files] [--min-score 0..1] [--no-context] [--log-file PATH|--no-log] "contract notice"
  #   planveyor_docs_retrieve followups [--db PATH] [--k N|--all] [--format text|md|json|--md] [--files] [--min-score 0..1] [--no-context] [--log-file PATH|--no-log] "upgrade conflict"
  #   planveyor_docs_retrieve plans [--db PATH] [--k N|--all] [--format text|md|json|--md] [--files] [--min-score 0..1] [--no-context] [--log-file PATH|--no-log] "decomposition queue"
  local corpus="${1:-}"
  [[ -n "${corpus//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_docs_retrieve <canon|followups|plans> [--db PATH] [--k N|--all] [--format text|md|json|--md] [--files] [--min-score 0..1] [--no-context] [--log-file PATH|--no-log] \"FTS query\"" >&2
    return 1
  }
  shift || true
  if [[ "$corpus" != "canon" && "$corpus" != "followups" && "$corpus" != "plans" ]]; then
    echo "ERROR: unsupported corpus: ${corpus} (expected: canon|followups|plans)" >&2
    echo "Usage: planveyor_docs_retrieve <canon|followups|plans> [--db PATH] [--k N|--all] [--format text|md|json|--md] [--files] [--min-score 0..1] [--no-context] [--log-file PATH|--no-log] \"FTS query\"" >&2
    return 2
  fi

  local -a args
  args=("$@")
  local has_db=0
  local arg=""
  for arg in "${args[@]}"; do
    if [[ "$arg" == "--db" || "$arg" == --db=* ]]; then
      has_db=1
      break
    fi
  done
  if (( has_db == 0 )); then
    args+=(--db "$(_planveyor_docs_index_db_default)")
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_retrieve.py)" --corpus "$corpus" "${args[@]}"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_lookup() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_lookup)" || return $?
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
  # One-shot retrieval path: query the index, instrumented-read selected files, and print a receipt skeleton.
  #
  # Usage:
  #   planveyor_docs_lookup canon --k 5 "contract notice"
  #   planveyor_docs_lookup plans --min-score 0.35 "docs retrieval receipt"
  local corpus="${1:-}"
  [[ -n "${corpus//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_docs_lookup <canon|followups|plans> [docs_retrieve flags except --format/--files/--md] \"FTS query\"" >&2
    return 1
  }
  shift || true
  if [[ "$corpus" != "canon" && "$corpus" != "followups" && "$corpus" != "plans" ]]; then
    echo "ERROR: unsupported corpus: ${corpus} (expected: canon|followups|plans)" >&2
    return 2
  fi

  local -a args
  args=("$@")
  local arg=""
  for arg in "${args[@]}"; do
    if [[ "$arg" == "--format" || "$arg" == --format=* || "$arg" == "--files" || "$arg" == "--md" ]]; then
      echo "ERROR: planveyor_docs_lookup owns output mode; do not pass --format/--files/--md" >&2
      return 2
    fi
  done

  local has_db=0
  for arg in "${args[@]}"; do
    if [[ "$arg" == "--db" || "$arg" == --db=* ]]; then
      has_db=1
      break
    fi
  done
  if (( has_db == 0 )); then
    args+=(--db "$(_planveyor_docs_index_db_default)")
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  local retrieve_json=""
  retrieve_json="$(PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_retrieve.py)" --corpus "$corpus" --format json "${args[@]}")"
  local rc=$?
  if (( rc != 0 )); then
    [[ -n "$retrieve_json" ]] && print -r -- "$retrieve_json"
    popd >/dev/null || return 1
    return $rc
  fi

  local event_id=""
  local files_count="0"
  local filelist=""
  event_id="$(PYTHONDONTWRITEBYTECODE=1 "$pybin" -c 'import json,sys; data=json.load(sys.stdin); print(data.get("meta",{}).get("event_id",""))' <<< "$retrieve_json")" || {
    popd >/dev/null || return 1
    return 1
  }
  files_count="$(PYTHONDONTWRITEBYTECODE=1 "$pybin" -c 'import json,sys; data=json.load(sys.stdin); print(len(data.get("files") or []))' <<< "$retrieve_json")" || {
    popd >/dev/null || return 1
    return 1
  }
  filelist="$(PYTHONDONTWRITEBYTECODE=1 "$pybin" -c 'import json,sys; data=json.load(sys.stdin); print("\n".join(data.get("files") or []))' <<< "$retrieve_json")" || {
    popd >/dev/null || return 1
    return 1
  }

  echo "docs_lookup (corpus=${corpus}, event_id=${event_id}, files=${files_count})"
  local read_output=""
  if [[ -n "${filelist//[[:space:]]/}" ]]; then
    echo "selected files:"
    print -r -- "$filelist" | sed 's/^/- /'
    echo

    read_output="$(print -r -- "$filelist" | PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_multi_get.py)" - --format md)"
    rc=$?
    [[ -n "$read_output" ]] && print -r -- "$read_output"
    if (( rc != 0 )); then
      popd >/dev/null || return 1
      return $rc
    fi
  else
    echo "selected files: N/A (why=no retrieval hits)"
  fi

  local read_event_id="N/A"
  if [[ "$read_output" =~ 'event_id=([^,)]+)' ]]; then
    read_event_id="${match[1]}"
  fi
  local read_open="N/A (why=not_used_for_decision)"
  if [[ -n "${filelist//[[:space:]]/}" ]]; then
    read_open="ok"
  fi
  local read_log_status="disabled"
  local read_log_path=""
  read_log_path="$(planveyor_docs_retrieve_read_log)"
  if [[ "$read_log_path" == "disabled" ]]; then
    read_log_status="disabled"
  elif [[ -f "$read_log_path" ]]; then
    read_log_status="present"
  else
    read_log_status="missing"
  fi

  local files_inline="N/A (why=no retrieval hits)"
  if [[ -n "${filelist//[[:space:]]/}" ]]; then
    files_inline="$(PYTHONDONTWRITEBYTECODE=1 "$pybin" -c 'import sys; print(", ".join(line.strip() for line in sys.stdin if line.strip()))' <<< "$filelist")"
  fi

  echo
  echo "## Retrieval telemetry receipt"
  echo "- query_event_id: ${event_id}"
  echo "- used_for_decision: false"
  echo "- read_open: ${read_open}"
  echo "- read_log_status: ${read_log_status}"
  echo "- read_event_id: ${read_event_id}"
  echo "- outcome: not_evaluated"
  echo "- outcome_reason: N/A (why=outcome not marked yet)"
  echo "- cited/opened files: ${files_inline}"
  echo "- no_op_reason: not_used_for_decision"
  echo
  echo "Outcome follow-up:"
  echo "  planveyor_docs_retrieve_outcome --event-id ${event_id} --outcome used --note \"<short reason>\""
  popd >/dev/null || return 1
  return 0
}

planveyor_docs_get() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_get)" || return $?
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
  # Read one document (full or around line) with safety caps and path-only read/open telemetry.
  #
  # Usage:
  #   planveyor_docs_get docs/tools/snippet.md:46
  #   planveyor_docs_get docs/tools/snippet.md --from-line 40 --lines 80 --format md
  #   planveyor_docs_get docs/tools/snippet.md --full --max-bytes 80000 --format json --no-context --no-read-log
  local target="${1:-}"
  [[ -n "${target//[[:space:]]/}" ]] || {
    echo "Usage: planveyor_docs_get <path|path:line> [--from-line N --lines M | --full] [--max-bytes N] [--max-lines N] [--format text|md|json] [--no-context] [--read-log PATH|--no-read-log]" >&2
    return 1
  }
  shift || true

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_get.py)" "$target" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_multi_get() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_multi_get)" || return $?
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
  # Batch-read documents with glob/@filelist/stdin inputs and path-only read/open telemetry.
  #
  # Usage:
  #   planveyor_docs_multi_get "docs/plans/*.md" --format md
  #   planveyor_docs_multi_get @.tmp/files.txt --format json --no-context --read-log .tmp/reads.jsonl
  #   planveyor_docs_retrieve plans --files "docs retrieval" | planveyor_docs_multi_get - --format md --max-bytes 200000
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_multi_get.py)" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_context_check() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_context_check)" || return $?
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
  # Check context coverage and suggest missing path prefixes.
  #
  # Usage:
  #   planveyor_docs_context_check --corpus plans
  #   planveyor_docs_context_check --corpus canon --format json
  #   planveyor_docs_context_check --corpus followups --max-uncovered 100 --max-hints 30
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1

  local -a args
  args=("$@")
  local has_db=0
  local arg=""
  for arg in "${args[@]}"; do
    if [[ "$arg" == "--db" || "$arg" == --db=* ]]; then
      has_db=1
      break
    fi
  done
  if (( has_db == 0 )); then
    args+=(--db "$(_planveyor_docs_index_db_default)")
  fi

  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_context_check.py)" "${args[@]}"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_archive_db() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_archive_db)" || return $?
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
  # Print default central docs archive DB path (append-only; prefer main worktree).
  echo "$(_planveyor_docs_archive_db_default)"
}

planveyor_docs_archive_query() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_archive_query)" || return $?
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
  # Query the central docs archive (SQLite FTS5) for deleted temp docs.
  #
  # Usage:
  #   planveyor_docs_archive_query --k 12 "contract upgrade notice"
  #   planveyor_docs_archive_query --profile all --k 12 "contract upgrade notice"
  #   planveyor_docs_archive_query --kind plan --k 20 "docs retrieval index adoption"
  #   planveyor_docs_archive_query --md --k 12 "decomposition queue"
  #   planveyor_docs_archive_query --db /abs/path/to/archive.sqlite --k 12 "..."
  local -a forwarded=()
  local db=""
  local has_profile=0
  local has_kind=0
  while [[ $# -gt 0 ]]; do
    case "${1}" in
      --db)
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_docs_archive_query [--db PATH] [--profile signal|all] [--kind KIND] [--k N] [--md] \"query\"" >&2; return 1; }
        db="${1}"
        shift
        ;;
      --db=*)
        db="${1#--db=}"
        shift
        ;;
      --profile)
        has_profile=1
        forwarded+=("${1}")
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_docs_archive_query [--db PATH] [--profile signal|all] [--kind KIND] [--k N] [--md] \"query\"" >&2; return 1; }
        forwarded+=("${1}")
        shift
        ;;
      --profile=*)
        has_profile=1
        forwarded+=("${1}")
        shift
        ;;
      --kind)
        has_kind=1
        forwarded+=("${1}")
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_docs_archive_query [--db PATH] [--profile signal|all] [--kind KIND] [--k N] [--md] \"query\"" >&2; return 1; }
        forwarded+=("${1}")
        shift
        ;;
      --kind=*)
        has_kind=1
        forwarded+=("${1}")
        shift
        ;;
      *)
        forwarded+=("${1}")
        shift
        ;;
    esac
  done
  [[ -n "${db//[[:space:]]/}" ]] || db="$(_planveyor_docs_archive_db_default)"
  if (( has_profile == 0 && has_kind == 0 )); then
    forwarded=(--profile signal "${forwarded[@]}")
  fi

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_archive.py)" --content-profile-id "$content_profile_id" --db "$db" query "${forwarded[@]}"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_archive_show() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_archive_show)" || return $?
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
  # Show full archived doc by --id or --path (most recent).
  #
  # Usage:
  #   planveyor_docs_archive_show --id 123
  #   planveyor_docs_archive_show --path docs/plans/260205_0153_process_docs_retrieval_index_adoption.md
  #   planveyor_docs_archive_show --db /abs/path/to/archive.sqlite --id 123
  local -a forwarded=()
  local db=""
  while [[ $# -gt 0 ]]; do
    case "${1}" in
      --db)
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_docs_archive_show [--db PATH] (--id N | --path PATH)" >&2; return 1; }
        db="${1}"
        shift
        ;;
      --db=*)
        db="${1#--db=}"
        shift
        ;;
      *)
        forwarded+=("${1}")
        shift
        ;;
    esac
  done
  [[ -n "${db//[[:space:]]/}" ]] || db="$(_planveyor_docs_archive_db_default)"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_archive.py)" --content-profile-id "$content_profile_id" --db "$db" show "${forwarded[@]}"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_archive_snapshot_info() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_archive_snapshot_info)" || return $?
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
  # Print portable snapshot facts for the central docs archive DB.
  #
  # Usage:
  #   planveyor_docs_archive_snapshot_info
  #   planveyor_docs_archive_snapshot_info --json
  #   planveyor_docs_archive_snapshot_info --db /abs/path/to/archive.sqlite
  local -a forwarded=()
  local db=""
  while [[ $# -gt 0 ]]; do
    case "${1}" in
      --db)
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_docs_archive_snapshot_info [--db PATH] [--json]" >&2; return 1; }
        db="${1}"
        shift
        ;;
      --db=*)
        db="${1#--db=}"
        shift
        ;;
      *)
        forwarded+=("${1}")
        shift
        ;;
    esac
  done
  [[ -n "${db//[[:space:]]/}" ]] || db="$(_planveyor_docs_archive_db_default)"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_archive.py)" --content-profile-id "$content_profile_id" --db "$db" snapshot-info "${forwarded[@]}"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_archive_snapshot_export() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_archive_snapshot_export)" || return $?
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
  # Export portable snapshot artifact/manifest for the central docs archive DB.
  #
  # Usage:
  #   planveyor_docs_archive_snapshot_export --backend git_text_export --output-dir docs/_meta/archive_snapshots/current --force
  #   planveyor_docs_archive_snapshot_export --backend git_whole_sqlite --output-dir .tmp/archive_snapshot --force
  #   planveyor_docs_archive_snapshot_export --backend s3_minio_sqlite --object-uri s3://bucket/key --object-sha256 <sha> --object-size-bytes <n>
  local -a forwarded=()
  local db=""
  while [[ $# -gt 0 ]]; do
    case "${1}" in
      --db)
        shift
        [[ -n "${1:-}" ]] || { echo "Usage: planveyor_docs_archive_snapshot_export [--db PATH] [--backend git_text_export|git_whole_sqlite|s3_minio_sqlite] [--output-dir DIR] [--force]" >&2; return 1; }
        db="${1}"
        shift
        ;;
      --db=*)
        db="${1#--db=}"
        shift
        ;;
      *)
        forwarded+=("${1}")
        shift
        ;;
    esac
  done
  [[ -n "${db//[[:space:]]/}" ]] || db="$(_planveyor_docs_archive_db_default)"

  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_archive.py)" --content-profile-id "$content_profile_id" --db "$db" snapshot-export "${forwarded[@]}"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_archive_snapshot_restore() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_archive_snapshot_restore)" || return $?
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
  # Restore portable snapshot artifact/manifest into a local SQLite FTS DB.
  #
  # Usage:
  #   planveyor_docs_archive_snapshot_restore --manifest docs/_meta/archive_snapshots/current/manifest.json --dest-db .tmp/restored.sqlite --replace --query "..." --expect-min-hits 1
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_archive.py)" --content-profile-id "$content_profile_id" snapshot-restore "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_archive_snapshot_validate() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_archive_snapshot_validate)" || return $?
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
  # Validate a portable snapshot manifest/artifact.
  #
  # Usage:
  #   planveyor_docs_archive_snapshot_validate --manifest docs/_meta/archive_snapshots/current/manifest.json --verify-artifact
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_archive.py)" --content-profile-id "$content_profile_id" snapshot-validate "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_docs_hygiene_archive() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_docs_hygiene_archive)" || return $?
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
  # Archive temp-doc cleanup candidates (plans/reviews/drafts) into the central archive DB.
  #
  # Can be run from any repo/worktree: scan happens against the current cwd,
  # while the DB path stays centralized in the main worktree.
  #
  # Usage:
  #   planveyor_docs_hygiene_archive --range BASE..HEAD --apply
  #   planveyor_docs_hygiene_archive --range BASE..HEAD            # dry-run
  local main_root="$(_planveyor_main_root)"
  local root=""
  root="$(_planveyor_project_root)" || return $?
  local db_path="$(_planveyor_docs_archive_db_default)"

  if [[ "$root" != "$main_root" ]]; then
    echo "[planveyor] Central archive DB: ${db_path} (current repo/worktree: ${root})" >&2
  fi

  local pybin=""
  pybin="$(_planveyor_get_pybin)" || return 1
  local content_profile_id=""
  content_profile_id="$(_planveyor_content_profile_id)" || return $?
  pushd "$root" >/dev/null || return 1
  PYTHONDONTWRITEBYTECODE=1 "$pybin" "$(_planveyor_script docs_hygiene_archive.py)" --content-profile-id "$content_profile_id" --db "$db_path" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}









# --- retained child entry -------------------------------------------------
_planveyor_sibling_ensure_native_session() {
  local role="$1" runtime="$2" project="$3" invocation="$4"
  local session_file="$project/.planveyor.session.$role" sid="" decision=init
  if [[ -e "$session_file" || -L "$session_file" ]]; then
    [[ -f "$session_file" && ! -L "$session_file" ]] || {
      print -u2 -r -- 'planveyor sibling: invalid native session pointer'; return 3
    }
    sid="$(planveyor_session "$role")" || return $?
    [[ "$sid" != '<SESSION_ID>' ]] || { print -u2 -r -- 'planveyor sibling: placeholder native session pointer'; return 3; }
    [[ "$sid" != *[[:space:]]* ]] && _planveyor_is_uuid "$sid" || {
      print -u2 -r -- 'planveyor sibling: invalid native session pointer'; return 3
    }
    decision="$(_planveyor_py_any "$runtime/scripts/sibling_runbook.py" \
      --runtime-root "$runtime" --project-root "$project" --invocation-root "$invocation" \
      --internal session-check "$role" "$sid")" || return $?
  fi
  if [[ "$decision" == ready ]]; then
    local codex_home="$(_planveyor_codex_home_effective)" stats_out="" stats_rc=0
    stats_out="$(_planveyor_py_any "$(_planveyor_codex_session_stats_script)" \
      --sid "$sid" --codex-home "$codex_home" --mode quick --format kv 2>&1)" || stats_rc=$?
    if (( stats_rc == 0 )); then
      return 0
    fi
    if (( stats_rc != 1 )) || [[ "$stats_out" != 'Session not found:'* ]]; then
      print -u2 -r -- "$stats_out"; return "$stats_rc"
    fi
    decision=init
  fi
  [[ "$decision" == init ]] || { print -u2 -r -- 'planveyor sibling: invalid session readback'; return 3; }
  case "$role" in
    architect) planveyor_arch_init || return $? ;;
    manager) planveyor_manager_init || return $? ;;
    *) return 64 ;;
  esac
  sid="$(planveyor_session "$role")" || return $?
  _planveyor_session_authority_resume_validate "$role" "$sid" || return $?
}

planveyor_sibling() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_sibling)" || return $?
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
  _planveyor_cli_require_attested_child || return $?
  local runtime="$(_planveyor_root)" project="$(_planveyor_project_root)"
  local invocation="${PLANVEYOR_INVOCATION_ROOT:-$project}" action="${1:---help}" arg=""
  local -a helper_args=(--runtime-root "$runtime" --project-root "$project" --invocation-root "$invocation")
  for arg in "$@"; do
    case "$arg" in
      --runtime-root|--runtime-root=*|--project-root|--project-root=*|--invocation-root|--invocation-root=*)
        print -u2 -r -- 'planveyor sibling: context selectors are reserved; use --project before sibling'
        return 64 ;;
    esac
  done
  if [[ "$action" == help ]]; then
    set -- --help
  fi
  for arg in "$@"; do
    if [[ "$arg" == -h || "$arg" == --help ]]; then
      _planveyor_py_any "$runtime/scripts/sibling_runbook.py" "${helper_args[@]}" "$@"
      return $?
    fi
  done
  if [[ "$action" == --internal && "${2:-}" == set-done && $# == 3 ]]; then
    _planveyor_py_any "$runtime/scripts/sibling_runbook.py" "${helper_args[@]}" --internal admit-done "$3" || return $?
    _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
    _planveyor_plan_set_header_status "$project/$3" Done
    return $?
  fi
  if [[ "$action" == architect || "$action" == run || "$action" == tui ]]; then
    # Invocation-local, unexported and readonly; validate before selection,
    # bootstrap/resume or any Owner-answer consumption.
    local sibling_commit_policy=human_explicit
    [[ "$action" != tui ]] || sibling_commit_policy=native_existing
    local -r +x PLANVEYOR_SIBLING_COMMIT_POLICY="$sibling_commit_policy" || return 3
    [[ ${(t)PLANVEYOR_SIBLING_COMMIT_POLICY-} == scalar-local-readonly &&
       "$PLANVEYOR_SIBLING_COMMIT_POLICY" == "$sibling_commit_policy" ]] || {
      print -u2 -r -- 'planveyor sibling: invalid invocation commit policy'
      return 3
    }
    local selection=""
    selection="$(_planveyor_py_any "$runtime/scripts/sibling_runbook.py" "${helper_args[@]}" "$@")" || return $?
    local role=manager
    [[ "$action" != architect ]] || role=architect
    _planveyor_sibling_ensure_native_session "$role" "$runtime" "$project" "$invocation" || return $?
    if [[ "$action" == architect ]]; then
      case "$selection" in
        'architect initial draft') planveyor_arch_initial || return $? ;;
        *) planveyor_arch || return $? ;;
      esac
    elif [[ "$action" == tui ]]; then
      # Preserve the native result, including its runtime-drift diagnostic.
      # A later convenience readback must not run after the interactive call.
      planveyor_manager_collab_tui
      return $?
    else
      shift
      planveyor_manager_collab_cmd run "$selection" "$@" || return $?
    fi
    _planveyor_py_any "$runtime/scripts/sibling_runbook.py" "${helper_args[@]}" plan
    return $?
  fi
  (( $# )) || set -- --help
  _planveyor_py_any "$runtime/scripts/sibling_runbook.py" "${helper_args[@]}" "$@"
}

planveyor_consumer_init() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_consumer_init)" || return $?
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
  local runtime=""
  runtime="$(_planveyor_root)" || return $?
  _planveyor_py_any "$(_planveyor_script consumer_contract.py)" --runtime-root "$runtime" init "$@"
}

planveyor_consumer_doctor() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_consumer_doctor)" || return $?
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
  (( $# == 0 )) || { print -u2 -r -- 'Usage: planveyor_consumer_doctor (with --project TARGET)'; return 64; }
  local runtime="" project=""
  runtime="$(_planveyor_root)" || return $?
  project="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$(_planveyor_script consumer_contract.py)" --runtime-root "$runtime" doctor "$project"
}

planveyor_plan_lint() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_plan_lint)" || return $?
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
  local lint_script=""
  lint_script="$(_planveyor_script plan_lint.py)" || return $?
  _planveyor_py_any "$lint_script" "$@"
}

planveyor_runtime_py() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_runtime_py)" || return $?
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
  (( $# >= 1 )) || { print -u2 -r -- 'Usage: planveyor_runtime_py <approved-helper.py> [args...]'; return 64; }
  local script_name="$1"
  shift
  case "$script_name" in
    censor_receipts_harvest.py|custom_pipeline_dirty_state.py|docs_context_check.py|\
    docs_multi_get.py|docs_retrieve.py|docs_retrieve_metrics.py|\
    followups_capture.py|followups_index_rebuild.py|followups_lint.py|\
    merge_tracker_oracle.py|plan_harvest_lint.py|plan_lint.py|\
    plan_queue.py|plan_status_oracle.py|process_improvements_collect.py|\
    process_improvements_lint.py|review_artifact_lint.py|\
    role_outcome_receipt.py|rollout_packet.py|satd_scan.py|\
    semantic_review_observation.py|upstream_request.py|zcode_bootstrap_lifecycle.py) ;;
    *) print -u2 -r -- "Unsupported runtime helper: $script_name"; return 64 ;;
  esac
  local helper=""
  helper="$(_planveyor_script "$script_name")" || return $?
  local root=""
  root="$(_planveyor_project_root)" || return $?
  pushd "$root" >/dev/null || return 1
  _planveyor_py_any "$helper" "$@"
  local rc=$?
  popd >/dev/null || return 1
  return $rc
}

planveyor_contract_upgrade() {
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_contract_upgrade)" || return $?
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
  local runtime="" project=""
  runtime="$(_planveyor_root)" || return $?
  project="$(_planveyor_project_root)" || return $?
  _planveyor_py_any "$(_planveyor_script consumer_contract.py)" --runtime-root "$runtime" upgrade "$project" "$@"
}

# `bin/planveyor` is the only supported process boundary.  It constructs a
# clean zsh child, binds the physical runtime and consumer project roots, and
# loads this facade through the retained authority loader.  Keep command
# selection here finite: the child must not turn an argv token into shell code
# or expose private `_planveyor_*` helpers.
_planveyor_cli_allowed_commands() {
  print -l -- \
    planveyor_consumer_init \
    planveyor_consumer_doctor \
    planveyor_plan_lint \
    planveyor_runtime_py \
    planveyor_contract_upgrade \
    planveyor_ai_gate \
    planveyor_ai_gate_smoke \
    planveyor_analysis_init \
    planveyor_arch \
    planveyor_arch_canon_sweep_start \
    planveyor_arch_censor \
    planveyor_arch_collab_resume \
    planveyor_arch_docs_general \
    planveyor_arch_followups \
    planveyor_arch_init \
    planveyor_arch_initial \
    planveyor_arch_inno_resume \
    planveyor_arch_innovations_tui \
    planveyor_arch_merge_notes_start \
    planveyor_arch_plan_harvest_start \
    planveyor_arch_post_merge_audit_start \
    planveyor_arch_process_collab_tui \
    planveyor_arch_process_roles_tui \
    planveyor_arch_resume \
    planveyor_arch_roles_resume \
    planveyor_bare_entrypoints_doctor \
    planveyor_clear_owner_answers \
    planveyor_code_draft_stub_from_plan \
    planveyor_coder \
    planveyor_coder_censor \
    planveyor_coder_docs_general \
    planveyor_coder_followups \
    planveyor_coder_init \
    planveyor_coder_resume \
    planveyor_collab_state_write_alive \
    planveyor_custom_role_step \
    planveyor_decomposition_collab \
    planveyor_decomposition_collab_tui \
    planveyor_decomposition_init \
    planveyor_decomposition_seed_promote \
    planveyor_doc_lint \
    planveyor_docs_archive_db \
    planveyor_docs_archive_query \
    planveyor_docs_archive_show \
    planveyor_docs_archive_snapshot_export \
    planveyor_docs_archive_snapshot_info \
    planveyor_docs_archive_snapshot_restore \
    planveyor_docs_archive_snapshot_validate \
    planveyor_docs_closeout \
    planveyor_docs_context_check \
    planveyor_docs_db \
    planveyor_docs_get \
    planveyor_docs_hygiene_archive \
    planveyor_docs_hygiene_list \
    planveyor_docs_hygiene_suggest \
    planveyor_docs_index_build \
    planveyor_docs_lookup \
    planveyor_docs_multi_get \
    planveyor_docs_retrieve \
    planveyor_docs_retrieve_log \
    planveyor_docs_retrieve_metrics \
    planveyor_docs_retrieve_outcome \
    planveyor_docs_retrieve_outcome_log \
    planveyor_docs_retrieve_read_log \
    planveyor_entry_doctor \
    planveyor_followups_apply \
    planveyor_followups_capture \
    planveyor_followups_lint \
    planveyor_followups_promote \
    planveyor_followups_query \
    planveyor_followups_reconcile \
    planveyor_followups_triage \
    planveyor_help \
    planveyor_manager \
    planveyor_manager_collab \
    planveyor_manager_collab_cmd \
    planveyor_manager_collab_tui \
    planveyor_manager_custom_pipeline \
    planveyor_manager_custom_pipeline_cmd \
    planveyor_manager_custom_pipeline_tui \
    planveyor_manager_init \
    planveyor_manager_invocation_checkpoint \
    planveyor_manager_resume \
    planveyor_merge_apply_collab_cmd \
    planveyor_merge_apply_collab_tui \
    planveyor_merge_bundle_report \
    planveyor_merge_collab_cmd \
    planveyor_merge_collab_tui \
    planveyor_merge_init \
    planveyor_merge_next \
    planveyor_merge_range_stats_json \
    planveyor_merge_range_verdict_digest \
    planveyor_merge_tracker_ensure \
    planveyor_merge_tracker_init \
    planveyor_merge_tracker_next_step \
    planveyor_merge_tracker_show \
    planveyor_merge_tracker_tick \
    planveyor_mirror_strict_gate \
    planveyor_owner_answers_set \
    planveyor_plan_bundle \
    planveyor_plan_closeout_preflight \
    planveyor_plan_list \
    planveyor_plan_list_status \
    planveyor_plan_provenance_context \
    planveyor_plan_provenance_stamp \
    planveyor_plan_set \
    planveyor_plan_status_oracle \
    planveyor_planner \
    planveyor_planner_censor \
    planveyor_planner_docs_general \
    planveyor_planner_followups \
    planveyor_planner_init \
    planveyor_planner_resume \
    planveyor_planning_wave_readback \
    planveyor_planning_wave_readback_json \
    planveyor_planpath \
    planveyor_planqueue_metrics \
    planveyor_planqueue_metrics_json \
    planveyor_post_merge_docs_finalize_tick \
    planveyor_post_merge_docs_hygiene_suggest_gate \
    planveyor_post_merge_operational_receipt \
    planveyor_post_merge_packetization_gate \
    planveyor_post_merge_packetization_gate_recover \
    planveyor_post_merge_ready_to_push_closeout \
    planveyor_post_merge_receipt_preflight \
    planveyor_post_merge_receipt_skeleton \
    planveyor_process_improvements_promote \
    planveyor_process_improvements_reconcile \
    planveyor_profile \
    planveyor_profile_clear \
    planveyor_profile_set \
    planveyor_pybin_file \
    planveyor_pybin_set \
    planveyor_q_advance_json \
    planveyor_q_append \
    planveyor_q_clear \
    planveyor_q_closeout_json \
    planveyor_q_final_report \
    planveyor_q_history \
    planveyor_q_history_json \
    planveyor_q_next_json \
    planveyor_q_planpath_override_json \
    planveyor_q_recover \
    planveyor_q_set \
    planveyor_q_show \
    planveyor_q_small_slice \
    planveyor_q_small_slice_json \
    planveyor_q_stop_json \
    planveyor_range_base \
    planveyor_range_head \
    planveyor_range_merge \
    planveyor_range_set \
    planveyor_range_set_auto_merge \
    planveyor_range_set_merge \
    planveyor_review_range_init \
    planveyor_review_range_start \
    planveyor_review_risk_packet \
    planveyor_review_target_snapshot \
    planveyor_reviewer \
    planveyor_reviewer_code_contracts \
    planveyor_reviewer_code_contracts_init \
    planveyor_reviewer_code_contracts_resume \
    planveyor_reviewer_code_risk \
    planveyor_reviewer_code_risk_init \
    planveyor_reviewer_code_risk_resume \
    planveyor_reviewer_docs_general \
    planveyor_reviewer_followups \
    planveyor_reviewer_init \
    planveyor_reviewer_resume \
    planveyor_role_bundle_prompt_manifest \
    planveyor_role_run \
    planveyor_role_run_child_dispatch \
    planveyor_role_run_probe \
    planveyor_role_run_receipt_check \
    planveyor_role_runner_preflight \
    planveyor_rollout_packet_ack \
    planveyor_rollout_packet_adoption_plan \
    planveyor_rollout_packet_create \
    planveyor_rollout_packet_harvest \
    planveyor_rollout_packet_import_instructions \
    planveyor_rollout_packet_inbox \
    planveyor_rollout_packet_lint \
    planveyor_rollout_packet_outcome_set \
    planveyor_rollout_packet_query \
    planveyor_rollout_packet_reconcile \
    planveyor_rollout_packet_show \
    planveyor_runner \
    planveyor_runner_clear \
    planveyor_runner_file \
    planveyor_runner_matrix \
    planveyor_runner_resolve_strict \
    planveyor_runner_set \
    planveyor_runtime_info \
    planveyor_session \
    planveyor_session_set \
    planveyor_shared_docs_mirror_drift \
    planveyor_show \
    planveyor_show_collab \
    planveyor_show_manual \
    planveyor_show_process \
    planveyor_status_line \
    planveyor_upstream_request_ack \
    planveyor_upstream_request_import \
    planveyor_upstream_request_query \
    planveyor_upstream_request_show \
    planveyor_verify \
    planveyor_wave_telemetry_report \
    planveyor_wave_telemetry_report_json
}

_planveyor_cli_require_attested_child() {
  [[ "${PLANVEYOR_CHILD_SHELL_V1:-}" == "planveyor-child-shell.v1" ]] || {
    print -u2 -r -- "planveyor: commands must run through bin/planveyor"
    return 126
  }
  [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == "pinned" ]] || {
    print -u2 -r -- "planveyor: retained runtime source is not pinned"
    return 126
  }
  [[ "${(t)_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY-}" == "scalar-readonly" ]] || {
    print -u2 -r -- "planveyor: retained runtime pin summary is unavailable"
    return 126
  }
  _planveyor_runtime_api_guard 5 5 || return $?
  local runtime_commit=""
  runtime_commit="$(_planveyor_authority_bridge runtime-field \
    --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" \
    --field commit 2>/dev/null || true)"
  [[ ${#runtime_commit} -eq 40 && "$runtime_commit" != *[^0-9a-f]* ]] || {
    print -u2 -r -- "planveyor: retained runtime pin is not Git-backed"
    return 126
  }
  _planveyor_authority_validate_runtime_pin
}

planveyor_runtime_info() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_runtime_info)" || return $?
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

  local runtime_root="" project_root="" source_kind="" runtime_commit="" python_executable=""
  runtime_root="$(_planveyor_authority_runtime_root)" || return $?
  project_root="$(_planveyor_project_root)" || return $?
  python_executable="$(_planveyor_get_pybin)" || return $?
  if [[ "${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}" == pinned && "${(t)_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY-}" == scalar-readonly ]]; then
    runtime_commit="$(_planveyor_authority_bridge runtime-field --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" --field commit 2>/dev/null || true)"
    if [[ ${#runtime_commit} -eq 40 && "$runtime_commit" != *[^0-9a-f]* ]]; then
      source_kind=git
    else
      source_kind="$(_planveyor_authority_bridge runtime-field --runtime-pin-summary "$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY" --field source_kind)" || return $?
    fi
  else
    source_kind="${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-unknown}"
  fi
  print -r -- "runtime_root=${runtime_root}"
  print -r -- "project_root=${project_root}"
  print -r -- "source_state=${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-unknown}"
  print -r -- "source_kind=${source_kind}"
  print -r -- "python_executable=${python_executable}"
  print -r -- "child_shell=${PLANVEYOR_CHILD_SHELL_V1:-absent}"
}

planveyor_entry_doctor() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_entry_doctor)" || return $?
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

  _planveyor_cli_require_attested_child || return $?
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  planveyor_runtime_info
}

planveyor_role_run_child_dispatch() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_role_run_child_dispatch)" || return $?
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

  (( $# == 3 )) || {
    print -u2 -r -- "Usage: planveyor_role_run_child_dispatch <wrapper> <runner_role> <runner>"
    return 2
  }
  local wrapper="$1" runner_role="$2" runner="$3"
  case "${wrapper}:${runner_role}" in
    planveyor_arch:architect|planveyor_arch_initial:architect|planveyor_arch_censor:architect|planveyor_coder:coder|planveyor_coder_censor:coder|planveyor_planner:planner|planveyor_planner_censor:planner|planveyor_reviewer:reviewer|planveyor_reviewer_code_risk:reviewer|planveyor_reviewer_code_contracts:reviewer|planveyor_manager:manager) ;;
    *)
      print -u2 -r -- "planveyor: unsupported role child wrapper/role pair"
      return 2
      ;;
  esac
  case "${runner_role}:${runner}" in
    architect:codex|manager:codex|coder:codex|planner:codex|planner:claude|reviewer:codex|reviewer:claude) ;;
    *)
      print -u2 -r -- "planveyor: runner is not allowed for role=${runner_role}"
      return 2
      ;;
  esac

  _planveyor_cli_require_attested_child || return $?
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?

  local saved_runner="_planveyor_child_dispatch_runner_${RANDOM}_${$}"
  functions -c planveyor_runner "$saved_runner" || return 1
  planveyor_runner() {
    if [[ "${1:-}" == "$runner_role" ]]; then
      print -r -- "$runner"
      return 0
    fi
    "$saved_runner" "$@"
  }

  local rc=0
  case "$wrapper" in
    planveyor_arch) planveyor_arch ;;
    planveyor_arch_initial) planveyor_arch_initial ;;
    planveyor_arch_censor) planveyor_arch_censor ;;
    planveyor_coder) planveyor_coder ;;
    planveyor_coder_censor) planveyor_coder_censor ;;
    planveyor_planner) planveyor_planner ;;
    planveyor_planner_censor) planveyor_planner_censor ;;
    planveyor_reviewer) planveyor_reviewer ;;
    planveyor_reviewer_code_risk) planveyor_reviewer_code_risk ;;
    planveyor_reviewer_code_contracts) planveyor_reviewer_code_contracts ;;
    planveyor_manager) planveyor_manager ;;
  esac
  rc=$?
  functions -c "$saved_runner" planveyor_runner || return 1
  unfunction "$saved_runner"
  return "$rc"
}

planveyor_cli() {
  emulate -L zsh
  local _planveyor_ctx_json=""
  _planveyor_ctx_json="$(_planveyor_authority_context_for_reader planveyor_cli)" || return $?
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

  _planveyor_cli_require_attested_child || return $?
  _planveyor_authority_before_effect_json "$PLANVEYOR_CTX_JSON" >/dev/null || return $?
  local project_root=""
  project_root="$(_planveyor_project_root)" || return $?
  [[ "$project_root" == "${PLANVEYOR_PROJECT_ROOT:-}" ]] || {
    print -u2 -r -- "planveyor: child project root does not match its authority context"
    return 126
  }

  if (( $# == 0 )); then
    planveyor_help
    return $?
  fi
  case "${1:-}" in
    sibling)
      shift
      planveyor_sibling "$@"
      return $?
      ;;
    help|-h|--help)
      shift
      if [[ "${1:-}" == sibling ]]; then
        shift
        planveyor_sibling --help "$@"
        return $?
      fi
      planveyor_help "$@"
      return $?
      ;;
  esac

  local command_name="$1"
  shift
  local allowed="" admitted=0
  for allowed in "${(@f)$(_planveyor_cli_allowed_commands)}"; do
    [[ "$command_name" == "$allowed" ]] || continue
    admitted=1
    break
  done
  (( admitted )) || {
    print -u2 -r -- "planveyor: unsupported child command: ${command_name}"
    return 64
  }
  [[ -n "${functions[$command_name]-}" ]] || {
    print -u2 -r -- "planveyor: allowed command is unavailable in the retained runtime: ${command_name}"
    return 126
  }
  "$command_name" "$@"
}

# Complete the source pin only after every facade/module definition is loaded.
# A failed post-observation leaves no authoritative loaded-state marker behind.
_planveyor_authority_finalize_loaded_source || return $?

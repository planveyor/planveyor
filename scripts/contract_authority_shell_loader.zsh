# Caller-owned loader template. The installer embeds the Python literal here;
# this template and the selected interpreter are outside the runtime pin.
# The rendered file is also the supported operator/test-harness entry.

planveyor_source_runtime() {
  local facade="${1:-}" python_bin="" candidate="" stream_dir="" stream_fd=""
  local header="" fields="" body_fd="" producer_rc=0 source_rc=0
  local expected_runtime_pin="${2:-}"
  local -a source_arguments=()
  (( $# >= 1 && $# <= 2 )) || return 1
  [[ "$facade" == /* ]] || {
    print -u2 -r -- 'planveyor authority: loader requires an absolute facade path'
    return 1
  }
  # Path selection belongs to this caller-owned anchor. Freeze its canonical
  # spelling before the descriptor reader enforces no-follow traversal.
  facade="${facade:A}"
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
  if [[ -n "${_PLANVEYOR_AUTHORITY_SOURCE_STATE+x}" ]]; then
    [[ ${(t)_PLANVEYOR_AUTHORITY_SOURCE_STATE-} == scalar-readonly ]] || {
      print -u2 -r -- 'planveyor authority: exported or mutable loaded source state is rejected'
      return 1
    }
    [[ ${(t)_PLANVEYOR_AUTHORITY_PYTHON_BIN-} == scalar-readonly && -x "${_PLANVEYOR_AUTHORITY_PYTHON_BIN:-}" ]] || {
      print -u2 -r -- 'planveyor authority: loaded interpreter state is invalid'
      return 1
    }
    python_bin="$_PLANVEYOR_AUTHORITY_PYTHON_BIN"
    if [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]]; then
      [[ ${(t)_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY-} == scalar-readonly ]] || {
        print -u2 -r -- 'planveyor authority: loaded runtime pin state is invalid'
        return 1
      }
      [[ -n "$expected_runtime_pin" ]] || expected_runtime_pin="$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY"
    fi
  else
  for candidate in "$(command -v python3 2>/dev/null)" \
    "$(command -v python 2>/dev/null)" "$(command -v python3.12 2>/dev/null)" \
    "$(command -v python3.11 2>/dev/null)" "$(command -v python3.10 2>/dev/null)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    "$candidate" -I -B -c 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)' >/dev/null 2>&1 || continue
    python_bin="${candidate:A}"
    break
  done
  fi
  [[ -n "$python_bin" ]] || {
    print -u2 -r -- 'planveyor authority: no Python 3.10-3.12 found on PATH (checked python3, python, python3.12, python3.11, python3.10); activate the Planveyor environment with Python 3.12 from requirements-dev.lock so that its python3 comes first on PATH, then rerun'
    return 1
  }
  local -r PLANVEYOR_SOURCE_BOOTSTRAP="$(cat <<'PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL_EOF'
@PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL@
PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL_EOF
)"
  local -r PLANVEYOR_SOURCE_PYTHON="$python_bin"
  local -r PLANVEYOR_SOURCE_PATH="$facade"
  local -r PLANVEYOR_SOURCE_SEAL='planveyor-source-buffer.v1'
  source_arguments=(--path "$facade" --runtime-root "${facade:h:h}")
  [[ -z "$expected_runtime_pin" ]] || source_arguments+=(--runtime-pin-summary "$expected_runtime_pin")
  stream_dir="$(umask 077; mktemp -d "${TMPDIR:-/tmp}/planveyor-authority-source.XXXXXXXX")" || return 1
  {
    (umask 077; "$python_bin" -I -B -c "$PLANVEYOR_SOURCE_BOOTSTRAP" \
      "${facade:h}/contract_authority_bridge.py" shell-source \
      "${source_arguments[@]}" > "$stream_dir/body")
    producer_rc=$?
    (( producer_rc == 0 )) || return "$producer_rc"
    exec {stream_fd}< "$stream_dir/body" || return 1
    rm -f -- "$stream_dir/body" || return 1
    IFS= read -r header <&$stream_fd || return 1
    fields="$("$python_bin" -I -B -c '
import json, sys
h = json.loads(sys.argv[1])
assert type(h) is dict and set(h) == {"version", "source_path", "runtime_root", "source", "source_descriptor", "runtime_pin"}
assert h["version"] == 1 and type(h["version"]) is int
assert h["source_path"] == sys.argv[2] and h["runtime_root"] == sys.argv[3]
assert type(h["source"]) is dict and set(h["source"]) == {"mode", "sha256", "size"}
assert type(h["source_descriptor"]) is dict and type(h["runtime_pin"]) is dict
print(json.dumps(h["source_descriptor"], sort_keys=True, separators=(",", ":")) + "\t" + json.dumps(h["runtime_pin"], sort_keys=True, separators=(",", ":")))
' "$header" "$facade" "${facade:h:h}")" || return 1
    local -r PLANVEYOR_SOURCE_DESCRIPTOR="${fields%%$'\t'*}"
    local -r PLANVEYOR_SOURCE_RUNTIME_PIN="${fields#*$'\t'}"
    # Complete the remaining bytes before sourcing: Linux reopens a regular
    # /dev/fd path at offset zero, so the consumed header must be excluded.
    (umask 077; command cat <&$stream_fd > "$stream_dir/source") || return $?
    exec {body_fd}< "$stream_dir/source" || return 1
    rm -f -- "$stream_dir/source" || return 1
    rmdir -- "$stream_dir" || return 1
    source "/dev/fd/$body_fd"
    source_rc=$?
    return "$source_rc"
  } always {
    [[ -z "$body_fd" ]] || exec {body_fd}<&-
    [[ -z "$stream_fd" ]] || exec {stream_fd}<&-
    [[ ! -d "$stream_dir" ]] || { rm -f -- "$stream_dir/body" "$stream_dir/source"; rmdir -- "$stream_dir"; }
  }
}

# Nested sources use the same completed private stream protocol. The bridge
# verifies its complete result before emitting bytes; no repository path is
# reopened by zsh after that verification.
_planveyor_caller_source_buffer() {
  local relative_path="${1:-}" stream_dir="" stream_fd="" producer_rc=0
  local python_bin="" bootstrap="" runtime_root="" pin=""
  if [[ -n "${_PLANVEYOR_AUTHORITY_SOURCE_STATE+x}" ]]; then
    _planveyor_authority_source_state_internal && [[ "$_PLANVEYOR_AUTHORITY_SOURCE_STATE" == pinned ]] || return 1
    python_bin="$_PLANVEYOR_AUTHORITY_PYTHON_BIN"
    bootstrap="$_PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL"
    runtime_root="$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT"
    pin="$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY"
  else
    [[ ${(t)PLANVEYOR_SOURCE_SEAL-} == scalar-local-readonly &&
       "${PLANVEYOR_SOURCE_SEAL:-}" == planveyor-source-buffer.v1 &&
       ${(t)PLANVEYOR_SOURCE_PATH-} == scalar-local-readonly &&
       ${(t)PLANVEYOR_SOURCE_RUNTIME_PIN-} == scalar-local-readonly &&
       ${(t)PLANVEYOR_SOURCE_PYTHON-} == scalar-local-readonly &&
       ${(t)PLANVEYOR_SOURCE_BOOTSTRAP-} == scalar-local-readonly ]] || return 1
    python_bin="$PLANVEYOR_SOURCE_PYTHON"
    bootstrap="$PLANVEYOR_SOURCE_BOOTSTRAP"
    runtime_root="${PLANVEYOR_SOURCE_PATH:h:h}"
    pin="$PLANVEYOR_SOURCE_RUNTIME_PIN"
  fi
  [[ -n "$python_bin" && -n "$bootstrap" && -n "$runtime_root" && -n "$pin" ]] || return 1
  stream_dir="$(umask 077; mktemp -d "${TMPDIR:-/tmp}/planveyor-authority-module.XXXXXXXX")" || return 1
  {
    (umask 077; "$python_bin" -I -B -c "$bootstrap" \
      "$runtime_root/scripts/contract_authority_bridge.py" source-buffer \
      --runtime-pin-summary "$pin" --relative-path "$relative_path" > "$stream_dir/body")
    producer_rc=$?
    (( producer_rc == 0 )) || return "$producer_rc"
    exec {stream_fd}< "$stream_dir/body" || return 1
    rm -f -- "$stream_dir/body" || return 1
    rmdir -- "$stream_dir" || return 1
    source "/dev/fd/$stream_fd"
  } always {
    [[ -z "$stream_fd" ]] || exec {stream_fd}<&-
    [[ ! -d "$stream_dir" ]] || { rm -f -- "$stream_dir/body"; rmdir -- "$stream_dir"; }
  }
}

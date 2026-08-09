#!/usr/bin/env bash
# WattHog installer for Linux.
#
# Installs WattHog into an isolated per-user environment and puts a launcher
# into ~/.local/bin. No root required.
#
#   curl -fsSL https://raw.githubusercontent.com/scarrymany/watthog/main/install.sh | bash
#
# Kept in plain ASCII to match install.ps1, where non-ASCII text breaks
# Windows PowerShell 5.1.

set -euo pipefail

REPOSITORY_URL="https://github.com/scarrymany/watthog.git"
INSTALL_ROOT="${WATTHOG_HOME:-$HOME/.local/share/watthog}"
BIN_DIR="${WATTHOG_BIN:-$HOME/.local/bin}"
MINIMUM_PYTHON_MINOR=10

YELLOW=$'\033[1;33m'
GREEN=$'\033[0;32m'
CYAN=$'\033[0;36m'
GREY=$'\033[0;90m'
RED=$'\033[0;31m'
RESET=$'\033[0m'

step() { printf '  %s%s%s\n' "$CYAN" "$1" "$RESET"; }
done_step() { printf '  %s%s%s\n' "$GREEN" "$1" "$RESET"; }
fail() { printf '  %sError: %s%s\n' "$RED" "$1" "$RESET" >&2; exit 1; }

printf '\n  %sWattHog - PC power consumption meter%s\n\n' "$YELLOW" "$RESET"

case "$(uname -s)" in
    Linux) ;;
    Darwin) fail "macOS is not supported: there is no RAPL and no equivalent of the PDH counters." ;;
    *) fail "Unknown system $(uname -s). Only Linux and Windows are supported." ;;
esac

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MINIMUM_PYTHON_MINOR) else 1)" 2>/dev/null; then
                printf '%s' "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON="$(find_python)" || fail "Python 3.$MINIMUM_PYTHON_MINOR or newer is required. Install it with your package manager."
step "Python: $("$PYTHON" --version 2>&1)"

if command -v pipx >/dev/null 2>&1; then
    step "Installing with pipx..."
    pipx install --force "git+$REPOSITORY_URL"
    done_step "Installed with pipx."
else
    step "Installing into an isolated environment: $INSTALL_ROOT"
    "$PYTHON" -m venv "$INSTALL_ROOT/venv" 2>/dev/null || fail "could not create a venv. Install the python3-venv package."
    "$INSTALL_ROOT/venv/bin/pip" install --quiet --upgrade pip
    "$INSTALL_ROOT/venv/bin/pip" install --quiet --upgrade "git+$REPOSITORY_URL"

    mkdir -p "$BIN_DIR"
    ln -sf "$INSTALL_ROOT/venv/bin/watthog" "$BIN_DIR/watthog"
    done_step "Installed: $BIN_DIR/watthog"

    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) printf '  %sAdd this to ~/.bashrc: export PATH="%s:$PATH"%s\n' "$GREY" "$BIN_DIR" "$RESET" ;;
    esac
fi

printf '\n  %sDone. Run it:%s\n' "$YELLOW" "$RESET"
printf '    watthog              %s# menu%s\n' "$GREY" "$RESET"
printf '    watthog run          %s# 60 second measurement%s\n' "$GREY" "$RESET"
printf '    watthog info         %s# detected hardware and sensors%s\n' "$GREY" "$RESET"
printf '\n  %sTip: sudo watthog run unlocks RAPL and measures real CPU power.%s\n' "$GREY" "$RESET"
printf '  %sThe application interface is in Russian. Author: @yeet17%s\n\n' "$GREY" "$RESET"

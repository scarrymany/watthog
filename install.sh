#!/usr/bin/env bash
# Установщик WattHog для Linux.
#
# Ставит WattHog в изолированное окружение пользователя и кладёт запускалку в
# ~/.local/bin. Права root не нужны.
#
#   curl -fsSL https://raw.githubusercontent.com/scarrymany/watthog/main/install.sh | bash

set -euo pipefail

REPOSITORY_URL="https://github.com/scarrymany/watthog.git"
INSTALL_ROOT="${WATTHOG_HOME:-$HOME/.local/share/watthog}"
BIN_DIR="${WATTHOG_BIN:-$HOME/.local/bin}"
MINIMUM_PYTHON_MINOR=10

YELLOW=$'\033[1;33m'
GREEN=$'\033[0;32m'
CYAN=$'\033[0;36m'
GREY=$'\033[0;90m'
RESET=$'\033[0m'

step() { printf '  %s%s%s\n' "$CYAN" "$1" "$RESET"; }
done_step() { printf '  %s%s%s\n' "$GREEN" "$1" "$RESET"; }
fail() { printf '  %sОшибка: %s%s\n' $'\033[0;31m' "$1" "$RESET" >&2; exit 1; }

printf '\n  %sWattHog - измеритель энергопотребления ПК%s\n\n' "$YELLOW" "$RESET"

case "$(uname -s)" in
    Linux) ;;
    Darwin) fail "macOS не поддерживается: там нет ни RAPL, ни аналога счётчиков PDH." ;;
    *) fail "Неизвестная система $(uname -s). Поддерживаются Linux и Windows." ;;
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

PYTHON="$(find_python)" || fail "нужен Python 3.$MINIMUM_PYTHON_MINOR или новее. Установите его через пакетный менеджер дистрибутива."
step "Python: $("$PYTHON" --version 2>&1)"

if command -v pipx >/dev/null 2>&1; then
    step "Ставлю через pipx..."
    pipx install --force "git+$REPOSITORY_URL"
    done_step "Установлено через pipx."
else
    step "Ставлю в изолированное окружение: $INSTALL_ROOT"
    "$PYTHON" -m venv "$INSTALL_ROOT/venv" 2>/dev/null || fail "не удалось создать venv. Установите пакет python3-venv."
    "$INSTALL_ROOT/venv/bin/pip" install --quiet --upgrade pip
    "$INSTALL_ROOT/venv/bin/pip" install --quiet --upgrade "git+$REPOSITORY_URL"

    mkdir -p "$BIN_DIR"
    ln -sf "$INSTALL_ROOT/venv/bin/watthog" "$BIN_DIR/watthog"
    done_step "Установлено: $BIN_DIR/watthog"

    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *) printf '  %sДобавьте в ~/.bashrc: export PATH="%s:$PATH"%s\n' "$GREY" "$BIN_DIR" "$RESET" ;;
    esac
fi

printf '\n  %sГотово. Запуск:%s\n' "$YELLOW" "$RESET"
printf '    watthog              %s# меню%s\n' "$GREY" "$RESET"
printf '    watthog run          %s# замер 60 секунд%s\n' "$GREY" "$RESET"
printf '    watthog info         %s# железо и источники данных%s\n' "$GREY" "$RESET"
printf '\n  %sСовет: sudo watthog run даст доступ к RAPL и точной мощности процессора.%s\n' "$GREY" "$RESET"
printf '  %sАвтор: @yeet17%s\n\n' "$GREY" "$RESET"

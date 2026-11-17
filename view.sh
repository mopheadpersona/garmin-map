#!/bin/bash
# Открывает собранную карту в QMapShack и оставляет окно открытым.
#
#   ./view.sh [регион]        # по умолчанию prague
#
# После новой сборки запустите ещё раз: окно перезапустится с новой картой.
# Если закрывать QMapShack через Cmd+Q, место и масштаб сохранятся.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 scripts/view.py "${1:-prague}"

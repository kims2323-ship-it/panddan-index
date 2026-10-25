#!/bin/zsh
# 매일 09:30 에 main.py 를 실행하는 launchd 에이전트 설치/제거.
#   ./schedule/install_launchd.sh          설치
#   ./schedule/install_launchd.sh remove   제거
set -e
ROOT="${0:A:h:h}"
LABEL="com.sia.panddan-index"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [[ "$1" == "remove" ]]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"; echo "제거 완료"; exit 0
fi

PY="$(command -v python3)"
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>-W</string><string>ignore</string><string>$ROOT/main.py</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/logs/run.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/run.log</string>
</dict></plist>
PL
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "설치 완료: 매일 09:30 실행 (로그: $ROOT/logs/run.log)"

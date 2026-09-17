#!/usr/bin/env bash
# Installs Gamerack for the current user only: a launcher in ~/.local/bin and a
# menu entry in ~/.local/share/applications. Nothing is written system-wide.
set -euo pipefail

SOURCE_DIR="$(dirname "$(readlink -f "$0")")"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"

mkdir -p "$BIN_DIR" "$APP_DIR"

cat > "${BIN_DIR}/gamerack" <<EOF
#!/usr/bin/env bash
exec python3 -m gamerack "\$@"
EOF
sed -i "2i cd \"${SOURCE_DIR}\"" "${BIN_DIR}/gamerack"
chmod +x "${BIN_DIR}/gamerack"

cat > "${APP_DIR}/io.github.tketchup.Gamerack.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Gamerack
Comment=Deine Spielebibliothek für Linux
Exec=${BIN_DIR}/gamerack
Icon=applications-games
Terminal=false
Categories=Game;
Keywords=Spiele;Games;Bibliothek;Library;Steam;Heroic;
StartupNotify=true
# Gamerack scans .desktop files; it must not list itself as a game.
NoDisplay=false
X-Gamerack-Self=true
EOF

update-desktop-database "$APP_DIR" 2>/dev/null || true

echo "Installiert."
echo "  Start:     gamerack   (oder über das Anwendungsmenü)"
echo "  Programm:  ${BIN_DIR}/gamerack"
echo "  Eintrag:   ${APP_DIR}/io.github.tketchup.Gamerack.desktop"
if ! echo ":$PATH:" | grep -q ":${BIN_DIR}:"; then
  echo
  echo "Hinweis: ${BIN_DIR} liegt nicht in deinem PATH."
fi

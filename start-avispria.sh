#!/bin/sh
# Starts Avispria and opens it in your web browser (Linux and macOS).
# Close this window, or press Ctrl+C, to stop it. Everything stays on this computer.
cd "$(dirname "$0")" || exit 1
if ! command -v uv >/dev/null 2>&1; then
  echo 'Avispria needs the program "uv" to run.'
  echo "Install it with:  curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "Then open a NEW terminal window and run this file again."
  exit 1
fi
echo "Starting Avispria... your browser will open in a moment."
exec uv run avispria ui

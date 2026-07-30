#!/bin/bash
# Build the VS Code extension .vsix package
set -euo pipefail

cd "$(dirname "$0")/../vscode-extension"

if ! command -v npx &> /dev/null; then
    echo "Error: npx not found. Install Node.js first."
    exit 1
fi

echo "Installing dependencies..."
npm install

echo "Compiling TypeScript..."
npx tsc -p tsconfig.json

echo "Packaging extension..."
npx @vscode/vsce package

echo "Done! .vsix file created in vscode-extension/"

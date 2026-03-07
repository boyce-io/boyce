# DataShark Client (VS Code Extension)

LSP client for DataShark. Activates on SQL files and launches the DataShark language server from `DataShark_Core`.

## Prerequisites

- **DataShark_Core** must be a sibling directory of this folder.
- **Python 3** with DataShark dependencies installed (`pip install -e ../DataShark_Core` or equivalent).
- **Node.js** and **npm** for building the extension.

## Setup

```bash
cd DataShark_Client
npm install
npm run compile
```

## Run from source

1. Open this repo in VS Code (or Cursor).
2. `F5` or Run > Start Debugging to launch a new window with the extension loaded.
3. Open a `.sql` file — the extension activates and the DataShark server starts with CWD set to `DataShark_Core`.
4. Hover over SQL files to see the DataShark context (model, schema, dependencies).

## Pack and install

```bash
npm install -g @vscode/vsce
vsce package
code --install-extension datashark-client-0.1.0.vsix
```

# DataShark Extension

This is the public wrapper for the DataShark Kernel.

## Overview

This VS Code extension provides the **Channel 2 (Public Harness)** distribution of DataShark. It bundles the Python kernel logic and manages its own isolated Python environment.

## Installation

Install via VS Code Extensions marketplace or by loading this directory as a development extension.

## Architecture

This extension:
- Bundles the Python logic from `datashark-mcp/src/datashark/` inside the extension folder
- Manages its own isolated Python venv
- Appears in the Extensions Sidebar with Logo and Version
- Is self-contained (batteries included)

## Development

The core logic lives in `datashark-mcp/src/datashark/core/` and `concepts/`. Changes to core logic must be verified to work with both:
- Channel 1 (Stealth): Local path via `install_stealth.py`
- Channel 2 (Public): Bundled path via this extension

See `project/03_DISTRIBUTION.md` for the full distribution strategy.

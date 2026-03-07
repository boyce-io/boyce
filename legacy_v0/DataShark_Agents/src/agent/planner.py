"""
Architect Planner: turn high-level goals into concrete file edits.

This module defines a MigrationPlanner that:
- Reads real file contents from disk
- Asks Anthropic (Claude) or OpenAI (GPT‑4o) to propose JSON edit actions
- Applies those edits safely via FileEditor
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from anthropic import Anthropic
from openai import OpenAI

from src.agent.editor import FileEditor, default_editor


MODEL = "claude-3-haiku-20240307"


class MigrationPlanner:
    """
    Planner that turns a high-level migration goal into executable file edits.
    """

    def __init__(
        self,
        client: Any,
        editor: FileEditor,
        model_provider: str = "anthropic",
    ) -> None:
        """
        Args:
            client: Anthropic or OpenAI client instance.
            editor: FileEditor bound to the workspace.
            model_provider: "anthropic" (default) or "openai".
        """
        self.client = client
        self.editor = editor
        self.provider = (model_provider or "anthropic").lower()
        # Assume editor.workspace_root is the repo root
        self._repo_root: Path = self.editor.workspace_root

    # ------------------------------------------------------------------ #
    # Planning
    # ------------------------------------------------------------------ #
    def generate_plan(self, goal: str, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Generate a structured JSON edit plan for the given goal and files.

        Args:
            goal: High-level migration / refactor goal.
            file_paths: List of repo-relative paths to consider.

        Returns:
            A list of action dicts like:
            [
              {
                "action": "UPDATE",
                "file": "path/to/file.sql",
                "search": "exact string to find",
                "replace": "new string"
              }
            ]
        """
        # Collect file contents
        file_blobs: List[str] = []
        for rel_path in file_paths:
            full_path = (self._repo_root / rel_path).resolve()
            try:
                content = full_path.read_text(encoding="utf-8")
                file_blobs.append(f"--- FILE: {rel_path} ---\n{content}\n")
            except FileNotFoundError:
                file_blobs.append(f"--- FILE: {rel_path} (MISSING) ---\n<missing file>\n")

        files_section = "\n\n".join(file_blobs) if file_blobs else "<no files provided>"

        # Shared prompts for both providers
        system_prompt = (
            "You are a Senior Data Architect. "
            "You design safe, minimal, and precise code edits. "
            "Output ONLY valid JSON in the specified format."
        )
        user_prompt = (
            "You will be given:\n"
            "1) A high-level migration or refactor goal.\n"
            "2) The current contents of one or more files.\n\n"
            "Your job is to propose a concrete edit plan as STRICT JSON only.\n"
            "Do NOT include any explanation, comments, or extra keys.\n"
            "The JSON MUST be a list of actions with this exact schema:\n"
            '[{\"action\": \"UPDATE\", \"file\": \"path/to/file.sql\", '
            '\"search\": \"exact string to find\", \"replace\": \"new string\"}]\n\n'
            "Rules:\n"
            "- Use only repo-relative paths exactly as provided.\n"
            "- 'search' MUST be an exact substring from the existing file content.\n"
            "- If you are unsure, prefer smaller, more local edits rather than huge blocks.\n"
            "- If no changes are required, return an empty list: []\n\n"
            f"GOAL:\n{goal}\n\n"
            "FILES:\n"
            f"{files_section}\n\n"
            "Now output ONLY the JSON list of actions. No prose."
        )

        if self.provider == "openai":
            # OpenAI GPT‑4o path
            if not isinstance(self.client, OpenAI):
                raise TypeError("OpenAI provider selected but client is not an OpenAI instance")
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2048,
            )
            try:
                raw_text = (response.choices[0].message.content or "").strip()
            except Exception:
                raw_text = ""
        else:
            # Anthropic Claude path
            if not isinstance(self.client, Anthropic):
                raise TypeError("Anthropic provider selected but client is not an Anthropic instance")
            claude_prompt = system_prompt + "\n\n" + user_prompt
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": claude_prompt}],
            )
            raw_text_parts: List[str] = []
            for block in getattr(response, "content", []) or []:
                if hasattr(block, "text"):
                    raw_text_parts.append(block.text)
            raw_text = "".join(raw_text_parts).strip()

        return self._parse_json_response(raw_text)

    def _parse_json_response(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Normalize and parse the LLM's JSON response.

        - Strips optional Markdown code fences ```json ... ``` or ``` ... ```
        - Attempts json.loads and enforces list-of-actions shape when possible.
        - Returns [] on any parse failure.
        """
        if not raw_text:
            return []

        text = raw_text.strip()

        # Handle Markdown fenced code blocks (```json ... ``` or ``` ... ```).
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1 :]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
            text = text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []

        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("plan"), list):
            return parsed["plan"]

        return []

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def execute_plan(self, plan: List[Dict[str, Any]]) -> List[str]:
        """
        Execute a JSON plan produced by `generate_plan`.

        For each UPDATE action, calls FileEditor.apply_patch and records
        a human-readable summary.
        """
        logs: List[str] = []
        for action in plan:
            action_type = action.get("action")
            target_file = action.get("file")
            search_block = action.get("search", "")
            replace_block = action.get("replace", "")

            if action_type != "UPDATE" or not target_file:
                logs.append(f"⚠️ Skipped unsupported action: {action}")
                continue

            ok = self.editor.apply_patch(target_file, search_block, replace_block)
            if ok:
                logs.append(f"✅ Updated {target_file}")
            else:
                logs.append(
                    f"❌ Failed to update {target_file} - block not found or ambiguous"
                )

        return logs


def main() -> None:
    """
    Simple test harness:
    - Defines a dummy goal
    - Asks provider for a plan against a few files
    - Prints the resulting JSON (does NOT execute by default)
    """
    editor = default_editor()
    # Default to Anthropic in this harness
    api_key = None
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set; skipping planner.main harness.")
        return

    client = Anthropic(api_key=api_key)
    planner = MigrationPlanner(client=client, editor=editor, model_provider="anthropic")

    goal = "Standardize references to a staging model and ensure comments are consistent."
    example_files = ["scenarios/dummy_fix.sql"]

    print("🧠 Generating migration plan (Anthropic harness)...")
    plan = planner.generate_plan(goal, example_files)
    print("\n--- Proposed Plan (JSON) ---")
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()


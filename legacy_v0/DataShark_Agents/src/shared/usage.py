"""
Telemetry: usage tracking and cost calculation for model requests.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

# Cost per million tokens: (input $/M, output $/M)
PRICING: dict[str, tuple[float, float]] = {
    # OLD: "claude-3-5-sonnet-20241022": (3.00, 15.00),
    # NEW (Jan 2026 Standard):
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
}

USAGE_LOG_PATH = Path("data/usage_log.csv")
CSV_HEADERS = ("Timestamp", "Model", "Input Tokens", "Output Tokens", "Cost ($)")


class UsageTracker:
    """Tracks model usage and cost; appends to data/usage_log.csv."""

    def __init__(self, log_path: Path | str | None = None):
        self._log_path = Path(log_path) if log_path else USAGE_LOG_PATH
        self._session_cost: float = 0.0

    def log_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Compute cost from PRICING, append a row to the CSV, update session cost.
        Returns cost in dollars.
        """
        pricing = PRICING.get(model)
        if pricing is None:
            input_per_m, output_per_m = 0.0, 0.0
        else:
            input_per_m, output_per_m = pricing

        cost = (input_tokens * input_per_m / 1_000_000) + (
            output_tokens * output_per_m / 1_000_000
        )
        self._session_cost += cost

        log_dir = self._log_path.parent
        log_dir.mkdir(parents=True, exist_ok=True)

        row = (
            datetime.utcnow().isoformat() + "Z",
            model,
            str(input_tokens),
            str(output_tokens),
            f"{cost:.6f}",
        )

        file_exists = self._log_path.exists()
        with open(self._log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(CSV_HEADERS)
            writer.writerow(row)

        return cost

    def print_summary(self) -> None:
        """
        Read the CSV (if present), then print Session Cost and Total Project Cost.
        Handles missing or empty CSV gracefully.
        """
        total_project = 0.0
        if self._log_path.exists():
            try:
                with open(self._log_path, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames != list(CSV_HEADERS):
                        pass  # wrong format, treat as no data
                    else:
                        for row in reader:
                            try:
                                total_project += float(row["Cost ($)"])
                            except (KeyError, ValueError):
                                pass
            except (OSError, csv.Error):
                pass

        print("Session Cost:     ${:.4f}".format(self._session_cost))
        print("Total Project Cost: ${:.4f}".format(total_project))

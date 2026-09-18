from pathlib import Path
import pandas as pd

REQUIRED = [
    "ticket_id", "created_at", "category", "priority", "status",
    "response_time_hrs", "resolution_time_hrs", "agent_id",
    "customer_rating", "issue_summary"
]

# The brief's schema preview abbreviates some headers visually; the canonical
# column names below follow its Column Descriptions section.
def load_tickets(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found: {path}. Place the assessment's support_tickets.csv at {path}."
        )
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    df = df.copy()
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    for c in ["response_time_hrs", "resolution_time_hrs", "customer_rating"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df["created_at"].isna().any():
        raise ValueError("created_at contains invalid datetime values")
    return df

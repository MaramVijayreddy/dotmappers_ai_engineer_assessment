import pandas as pd
from app.models.schemas import TimeRange

class AnomalyService:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.anchor = self.df.created_at.max()

    def detect(self, iqr_multiplier=1.5, unresolved_age_hours=24.0, time_range: TimeRange | None = None):
        df = self._apply_time_range(self.df.copy(), time_range or TimeRange())
        resolved = df["resolution_time_hrs"].dropna()
        if len(resolved) >= 4:
            q1, q3 = resolved.quantile([0.25, 0.75])
            upper = q3 + iqr_multiplier * (q3 - q1)
        else:
            upper = resolved.max() if len(resolved) else float("inf")

        long = df[df["resolution_time_hrs"] > upper].copy()
        long["anomaly_type"] = "abnormally_long_resolution_time"
        long["threshold_hours"] = round(float(upper), 2) if upper != float("inf") else None

        age_hours = (self.anchor - df["created_at"]).dt.total_seconds() / 3600
        high_unresolved = df[
            df["priority"].isin(["High", "Critical"])
            & df["status"].ne("Resolved")
            & (age_hours > unresolved_age_hours)
        ].copy()
        high_unresolved["anomaly_type"] = "unresolved_high_priority_over_threshold"
        high_unresolved["threshold_hours"] = unresolved_age_hours

        cols = ["ticket_id","created_at","category","priority","status","response_time_hrs",
                "resolution_time_hrs","agent_id","customer_rating","issue_summary",
                "anomaly_type","threshold_hours"]
        combined = pd.concat([long, high_unresolved], ignore_index=True)
        if not combined.empty:
            combined = combined.drop_duplicates(subset=["ticket_id", "anomaly_type"])
            combined["created_at"] = combined["created_at"].astype(str)

        return {
            "anchor_timestamp": self.anchor.isoformat(),
            "time_range": time_range.model_dump() if time_range else {"kind":"none","start":None,"end":None},
            "long_resolution_threshold_hours": round(float(upper), 2) if upper != float("inf") else None,
            "anomaly_count": int(len(combined)),
            "anomalies": combined[cols].astype(object).where(pd.notna(combined[cols]), None).to_dict(orient="records") if not combined.empty else [],
        }

    def _apply_time_range(self, df, tr):
        if tr.kind in {"last_7_days", "this_week"}:
            return df[df.created_at >= self.anchor - pd.Timedelta(days=7)]
        if tr.kind == "last_30_days":
            return df[df.created_at >= self.anchor - pd.Timedelta(days=30)]
        if tr.kind == "this_month":
            return df[df.created_at.dt.to_period("M") == self.anchor.to_period("M")]
        if tr.kind == "after_date": return df[df.created_at >= pd.Timestamp(tr.start)]
        if tr.kind == "before_date": return df[df.created_at <= pd.Timestamp(tr.end)]
        if tr.kind == "between_dates": return df[(df.created_at >= pd.Timestamp(tr.start)) & (df.created_at <= pd.Timestamp(tr.end))]
        return df

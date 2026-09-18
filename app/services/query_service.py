from datetime import timedelta

import pandas as pd

from app.models.schemas import QueryIntent


ALLOWED_COLUMNS = {
    "ticket_id",
    "created_at",
    "category",
    "priority",
    "status",
    "response_time_hrs",
    "resolution_time_hrs",
    "agent_id",
    "customer_rating",
    "issue_summary",
}

NUMERIC_FIELDS = {
    "response_time_hrs",
    "resolution_time_hrs",
    "customer_rating",
}


class QueryService:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.anchor = self.df["created_at"].max()

    def execute(self, intent: QueryIntent):
        if intent.operation == "anomaly":
            raise ValueError(
                "Anomaly queries are served by the /anomalies endpoint"
            )

        df = self._apply_filters(self.df, intent)

        op = intent.operation
        metric = intent.metric

        # -----------------------------------------
        # Validate metric requirements
        # -----------------------------------------
        if op in {
            "average",
            "sum",
            "min",
            "max",
            "group_metric",
        } and not metric:
            raise ValueError(f"{op} requires a metric")

        # -----------------------------------------
        # COUNT
        # -----------------------------------------
        if op == "count":
            value = int(len(df))

            return (
                [{"count": value}],
                f"There are {value} matching tickets.",
            )

        # -----------------------------------------
        # AVERAGE
        # -----------------------------------------
        if op == "average":
            v = df[metric].mean()

            return (
                [
                    {
                        "average": (
                            None
                            if pd.isna(v)
                            else round(float(v), 2)
                        )
                    }
                ],
                self._scalar_answer(
                    "average",
                    metric,
                    v,
                ),
            )

        # -----------------------------------------
        # SUM / MIN / MAX
        # -----------------------------------------
        if op in {"sum", "min", "max"}:
            series = df[metric].dropna()

            v = (
                getattr(series, op)()
                if len(series)
                else None
            )

            return (
                [
                    {
                        op: (
                            None
                            if v is None
                            else round(float(v), 2)
                        )
                    }
                ],
                self._scalar_answer(
                    op,
                    metric,
                    v,
                ),
            )

        # -----------------------------------------
        # LIST
        # -----------------------------------------
        if op == "list":
            cols = (
                [
                    c
                    for c in intent.include_columns
                    if c in ALLOWED_COLUMNS
                ]
                or [
                    "ticket_id",
                    "created_at",
                    "category",
                    "priority",
                    "status",
                    "response_time_hrs",
                    "resolution_time_hrs",
                    "agent_id",
                    "customer_rating",
                    "issue_summary",
                ]
            )

            out = (
                df.sort_values(
                    "created_at",
                    ascending=False,
                )
                .head(intent.limit)
            )

            records = self._records(out[cols])

            return (
                records,
                self._list_answer(
                    intent,
                    len(df),
                ),
            )

        # -----------------------------------------
        # GROUP COUNT
        # -----------------------------------------
        if op == "group_count":
            if not intent.group_by:
                raise ValueError(
                    "group_count requires group_by"
                )

            g = (
                df.groupby(
                    intent.group_by,
                    dropna=False,
                )
                .size()
                .reset_index(name="count")
            )

            g = g.sort_values(
                "count",
                ascending=(
                    intent.order_by == "asc"
                ),
            )

            records = self._records(
                g.head(intent.limit)
            )

            return (
                records,
                self._group_count_answer(
                    intent,
                    records,
                ),
            )

        # -----------------------------------------
        # GROUP METRIC
        # -----------------------------------------
        if op == "group_metric":
            if not intent.group_by or not metric:
                raise ValueError(
                    "group_metric requires "
                    "group_by and metric"
                )

            value_column = f"average_{metric}"

            g = (
                df.groupby(
                    intent.group_by,
                    dropna=False,
                )[metric]
                .mean()
                .reset_index(
                    name=value_column
                )
            )

            g = g.dropna(
                subset=[value_column]
            )

            g = g.sort_values(
                value_column,
                ascending=(
                    intent.order_by == "asc"
                ),
            )

            records = self._records(
                g.head(intent.limit)
            )

            return (
                records,
                self._group_metric_answer(
                    intent,
                    records,
                    metric,
                ),
            )

        raise ValueError(
            f"Unsupported operation: {op}"
        )

    # ==================================================
    # FILTERING
    # ==================================================

    def _apply_filters(
        self,
        df: pd.DataFrame,
        intent: QueryIntent,
    ):
        out = df.copy()

        # -----------------------------------------
        # filters = AND
        # -----------------------------------------
        out = self._filter_all(
            out,
            intent.filters,
        )

        # -----------------------------------------
        # any_filters = OR
        # -----------------------------------------
        if intent.any_filters:
            masks = [
                self._filter_mask(
                    out,
                    f,
                )
                for f in intent.any_filters
            ]

            if masks:
                combined = masks[0]

                for mask in masks[1:]:
                    combined = combined | mask

                out = out[combined]

        # -----------------------------------------
        # Time range
        # -----------------------------------------
        tr = intent.time_range

        if tr.kind in {
            "last_7_days",
            "this_week",
        }:
            out = out[
                out.created_at
                >= self.anchor - timedelta(days=7)
            ]

        elif tr.kind == "last_30_days":
            out = out[
                out.created_at
                >= self.anchor - timedelta(days=30)
            ]

        elif tr.kind == "this_month":
            out = out[
                out.created_at.dt.to_period("M")
                == self.anchor.to_period("M")
            ]

        elif tr.kind == "after_date":
            out = out[
                out.created_at
                >= pd.Timestamp(tr.start)
            ]

        elif tr.kind == "before_date":
            out = out[
                out.created_at
                <= pd.Timestamp(tr.end)
            ]

        elif tr.kind == "between_dates":
            out = out[
                (
                    out.created_at
                    >= pd.Timestamp(tr.start)
                )
                & (
                    out.created_at
                    <= pd.Timestamp(tr.end)
                )
            ]

        return out

    def _filter_all(
        self,
        df: pd.DataFrame,
        filters,
    ):
        out = df

        for f in filters:
            out = out[
                self._filter_mask(
                    out,
                    f,
                )
            ]

        return out

    def _filter_mask(
        self,
        df: pd.DataFrame,
        f,
    ):
        if f.field not in ALLOWED_COLUMNS:
            raise ValueError(
                "Unsafe filter field"
            )

        series = df[f.field]

        vals = (
            f.value
            if isinstance(f.value, list)
            else [f.value]
        )

        # -----------------------------------------
        # String / equality filters
        # -----------------------------------------
        if f.operator in {
            "eq",
            "neq",
            "in",
        }:
            lhs = (
                series
                .astype(str)
                .str.lower()
            )

            rhs = [
                str(v).lower()
                for v in vals
            ]

            if f.operator == "eq":
                return lhs == rhs[0]

            if f.operator == "neq":
                return lhs != rhs[0]

            return lhs.isin(rhs)

        # -----------------------------------------
        # Text search
        # -----------------------------------------
        if f.operator == "contains":
            return series.astype(str).str.contains(
                str(vals[0]),
                case=False,
                na=False,
                regex=False,
            )

        # -----------------------------------------
        # Numeric comparisons
        # -----------------------------------------
        if f.field not in NUMERIC_FIELDS:
            raise ValueError(
                f"Operator {f.operator} "
                f"is only valid for numeric fields"
            )

        numeric = pd.to_numeric(
            series,
            errors="coerce",
        )

        value = float(vals[0])

        if f.operator == "gt":
            return numeric > value

        if f.operator == "gte":
            return numeric >= value

        if f.operator == "lt":
            return numeric < value

        if f.operator == "lte":
            return numeric <= value

        raise ValueError(
            f"Unsupported filter operator: "
            f"{f.operator}"
        )

    # ==================================================
    # RESPONSE FORMATTING
    # ==================================================

    @staticmethod
    def _records(df):
        records = df.copy()

        if "created_at" in records:
            records["created_at"] = (
                records["created_at"]
                .astype(str)
            )

        return (
            records.astype(object)
            .where(
                pd.notna(records),
                None,
            )
            .to_dict(
                orient="records"
            )
        )

    @staticmethod
    def _scalar_answer(
        op,
        metric,
        value,
    ):
        name = metric.replace(
            "_",
            " ",
        )

        if value is None or pd.isna(value):
            return (
                f"No non-null {name} "
                f"values were found."
            )

        if op == "average":
            return (
                f"The average {name} "
                f"is {float(value):.2f}."
            )

        return (
            f"The {op} {name} "
            f"is {float(value):.2f}."
        )

    @staticmethod
    def _list_answer(
        intent,
        count,
    ):
        if count == 0:
            return "No matching tickets were found."

        if count <= intent.limit:
            return (
                f"Found {count} matching "
                f"tickets."
            )

        return (
            f"Found {count} matching tickets; "
            f"showing the latest {intent.limit}."
        )

    @staticmethod
    def _group_count_answer(
        intent,
        records,
    ):
        if not records:
            return (
                "No matching tickets were "
                "found for the requested grouping."
            )

        group_by = intent.group_by

        # -----------------------------------------
        # Human-readable group name
        # -----------------------------------------
        group_name = group_by.replace(
            "_",
            " ",
        )

        # -----------------------------------------
        # Detect resolved-ticket query
        # -----------------------------------------
        resolved_filter = any(
            f.field == "status"
            and f.operator == "eq"
            and str(f.value).lower()
            == "resolved"
            for f in intent.filters
        )

        # -----------------------------------------
        # Time description
        # -----------------------------------------
        time_description = ""

        if intent.time_range.kind == "this_month":
            time_description = " this month"

        elif intent.time_range.kind == "this_week":
            time_description = " this week"

        elif intent.time_range.kind == "last_7_days":
            time_description = (
                " in the last 7 days"
            )

        elif intent.time_range.kind == "last_30_days":
            time_description = (
                " in the last 30 days"
            )

        # -----------------------------------------
        # Most
        # -----------------------------------------
        if intent.order_by == "desc":

            top_count = records[0]["count"]

            top_groups = [
                str(row[group_by])
                for row in records
                if row["count"]
                == top_count
            ]

            if len(top_groups) == 1:

                group_value = top_groups[0]

                if (
                    resolved_filter
                    and group_by == "agent_id"
                ):
                    answer = (
                        f"{group_value} resolved "
                        f"the most tickets"
                        f"{time_description}, "
                        f"with {top_count} "
                        f"resolved tickets."
                    )
                else:
                    answer = (
                        f"{group_value} has the "
                        f"most tickets"
                        f"{time_description}, "
                        f"with {top_count} tickets."
                    )

            else:

                if resolved_filter:
                    answer = (
                        f"The most resolved "
                        f"tickets{time_description} "
                        f"were {top_count}, "
                        f"shared by "
                        f"{', '.join(top_groups)}."
                    )
                else:
                    answer = (
                        f"The highest ticket "
                        f"count{time_description} "
                        f"is {top_count}, "
                        f"shared by "
                        f"{', '.join(top_groups)}."
                    )

        # -----------------------------------------
        # Least
        # -----------------------------------------
        else:

            lowest_count = records[0]["count"]

            lowest_groups = [
                str(row[group_by])
                for row in records
                if row["count"]
                == lowest_count
            ]

            if len(lowest_groups) == 1:

                group_value = lowest_groups[0]

                if (
                    resolved_filter
                    and group_by == "agent_id"
                ):
                    answer = (
                        f"{group_value} resolved "
                        f"the fewest tickets"
                        f"{time_description}, "
                        f"with {lowest_count} "
                        f"resolved tickets."
                    )
                else:
                    answer = (
                        f"{group_value} has the "
                        f"fewest tickets"
                        f"{time_description}, "
                        f"with {lowest_count} tickets."
                    )

            else:

                if resolved_filter:
                    answer = (
                        f"The fewest resolved "
                        f"tickets{time_description} "
                        f"were {lowest_count}, "
                        f"shared by "
                        f"{', '.join(lowest_groups)}."
                    )
                else:
                    answer = (
                        f"The lowest ticket "
                        f"count{time_description} "
                        f"is {lowest_count}, "
                        f"shared by "
                        f"{', '.join(lowest_groups)}."
                    )

        return answer

    @staticmethod
    def _group_metric_answer(
        intent,
        records,
        metric,
    ):
        if not records:
            return (
                f"No non-null "
                f"{metric.replace('_', ' ')} "
                f"values were found for "
                f"the requested groups."
            )

        group = intent.group_by.replace(
            "_",
            " ",
        )

        value_key = (
            f"average_{metric}"
        )

        first = records[0]

        direction = (
            "lowest"
            if intent.order_by == "asc"
            else "highest"
        )

        return (
            f"The {direction} average "
            f"{metric.replace('_', ' ')} "
            f"is for {group} "
            f"{first[intent.group_by]}, "
            f"at "
            f"{float(first[value_key]):.2f}."
        )
        
from typing import Literal, Optional, List, Union
from pydantic import BaseModel, Field

Operation = Literal[
    "count", "average", "sum", "min", "max", "list",
    "group_count", "group_metric", "anomaly"
]
Metric = Literal["response_time_hrs", "resolution_time_hrs", "customer_rating"]
GroupField = Literal["category", "priority", "status", "agent_id"]
FilterField = Literal[
    "category", "priority", "status", "agent_id", "ticket_id", "issue_summary",
    "response_time_hrs", "resolution_time_hrs", "customer_rating"
]
FilterOperator = Literal["eq", "neq", "in", "contains", "gt", "gte", "lt", "lte"]

class Filter(BaseModel):
    field: FilterField
    operator: FilterOperator = "eq"
    value: Union[str, float, int, List[Union[str, float, int]]]

class TimeRange(BaseModel):
    kind: Literal[
        "none", "last_7_days", "last_30_days", "this_week", "this_month",
        "after_date", "before_date", "between_dates"
    ] = "none"
    start: Optional[str] = None
    end: Optional[str] = None

class QueryIntent(BaseModel):
    operation: Operation
    metric: Optional[Metric] = None
    group_by: Optional[GroupField] = None
    filters: List[Filter] = Field(default_factory=list)
    any_filters: List[Filter] = Field(default_factory=list)
    time_range: TimeRange = Field(default_factory=TimeRange)
    order_by: Optional[Literal["asc", "desc"]] = None
    limit: int = Field(default=20, ge=1, le=100)
    include_columns: List[str] = Field(default_factory=list)

class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)

class QueryResponse(BaseModel):
    question: str
    intent: QueryIntent
    answer: str
    data: list[dict]

class AnomalyRequest(BaseModel):
    resolution_iqr_multiplier: float = Field(default=1.5, ge=0.5, le=5.0)
    unresolved_age_hours: float = Field(default=24.0, ge=1, le=720)
    time_range: TimeRange = Field(default_factory=TimeRange)

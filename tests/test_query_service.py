import pandas as pd
from app.services.query_service import QueryService
from app.models.schemas import QueryIntent, Filter

def sample_df():
    return pd.DataFrame({
        "ticket_id":["T1","T2","T3"],
        "created_at":pd.to_datetime(["2024-01-01","2024-01-02","2024-01-03"]),
        "category":["Billing","Technical","Technical"],
        "priority":["High","Critical","Low"],
        "status":["Resolved","Open","Resolved"],
        "response_time_hrs":[1,2,3],
        "resolution_time_hrs":[2,20,4],
        "agent_id":["A","B","B"],
        "customer_rating":[4, None, 5],
        "issue_summary":["x","y","z"],
    })

def test_count():
    data, _ = QueryService(sample_df()).execute(QueryIntent(operation="count"))
    assert data[0]["count"] == 3

def test_critical():
    intent = QueryIntent(operation="count", filters=[Filter(field="priority", value="Critical")])
    data, _ = QueryService(sample_df()).execute(intent)
    assert data[0]["count"] == 1

def test_numeric_filter():
    intent = QueryIntent(operation="list", filters=[Filter(field="resolution_time_hrs", operator="gt", value=10)])
    data, _ = QueryService(sample_df()).execute(intent)
    assert [x["ticket_id"] for x in data] == ["T2"]

def test_group_metric():
    intent = QueryIntent(operation="group_metric", group_by="agent_id", metric="customer_rating", order_by="asc")
    data, answer = QueryService(sample_df()).execute(intent)
    assert data[0]["agent_id"] == "A"
    assert "lowest" in answer

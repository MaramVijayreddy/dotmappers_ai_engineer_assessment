from fastapi import APIRouter, HTTPException
from app.models.schemas import QueryRequest, QueryResponse, AnomalyRequest

router = APIRouter()

class AppState:
    df = None
    query_service = None
    anomaly_service = None
    llm = None
    startup_error = None

state = AppState()

@router.get("/health")
def health():
    if state.df is None:
        return {"status":"degraded","dataset_loaded":False,"error":state.startup_error}
    return {"status":"ok","dataset_loaded":True,"rows":len(state.df),"llm_provider": getattr(state.llm, "provider", None)}

@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if state.df is None: raise HTTPException(503, "Dataset is not loaded")
    try:
        intent = state.llm.plan(req.question)
        if intent.operation == "anomaly":
            result = state.anomaly_service.detect(time_range=intent.time_range)
            return {"question":req.question,"intent":intent,"answer":f"Detected {result['anomaly_count']} anomalies.","data":result["anomalies"]}
        data, answer = state.query_service.execute(intent)
        return {"question":req.question,"intent":intent,"answer":answer,"data":data}
    except Exception as e:
        raise HTTPException(400, f"Could not process query: {e}")

@router.post("/anomalies")
def anomalies(req: AnomalyRequest):
    if state.df is None: raise HTTPException(503, "Dataset is not loaded")
    try:
        return state.anomaly_service.detect(req.resolution_iqr_multiplier, req.unresolved_age_hours, req.time_range)
    except Exception as e:
        raise HTTPException(400, str(e))

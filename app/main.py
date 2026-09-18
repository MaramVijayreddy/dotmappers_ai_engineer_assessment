import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv
from app.data.loader import load_tickets
from app.api.routes import router, state
from app.services.query_service import QueryService
from app.services.anomaly_service import AnomalyService
from app.services.llm_service import LLMService

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    path = os.getenv("DATA_PATH", "data/support_tickets.csv")
    try:
        state.df = load_tickets(path)
        state.query_service = QueryService(state.df)
        state.anomaly_service = AnomalyService(state.df)
        state.llm = LLMService()
        state.startup_error = None
    except Exception as e:
        state.df = None
        state.startup_error = str(e)
    yield

app = FastAPI(title="DOTMappers AI Support Ticket Analytics", version="1.0.0", lifespan=lifespan)
app.include_router(router)

@app.get("/")
def root():
    return {"service":"DOTMappers AI Support Ticket Analytics","docs":"/docs","health":"/health"}

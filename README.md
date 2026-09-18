# DOTMappers IT Pvt. Ltd. — AI Engineer Assessment

End-to-end AI-powered customer-support ticket analytics system built for the supplied **AI Engineer Technical Assessment — End-to-End AI System Sprint**.

## 1. Assessment alignment

The supplied brief asks for a Python system that:

1. Ingests the supplied `support_tickets.csv` and makes it queryable.
2. Answers natural-language questions about the data.
3. Detects and flags anomalies, including abnormally long resolution times and unresolved high-priority tickets older than 24 hours.
4. Exposes the functionality through a REST API **and** a minimal UI.

The brief also requires an LLM for natural-language understanding, permits Ollama/Groq/Hugging Face/local models, prohibits paid APIs/services, requires zero-cost evaluation, and asks for a single-command application startup. See the supplied assessment brief for the authoritative requirements.

## 2. Architecture

```text
                         User
                           |
                +----------+----------+
                |                     |
           Streamlit UI          FastAPI API
                |                     |
                +----------+----------+
                           |
                    Query Controller
                           |
                      LLM Service
                    /              \
               Ollama          HuggingFace/Groq
                  |                  |
                  +--------+---------+
                           |
                    QueryIntent JSON
                           |
                    Pydantic validation
                           |
                    Deterministic Pandas
                           |
                    support_tickets.csv
                           |
                 +---------+----------+
                 |                    |
             Query result       Anomaly engine
```

### Core design decision

The LLM is a **query planner**, not the calculator and not an arbitrary code generator.

```text
Natural-language question
          |
          v
         LLM
          |
          v
  Structured QueryIntent
          |
          v
 Pydantic validation
          |
          v
 Deterministic Pandas
          |
          v
 Actual answer from CSV
```

The LLM never receives permission to execute SQL/Python. The application only executes allow-listed operations, fields, and operators.

## 3. Repository structure

```text
DOTMappers-AI-Engineer-Assessment/
├── app/
│   ├── api/routes.py
│   ├── data/loader.py
│   ├── models/schemas.py
│   ├── services/
│   │   ├── anomaly_service.py
│   │   ├── llm_service.py
│   │   └── query_service.py
│   └── main.py
├── data/
│   └── support_tickets.csv
├── tests/
│   └── test_query_service.py
├── ui/
│   └── streamlit_app.py
├── .env.example
├── requirements.txt
├── run.py
├── ARCHITECTURE_WALKTHROUGH.md
└── README.md
```

## 4. Dataset

The supplied assessment dataset is included as `data/support_tickets.csv`. The brief specifies 500 rows and these 10 columns:

| Column | Meaning |
|---|---|
| `ticket_id` | Unique ticket identifier |
| `created_at` | Ticket creation timestamp |
| `category` | Billing / Technical / General |
| `priority` | Low / Medium / High / Critical |
| `status` | Open / Resolved / Escalated |
| `response_time_hrs` | Hours from creation to first agent response |
| `resolution_time_hrs` | Hours from creation to resolution; null when unresolved |
| `agent_id` | Assigned support agent identifier |
| `customer_rating` | 1–5 post-resolution rating; null when unresolved |
| `issue_summary` | Brief issue description |

The loader validates the schema and converts datetime/numeric fields before analytics.

## 5. LLM provider strategy

The code supports **Ollama, Groq, and Hugging Face** through the same `LLMService` interface.

### Recommended assessment configuration: Ollama

Ollama is the simplest provider when the evaluator wants a fully local, zero-cost run:

- no API key
- no paid service
- ticket data stays on the evaluator's machine
- the same downloaded model can be reused across runs

One-time prerequisite:

```bash
ollama pull llama3.2:3b
```

Then configure:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

### Alternative: Hugging Face

If the evaluator prefers an API-based run, configure an available Hugging Face Inference API token:

```env
LLM_PROVIDER=huggingface
HF_TOKEN=your_token
HF_MODEL=Qwen/Qwen2.5-7B-Instruct
```

### Alternative: Groq

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_key
GROQ_MODEL=llama-3.1-8b-instant
```

### Automatic selection

With:

```env
LLM_PROVIDER=auto
```

the application selects Groq when `GROQ_API_KEY` is present, otherwise Hugging Face when `HF_TOKEN` is present, otherwise Ollama.

**Important:** an evaluator must configure at least one permitted LLM provider. There is no fake/mock answer path because the assessment explicitly requires an LLM for natural-language query handling.

## 6. Setup for an evaluator

### Step 1 — Clone the repository

```bash
git clone <repository-url>
cd <repository-folder>
```

### Step 2 — Install Python dependencies

Python 3.11+ is recommended.

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Step 3 — Configure one LLM provider

For the recommended local path, install Ollama separately and download the small instruction-following model:

```bash
ollama pull llama3.2:3b
```

Keep the Ollama settings in `.env`.

### Step 4 — Start the application

After the one-time setup, the application itself starts with one command:

```bash
python run.py
```

The launcher starts both required interfaces:

- FastAPI: `http://localhost:8000`
- Swagger/OpenAPI: `http://localhost:8000/docs`
- Streamlit UI: `http://localhost:8501`

## 7. REST API

### Health check

```http
GET /health
```

Returns dataset availability and row count without calling the LLM.

### Natural-language query

```http
POST /query
Content-Type: application/json

{"question":"How many tickets are currently open?"}
```

The response contains:

- original question
- validated LLM intent
- grounded answer
- structured result data

### Anomaly detection

```http
POST /anomalies
Content-Type: application/json

{}
```

Optional parameters control the resolution-time IQR multiplier, unresolved-age threshold, and deterministic dataset time range.

## 8. Natural-language query capabilities

Supported intent operations:

- `count`
- `average`
- `sum`
- `min`
- `max`
- `list`
- `group_count`
- `group_metric`
- `anomaly`

Supported filters include:

- category, priority, status, agent, ticket ID
- issue-summary text matching
- numeric comparisons for response time, resolution time, and rating
- date windows such as latest 7 days, latest 30 days, latest calendar month, and explicit dates

The LLM maps language into the structured intent. Pandas performs the actual operation.

## 9. Anomaly detection

### A. Abnormally long resolution time

For resolved tickets:

```text
upper_fence = Q3 + multiplier × IQR
IQR = Q3 - Q1
```

Tickets above the upper fence are flagged.

### B. Unresolved high-priority tickets older than 24 hours

```text
priority in {High, Critical}
AND status != Resolved
AND ticket age > 24 hours
```

Because the CSV does not contain a separate observation timestamp, ticket age uses the dataset's latest `created_at` as a deterministic reference point. This avoids results changing according to the evaluator's wall-clock time.

## 10. Sample assessment queries

The supplied brief lists examples such as:

```text
How many tickets are currently open?
Which agent resolved the most tickets this month?
Show me all Critical tickets not resolved within 12 hours.
What is the average customer rating for Technical category tickets?
Are there any anomalies in resolution times this week?
```

The evaluator is expected to use their own queries during the walkthrough, so the implementation is not hard-coded to those examples.

## 11. Error handling and safety

- Required CSV columns are validated at startup.
- Datetimes and numeric fields are coerced and checked.
- API input is validated with Pydantic.
- LLM output must parse as JSON and satisfy the `QueryIntent` schema.
- Only allow-listed fields/operators can be executed.
- Numeric operators are restricted to numeric fields.
- `contains` uses non-regex matching.
- Invalid LLM output becomes an explicit error rather than a fabricated result.

## 12. Testing

Run:

```bash
pytest -q
```

The included tests cover basic counting, categorical filtering, numeric filtering, and grouped metrics.

## 13. Known limitations

1. Pandas is appropriate for the supplied 500-row assessment dataset; production-scale data should move to a database/warehouse.
2. Natural-language intent accuracy depends on the selected LLM.
3. Dataset-relative time anchoring is used because the CSV has no observation timestamp.
4. Authentication, rate limiting, structured logging, tracing, and deployment configuration are outside this prototype.
5. Semantic search over `issue_summary` could be extended with embeddings/vector search.

## 14. Walkthrough

See `ARCHITECTURE_WALKTHROUGH.md` for the demo flow, design reasoning, trade-offs, scaling discussion, and likely evaluator questions.

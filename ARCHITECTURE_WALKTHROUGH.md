# DOTMappers AI Engineer Assessment — 30-Minute Walkthrough

## 1. Opening — 2 minutes

> "I built an end-to-end AI support-ticket analytics system. It ingests the supplied 500-row CSV, uses an LLM for natural-language understanding, validates a structured query intent, performs deterministic analytics against the CSV, detects anomalies, and exposes the same functionality through FastAPI and a Streamlit UI."

## 2. Live demo — 8 minutes

Start:

```bash
python run.py
```

Show:

1. `GET /health` in Swagger.
2. Streamlit UI.
3. `How many tickets are currently open?`
4. `What is the average customer rating for Technical category tickets?`
5. `Which agent resolved the most tickets this month?`
6. `Are there any anomalies in resolution times this week?`
7. A custom evaluator-style question.
8. The structured intent returned with the answer.

Explain that the UI calls the API and the API is the source of truth.

## 3. Architecture — 7 minutes

```text
User
 |
 +--> Streamlit UI
 |
 +--> FastAPI /query
          |
          v
     LLM Service
          |
          v
    QueryIntent JSON
          |
          v
   Pydantic validation
          |
          v
     QueryService
          |
          v
     Pandas / CSV
          |
          v
   Grounded response
```

### Why this architecture?

- The supplied dataset is only 500 rows, so Pandas is sufficient for the assessment.
- The LLM is used where language understanding is valuable.
- Structured output creates a contract between the LLM and application code.
- Deterministic execution prevents the LLM from inventing numerical results.
- FastAPI separates transport from business logic.
- Streamlit satisfies the minimal UI requirement.
- The LLM provider is isolated in one service, allowing Ollama, Groq, or Hugging Face without rewriting query logic.

## 4. LLM integration — 4 minutes

The system prompt tells the model to return only a `QueryIntent`; it must not answer the question or generate executable SQL/Python.

Example:

```text
User:
Which agent has the lowest average customer rating?

LLM intent:
operation = group_metric
metric = customer_rating
group_by = agent_id
order_by = asc
```

The application then calculates the averages itself.

The trust boundary is:

```text
LLM = interpretation
Application = execution
CSV = source of truth
```

### Provider choice

For a zero-cost local evaluation, Ollama is the recommended path. The project also keeps cloud-provider adapters for Hugging Face and Groq. This avoids coupling the business logic to one provider.

## 5. Anomaly detection — 3 minutes

Two deterministic rules are implemented:

### Long resolution time

```text
upper_fence = Q3 + multiplier × IQR
```

### Old unresolved high-priority tickets

```text
High/Critical
AND status != Resolved
AND age > 24 hours
```

The age reference is the dataset's latest timestamp so the result is reproducible.

## 6. Likely evaluator questions

### Why not let the LLM generate SQL?

Because unrestricted generated SQL increases safety and reliability risk. The requirement is LLM-based natural-language understanding, so a structured intent is a smaller and safer interface.

### What happens if the LLM returns invalid JSON?

The parser attempts to extract JSON and Pydantic validates the final object. Invalid output becomes an explicit error rather than an invented answer.

### How do you handle prompt injection?

The model has no direct execution privileges. Its output is constrained by a Pydantic schema, and the executor uses allow-listed fields and operations.

### Why not use the LLM for anomaly detection?

Anomaly thresholds should be reproducible and testable. The LLM interprets the request; deterministic statistical/business rules make the anomaly decision.

### How would you scale to 10 million rows?

Move analytics to a database/warehouse. Keep the intent layer, then map validated intents to parameterized SQL or a query-builder layer. Add indexes, caching, pagination, logging, tracing, and access control.

### What would you improve with more time?

- database-backed analytics
- stronger LLM intent evaluation set
- richer semantic search over `issue_summary`
- authentication/rate limiting
- structured logging/tracing
- more integration tests
- containerized deployment

## 7. Closing — 1 minute

> "The main design principle is that the LLM understands the user's language, while deterministic application code performs the actual computation. That separation makes the prototype easier to test, safer to operate, and straightforward to scale."

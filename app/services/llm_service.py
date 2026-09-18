import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from app.models.schemas import QueryIntent


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# PROMPT
# ============================================================

PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "query_planner_prompt.txt"
)

SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


# ============================================================
# LLM SERVICE
# ============================================================

class LLMService:
    """
    Converts a user's natural-language question into a
    validated QueryIntent.

    Architecture:

        User Question
             ↓
        LLM Planner
             ↓
        JSON
             ↓
        Pydantic Validation
             ↓
        QueryIntent
             ↓
        QueryService
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "auto").lower()

        # Optional Ollama structured output.
        #
        # false = current behavior
        # true  = Ollama receives QueryIntent JSON schema
        #
        # We keep this OFF initially so the existing
        # llama3.2:3b setup continues to work exactly as before.
        self.ollama_structured_output = (
            os.getenv("OLLAMA_STRUCTURED_OUTPUT", "false").lower()
            in {"1", "true", "yes", "on"}
        )

    # ========================================================
    # PUBLIC METHOD
    # ========================================================
    def plan(self, question: str) -> QueryIntent:
        raw = self._call(question)

        obj = self._extract_json(raw)

        obj = self._normalize_null_strings(obj)

        obj = self._normalize_intent(obj)

        obj = self._repair_not_resolved_within_logic(
            obj,
            question
        )

        return QueryIntent.model_validate(obj)
    # ========================================================
    # INTENT NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_intent(obj):
        """
        Normalize harmless LLM formatting mistakes before
        Pydantic validation.

        This does NOT perform business logic.

        It only converts common model-output mistakes into
        the format expected by QueryIntent.
        """

        if not isinstance(obj, dict):
            return obj

        # ----------------------------------------------------
        # Ensure time_range exists
        # ----------------------------------------------------

        time_range = obj.get("time_range")

        if not isinstance(time_range, dict):
            obj["time_range"] = {
                "kind": "none",
                "start": None,
                "end": None,
            }

        else:
            kind = time_range.get("kind")

            if kind is None:
                time_range["kind"] = "none"

            elif kind in {"now", "current", "currently"}:
                time_range["kind"] = "none"
                time_range["start"] = None
                time_range["end"] = None

            # between_dates requires start + end
            elif kind == "between_dates":

                if (
                    not time_range.get("start")
                    or not time_range.get("end")
                ):
                    time_range["kind"] = "none"
                    time_range["start"] = None
                    time_range["end"] = None

            # after_date requires start
            elif kind == "after_date":

                if not time_range.get("start"):
                    time_range["kind"] = "none"
                    time_range["start"] = None
                    time_range["end"] = None

            # before_date requires end
            elif kind == "before_date":

                if not time_range.get("end"):
                    time_range["kind"] = "none"
                    time_range["start"] = None
                    time_range["end"] = None

        # ----------------------------------------------------
        # Normalize filters
        # ----------------------------------------------------

        for filter_list_name in ("filters", "any_filters"):

            filters = obj.get(filter_list_name)

            if not isinstance(filters, list):
                continue

            for filter_obj in filters:

                if not isinstance(filter_obj, dict):
                    continue

                operator = filter_obj.get("operator")
                value = filter_obj.get("value")

                # Example:
                #
                # "Critical,High"
                #
                # becomes:
                #
                # ["Critical", "High"]
                #
                # This is useful when a model understands
                # "in" but returns a comma-separated string.

                if (
                    operator == "in"
                    and isinstance(value, str)
                    and "," in value
                ):
                    filter_obj["value"] = [
                        item.strip()
                        for item in value.split(",")
                        if item.strip()
                    ]

        return obj
    @staticmethod
    def _repair_not_resolved_within_logic(obj, question):
        """
        Repair a specific logical pattern:

        "not resolved within N hours"

        Intended meaning:

            status != Resolved
            OR
            resolution_time_hrs > N

        This is applied only when the user's question explicitly
        contains the phrase "not resolved within".
        """

        if not isinstance(obj, dict):
            return obj

        question_lower = question.lower()

        # Only activate for this specific natural-language pattern.
        if "not resolved within" not in question_lower:
            return obj

        filters = obj.get("filters")

        if not isinstance(filters, list):
            return obj

        # Find the two filters produced by the LLM.
        status_filter = None
        resolution_filter = None

        for f in filters:
            if not isinstance(f, dict):
                continue

            if (
                f.get("field") == "status"
                and f.get("operator") == "neq"
                and str(f.get("value", "")).lower() == "resolved"
            ):
                status_filter = f

            if (
                f.get("field") == "resolution_time_hrs"
                and f.get("operator") == "gt"
            ):
                resolution_filter = f

        # If the LLM did not produce both expected filters,
        # don't interfere with its output.
        if status_filter is None or resolution_filter is None:
            return obj

        # Remove them from the AND filters.
        obj["filters"] = [
            f
            for f in filters
            if f is not status_filter and f is not resolution_filter
        ]

        # Put them into the OR section.
        any_filters = obj.get("any_filters")

        if not isinstance(any_filters, list):
            any_filters = []

        any_filters.extend([
            status_filter,
            resolution_filter,
        ])

        obj["any_filters"] = any_filters

        return obj
    # ========================================================
    # NULL NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_null_strings(obj):
        """
        Some local models return:

            "null"

        instead of:

            null

        Normalize only exact null-like strings.
        """

        if isinstance(obj, dict):

            return {
                key: LLMService._normalize_null_strings(value)
                for key, value in obj.items()
            }

        if isinstance(obj, list):

            return [
                LLMService._normalize_null_strings(value)
                for value in obj
            ]

        if (
            isinstance(obj, str)
            and obj.strip().lower() in {"null", "none"}
        ):
            return None

        return obj

    # ========================================================
    # LLM CALL
    # ========================================================

    def _call(self, question: str) -> str:

        provider = self.provider

        # ----------------------------------------------------
        # AUTO PROVIDER SELECTION
        # ----------------------------------------------------

        if provider == "auto":

            if os.getenv("GROQ_API_KEY"):
                provider = "groq"

            elif os.getenv("HF_TOKEN"):
                provider = "huggingface"

            else:
                provider = "ollama"

        # ----------------------------------------------------
        # GROQ
        # ----------------------------------------------------

        if provider == "groq":

            from groq import Groq

            key = os.getenv("GROQ_API_KEY")

            if not key:
                raise RuntimeError(
                    "GROQ_API_KEY is not configured"
                )

            client = Groq(api_key=key)

            response = client.chat.completions.create(
                model=os.getenv(
                    "GROQ_MODEL",
                    "llama-3.1-8b-instant",
                ),
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": question,
                    },
                ],
                temperature=0,
                response_format={
                    "type": "json_object"
                },
            )

            return response.choices[0].message.content

        # ----------------------------------------------------
        # HUGGING FACE
        # ----------------------------------------------------

        if provider == "huggingface":

            from huggingface_hub import InferenceClient

            token = os.getenv("HF_TOKEN")

            if not token:
                raise RuntimeError(
                    "HF_TOKEN is not configured"
                )

            client = InferenceClient(token=token)

            response = client.chat.completions.create(
                model=os.getenv(
                    "HF_MODEL",
                    "Qwen/Qwen2.5-7B-Instruct",
                ),
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": question,
                    },
                ],
                temperature=0,
                max_tokens=600,
            )

            return response.choices[0].message.content

        # ----------------------------------------------------
        # OLLAMA
        # ----------------------------------------------------

        if provider == "ollama":

            import requests

            base_url = os.getenv(
                "OLLAMA_BASE_URL",
                "http://localhost:11434",
            )

            model = os.getenv(
                "OLLAMA_MODEL",
                "llama3.2:3b",
            )

            payload = {
                "model": model,

                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": question,
                    },
                ],

                "stream": False,

                "options": {
                    "temperature": 0,
                },
            }

            # ------------------------------------------------
            # OPTIONAL STRUCTURED OUTPUT
            # ------------------------------------------------
            #
            # When enabled, Ollama receives the exact
            # QueryIntent JSON schema generated by Pydantic.
            #
            # This improves structural reliability.
            #
            # It does NOT replace the prompt.
            # The prompt still explains the semantics.
            #
            # Example:
            #
            # User:
            # "How many tickets are either Critical or High?"
            #
            # The schema guarantees the structure, while
            # the prompt/model determines whether the
            # conditions belong in filters or any_filters.
            # ------------------------------------------------

            if self.ollama_structured_output:

                payload["format"] = (
                    QueryIntent.model_json_schema()
                )

            response = requests.post(
                f"{base_url}/api/chat",
                json=payload,
                timeout=180,
            )

            response.raise_for_status()

            data = response.json()

            return data["message"]["content"]

        # ----------------------------------------------------
        # INVALID PROVIDER
        # ----------------------------------------------------

        raise RuntimeError(
            "Unsupported LLM_PROVIDER. "
            "Use auto, ollama, groq, or huggingface."
        )

    # ========================================================
    # JSON EXTRACTION
    # ========================================================

    @staticmethod
    def _extract_json(text: str) -> dict:
        """
        Extract JSON from the model response.

        Handles:

        1. Pure JSON
        2. ```json ... ```
        3. JSON surrounded by explanatory text
        """

        text = text.strip()

        # ----------------------------------------------------
        # Remove markdown code fences
        # ----------------------------------------------------

        if text.startswith("```"):

            text = re.sub(
                r"^```(?:json)?",
                "",
                text,
            ).strip()

            text = re.sub(
                r"```$",
                "",
                text,
            ).strip()

        # ----------------------------------------------------
        # Direct JSON
        # ----------------------------------------------------

        try:

            return json.loads(text)

        except json.JSONDecodeError:
            pass

        # ----------------------------------------------------
        # JSON embedded inside text
        # ----------------------------------------------------

        match = re.search(
            r"\{.*\}",
            text,
            re.S,
        )

        if not match:

            raise ValueError(
                "LLM did not return valid JSON"
            )

        try:

            return json.loads(
                match.group(0)
            )

        except json.JSONDecodeError as exc:

            raise ValueError(
                "LLM returned malformed JSON"
            ) from exc
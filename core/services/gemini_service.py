import time
import google.generativeai as genai
from django.conf import settings


class GeminiQuotaExceeded(Exception):
    """Raised when the Gemini API daily quota is exhausted."""
    pass


class GeminiUnavailable(Exception):
    """Raised when the model is temporarily overloaded (HTTP 503 / high demand)."""
    pass


class GeminiService:
    """
    Wraps the Google Gemini API.
    Uses gemini-2.0-flash: good free-tier limits and far more available than
    gemini-2.5-flash, which frequently returns 503 'high demand'.
    """

    # Per-request timeout (seconds). Kept well under gunicorn's --timeout so the
    # web worker returns a real response instead of being SIGKILLed mid-retry.
    REQUEST_TIMEOUT = 45

    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.0-flash')

    def fetch_response(self, prompt: str) -> str:
        """
        Send a prompt to Gemini and return the text response.
        Bounds each call with a timeout and retries transient errors once.
        Raises GeminiQuotaExceeded (quota) or GeminiUnavailable (503) so the
        view can return a clean JSON error instead of crashing the worker.
        """
        max_retries = 2

        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    prompt,
                    request_options={'timeout': self.REQUEST_TIMEOUT},
                )
                return response.text

            except Exception as e:
                error_str = str(e).lower()

                # Quota exhausted — no point retrying, surface immediately
                if any(kw in error_str for kw in ('quota', 'resourceexhausted', '429', 'rate limit')):
                    raise GeminiQuotaExceeded(
                        "Daily API quota exceeded. Please try again tomorrow "
                        "or upgrade your Gemini API plan at aistudio.google.com."
                    )

                # Model overloaded (503) — retry once quickly, then fail fast
                if any(kw in error_str for kw in ('unavailable', '503', 'high demand', 'overloaded')):
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    raise GeminiUnavailable(
                        "The AI model is busy right now (high demand). "
                        "Please wait a moment and try again."
                    )

                # Other transient error — short backoff then retry once
                if attempt < max_retries - 1:
                    print(f"[GeminiService] Attempt {attempt + 1} failed, retrying: {e}")
                    time.sleep(2)
                else:
                    print(f"[GeminiService] All retries exhausted: {e}")
                    return ""

        return ""

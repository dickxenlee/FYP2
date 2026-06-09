import os
import time
import google.generativeai as genai
from django.conf import settings


class GeminiQuotaExceeded(Exception):
    """Raised when the Gemini API request limit (per-minute or per-day) is hit."""
    pass


class GeminiUnavailable(Exception):
    """Raised when the model is temporarily overloaded (HTTP 503 / high demand)."""
    pass


class GeminiService:
    """
    Wraps the Google Gemini API.

    Model is configurable via the GEMINI_MODEL env var. Default is
    gemini-2.5-flash-lite, which has the highest free-tier daily limit
    (~1,000 requests/day vs ~200/day for gemini-2.0-flash).
    """

    # Per-request timeout (seconds). Kept well under gunicorn's timeout so the
    # web worker returns a real response instead of being SIGKILLed mid-retry.
    REQUEST_TIMEOUT = 45

    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model_name = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash-lite')
        self.model = genai.GenerativeModel(model_name)

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

                # Rate / quota limit. A 429 is often the PER-MINUTE limit (resets
                # in ~60s), not the daily cap — so retry once after a short wait
                # before giving up, and word the message accordingly.
                if any(kw in error_str for kw in ('quota', 'resourceexhausted', '429', 'rate limit')):
                    if attempt < max_retries - 1:
                        time.sleep(5)
                        continue
                    raise GeminiQuotaExceeded(
                        "Gemini API limit reached. This is usually the per-minute "
                        "rate limit — wait about a minute and try again. If it "
                        "keeps happening you've hit the daily free quota, which "
                        "resets at midnight Pacific time. To raise the limit, use a "
                        "key from another Google account or enable billing at "
                        "aistudio.google.com."
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

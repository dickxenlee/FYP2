import time
import google.generativeai as genai
from django.conf import settings


class GeminiError(Exception):
    """Base class for Gemini failures. `message` is safe to show the user."""
    status = 503


class GeminiQuotaExceeded(GeminiError):
    """Raised when the Gemini API daily quota is exhausted."""
    status = 429


class GeminiNotConfigured(GeminiError):
    """Raised when no API key is set."""
    status = 503


class GeminiUnavailable(GeminiError):
    """Raised when the API does not return a usable response."""
    status = 503


class GeminiService:
    """
    Wraps the Google Gemini API (model: gemini-2.5-flash-lite, chosen for its
    high free-tier request limit).
    """

    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # temperature=0 makes the output deterministic, so the same requirement
        # always returns the same Accuracy Score (reproducible for evaluation).
        # max_output_tokens caps each reply to keep token usage (and free-tier
        # quota consumption) low; 8192 is high enough for a full multi-requirement
        # report, so the JSON is never cut off.
        self.model = genai.GenerativeModel(
            'gemini-2.5-flash-lite',
            generation_config={'temperature': 0, 'max_output_tokens': 8192},
        )

    # Max seconds to wait for one Gemini reply before giving up, so a slow or
    # frozen API never makes the request hang forever.
    REQUEST_TIMEOUT = 60

    def fetch_response(self, prompt: str) -> str:
        """
        Send a prompt to Gemini and return the text response.
        Retries up to 3 times on transient errors with exponential backoff.
        Raises GeminiQuotaExceeded if the daily quota is hit, GeminiNotConfigured
        if no API key is set, and GeminiUnavailable if the service does not respond.
        """
        if not (settings.GEMINI_API_KEY or '').strip():
            raise GeminiNotConfigured(
                "The AI service is not set up yet. Please add a Gemini API key "
                "(GEMINI_API_KEY) and try again."
            )

        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    prompt,
                    request_options={'timeout': self.REQUEST_TIMEOUT},
                )
                return response.text

            except Exception as e:
                error_str = str(e).lower()

                # Quota exhausted — no point retrying, surface the error immediately
                if any(kw in error_str for kw in ('quota', 'resourceexhausted', '429', 'rate limit')):
                    raise GeminiQuotaExceeded(
                        "Daily AI quota exceeded. Please try again tomorrow "
                        "or upgrade your Gemini API plan at aistudio.google.com."
                    )

                # Transient error — wait and retry
                if attempt < max_retries - 1:
                    wait_seconds = 2 ** attempt   # 1 s, 2 s, 4 s
                    print(f"[GeminiService] Attempt {attempt + 1} failed, retrying in {wait_seconds}s: {e}")
                    time.sleep(wait_seconds)
                else:
                    print(f"[GeminiService] All retries exhausted: {e}")
                    raise GeminiUnavailable(
                        "The AI service is not responding right now. Please try again in a moment."
                    )

        raise GeminiUnavailable(
            "The AI service is not responding right now. Please try again in a moment."
        )

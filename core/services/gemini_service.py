import time
import google.generativeai as genai
from django.conf import settings


class GeminiQuotaExceeded(Exception):
    """Raised when the Gemini API daily quota is exhausted."""
    pass


class GeminiService:
    """
    Wraps the Google Gemini API.
    Uses gemini-1.5-flash: 1,500 requests/day on the free tier
    (vs gemini-2.5-flash which only allows 20/day).
    """

    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def fetch_response(self, prompt: str) -> str:
        """
        Send a prompt to Gemini and return the text response.
        Retries up to 3 times on transient errors with exponential backoff.
        Raises GeminiQuotaExceeded immediately if the daily quota is hit.
        """
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                return response.text

            except Exception as e:
                error_str = str(e).lower()

                # Quota exhausted — no point retrying, surface the error immediately
                if any(kw in error_str for kw in ('quota', 'resourceexhausted', '429', 'rate limit')):
                    raise GeminiQuotaExceeded(
                        "Daily API quota exceeded. Please try again tomorrow "
                        "or upgrade your Gemini API plan at aistudio.google.com."
                    )

                # Transient error — wait and retry
                if attempt < max_retries - 1:
                    wait_seconds = 2 ** attempt   # 1 s, 2 s, 4 s
                    print(f"[GeminiService] Attempt {attempt + 1} failed, retrying in {wait_seconds}s: {e}")
                    time.sleep(wait_seconds)
                else:
                    print(f"[GeminiService] All retries exhausted: {e}")
                    return ""

        return ""

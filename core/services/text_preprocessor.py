import re
import unicodedata


class TextPreprocessor:
    """
    Light NLP preprocessing applied to raw requirement text before it is sent
    to the LLM for semantic analysis.

    This is the system's text-normalization (NLP) step. It cleans and
    normalizes free-text input so the analysis always works on consistent,
    well-formed text regardless of how the user typed or pasted it.

    Steps:
      1. Unicode normalization (NFKC) — converts smart quotes, full-width
         characters and similar variants into their plain equivalents.
      2. Remove invisible/control characters (zero-width spaces, etc.).
      3. Strip Markdown formatting marks at the start of lines
         (headings '#', block quotes '>', and bullet symbols).
      4. Normalize whitespace — collapse repeated spaces, limit blank lines,
         and trim each line and the whole text.
    """

    _LINE_MARKERS = re.compile(r'^\s*(?:#{1,6}\s*|>+\s*|[-*+•·●▪]\s+)', re.MULTILINE)
    _MULTISPACE = re.compile(r'[ \t]{2,}')
    _BLANKLINES = re.compile(r'\n{3,}')

    # Typographic characters → plain ASCII equivalents
    _PUNCT_MAP = {
        '‘': "'", '’': "'",            # ‘ ’ single quotes
        '“': '"', '”': '"',            # “ ” double quotes
        '–': '-', '—': '-',            # – — dashes
        '…': '...',                         # … ellipsis
    }
    _PUNCT_TABLE = str.maketrans(_PUNCT_MAP)

    def clean(self, text: str) -> str:
        """Return the cleaned, normalized version of the input text."""
        if not text:
            return ''

        # 1. Unicode normalization
        text = unicodedata.normalize('NFKC', text)
        text = text.translate(self._PUNCT_TABLE)

        # 2. Drop control/invisible characters, but keep newlines and tabs
        text = ''.join(
            ch for ch in text
            if ch in '\n\t' or unicodedata.category(ch)[0] != 'C'
        )

        # 3. Strip Markdown markers at the start of lines
        text = self._LINE_MARKERS.sub('', text)

        # 4. Normalize whitespace
        text = self._MULTISPACE.sub(' ', text)
        text = self._BLANKLINES.sub('\n\n', text)
        text = '\n'.join(line.strip() for line in text.split('\n'))

        return text.strip()

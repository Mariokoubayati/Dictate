"""LLM cleanup pass: raw transcript -> clean text via Claude Haiku."""

import os
import sys

import anthropic

import config


def require_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY is not set. Set it with: "
            'export ANTHROPIC_API_KEY="sk-ant-..." (add to ~/.zshrc to persist)'
        )


class Cleaner:
    def __init__(self):
        self._client = anthropic.Anthropic()

    def clean(self, transcript: str) -> str:
        """Return the cleaned transcript. Falls back to the raw transcript
        if the API call fails, so dictation is never lost."""
        if not transcript.strip():
            return ""
        try:
            response = self._client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=4096,
                system=config.CLEANUP_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "<transcript>\n"
                            f"{transcript}\n"
                            "</transcript>"
                        ),
                    }
                ],
            )
            cleaned = response.content[0].text.strip()
            return cleaned if cleaned else transcript
        except Exception as exc:
            print(f"cleanup: API call failed ({exc}); injecting raw transcript",
                  file=sys.stderr)
            return transcript

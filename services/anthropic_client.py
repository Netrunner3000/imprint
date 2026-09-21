import os

from services.api_limits import REQUEST_TIMEOUT_SECONDS, MAX_RETRIES

try:
    import anthropic as _sdk
    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False


class AnthropicClientWrapper:
    KNOWN_MODELS = [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ]

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.client = (
            _sdk.Anthropic(
                api_key=api_key,
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=MAX_RETRIES,
            )
            if _HAS_SDK and api_key
            else None
        )

    @staticmethod
    def key_available() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY", ""))

    def list_models(self) -> list[str]:
        if not self.client:
            return self.KNOWN_MODELS
        try:
            result = self.client.models.list()
            models = sorted(m.id for m in result.data)
            return models if models else self.KNOWN_MODELS
        except Exception:
            return self.KNOWN_MODELS

    # test_connection() was removed here and in the Qwen wrapper: nothing
    # called either (the API-keys status card reads key_available() only),
    # and wiring one up would have made an unguarded paid call.

    def stream_chat(self, messages: list, model: str = "claude-sonnet-4-6"):
        if not self.client:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set.\n"
                "Add it to your .env file and restart the app."
            )
        system, chat_messages = self._split(messages)
        kwargs = {"model": model, "max_tokens": 8096, "messages": chat_messages}
        if system:
            kwargs["system"] = system

        def _gen(out):
            yield from self._stream(kwargs, out)

        from services.stream_usage import UsageStream
        return UsageStream(_gen)

    def _stream(self, kwargs, out):
        try:
            with self.client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text
                # The final message carries the real token counts; without
                # this the whole stream was billed on the chars/4 estimate.
                try:
                    final = stream.get_final_message()
                    if final is not None and final.usage is not None:
                        out.usage = {
                            "input_tokens": final.usage.input_tokens,
                            "output_tokens": final.usage.output_tokens,
                        }
                except Exception:
                    pass    # usage is best-effort; the text already streamed
        except _sdk.AuthenticationError:
            raise RuntimeError(
                "AuthenticationError (401) — API key invalid or expired.\n"
                "→ Go to console.anthropic.com → API Keys and generate a new key,\n"
                "  then update ANTHROPIC_API_KEY in your .env file."
            )
        except _sdk.APIConnectionError:
            raise RuntimeError(
                "APIConnectionError — Could not reach api.anthropic.com.\n"
                "→ Check your internet connection.\n"
                "→ If your key is new, make sure it has been activated.\n"
                "→ Check that no firewall or VPN is blocking outbound HTTPS."
            )
        except _sdk.RateLimitError:
            raise RuntimeError(
                "RateLimitError (429) — Too many requests.\n"
                "→ Wait a moment and try again.\n"
                "→ Check your usage limits at console.anthropic.com."
            )
        except _sdk.NotFoundError:
            raise RuntimeError(
                f"NotFoundError (404) — Model '{model}' does not exist.\n"
                "→ Select a different model from the dropdown."
            )
        except _sdk.APIStatusError as e:
            raise RuntimeError(
                f"APIStatusError ({e.status_code}) — {e.message}"
            )

    def chat(self, messages: list, model: str = "claude-sonnet-4-6"):
        if not self.client:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set.\n"
                "Add it to your .env file and restart the app."
            )
        system, chat_messages = self._split(messages)
        kwargs = {"model": model, "max_tokens": 8096, "messages": chat_messages}
        if system:
            kwargs["system"] = system
        try:
            response = self.client.messages.create(**kwargs)
        except _sdk.AuthenticationError:
            raise RuntimeError(
                "AuthenticationError (401) — API key invalid or expired.\n"
                "→ Go to console.anthropic.com → API Keys and generate a new key,\n"
                "  then update ANTHROPIC_API_KEY in your .env file."
            )
        except _sdk.APIConnectionError:
            raise RuntimeError(
                "APIConnectionError — Could not reach api.anthropic.com.\n"
                "→ Check your internet connection.\n"
                "→ If your key is new, make sure it has been activated.\n"
                "→ Check that no firewall or VPN is blocking outbound HTTPS."
            )
        except _sdk.RateLimitError:
            raise RuntimeError(
                "RateLimitError (429) — Too many requests.\n"
                "→ Wait a moment and try again."
            )
        except _sdk.NotFoundError:
            raise RuntimeError(
                f"NotFoundError (404) — Model '{model}' does not exist.\n"
                "→ Select a different model from the dropdown."
            )
        except _sdk.APIStatusError as e:
            raise RuntimeError(
                f"APIStatusError ({e.status_code}) — {e.message}"
            )
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        # content can be empty (max_tokens exhausted before any text block)
        # and can carry more than one text block; indexing [0] crashed on the
        # first case and silently dropped the rest on the second.
        text = "".join(
            block.text for block in response.content
            if getattr(block, "type", "") == "text")
        return text, usage

    def _split(self, messages: list) -> tuple[str, list]:
        system = ""
        chat = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat.append({"role": msg["role"], "content": msg["content"]})
        return system, chat

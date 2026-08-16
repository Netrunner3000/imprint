"""Shared network limits for the paid provider clients.

None of the cloud wrappers passed a timeout, so a hung connection blocked the
agent that made the call indefinitely, with no way to recover short of killing
the app. (`ollama_client` already set 10s/300s; the five paid clients set
nothing.)

The timeout is deliberately generous. For streaming responses the SDKs apply it
between chunks rather than to the whole generation, so this breaks a dead
connection without capping a slow model.
"""

# Seconds — openai / deepseek / kimi / anthropic SDKs.
REQUEST_TIMEOUT_SECONDS = 120.0

# Milliseconds — google-genai's HttpOptions takes ms, not seconds.
REQUEST_TIMEOUT_MS = int(REQUEST_TIMEOUT_SECONDS * 1000)

# One retry on transient/connection errors. Kept low on purpose: a retry of a
# paid request costs money, and the request has already been budget-checked
# once by GodAI.authorize_request().
MAX_RETRIES = 1

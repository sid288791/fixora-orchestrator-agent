"""
Groq LLM call used by DiagnosticLoop for phase 1 (replaces the local-Ollama
default so the orchestrator uses the same LLM provider as fixora-rca-ai).
"""
import httpx

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


async def call_groq(prompt: str, api_key: str, model: str) -> str:
    if not api_key:
        raise RuntimeError("GROQ_API_KEY / LLM_API_KEY not configured")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

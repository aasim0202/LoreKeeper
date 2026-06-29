"""
LoreKeeper 3.0 — Fallback LLM Client (Ollama Cloud API)
Streams responses from Ollama Cloud when the primary Gemini API fails.
"""
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)

# Configurable fallback parameters
FALLBACK_BASE_URL = os.getenv("FALLBACK_BASE_URL", "https://ollama.com")
FALLBACK_API_KEY = os.getenv("FALLBACK_API_KEY", "")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-oss:120b")


def generate_fallback_stream(prompt: str):
    """
    Calls the Ollama Cloud /api/chat endpoint using NDJSON streaming.
    Yields chunks of text as they arrive.
    """
    if not FALLBACK_API_KEY:
        logger.error("Fallback LLM triggered but no FALLBACK_API_KEY is configured.")
        yield ""
        return

    url = f"{FALLBACK_BASE_URL.rstrip('/')}/api/chat"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FALLBACK_API_KEY}"
    }
    
    payload = {
        "model": FALLBACK_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": True
    }

    logger.info(f"Initiating fallback stream to {url} using model {FALLBACK_MODEL}")

    try:
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=10) as response:
            if response.status_code != 200:
                logger.error(f"Fallback LLM failed with status {response.status_code}: {response.text}")
                yield f"Fallback API Error: HTTP {response.status_code}"
                return
            
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    try:
                        chunk_data = json.loads(decoded)
                        if "message" in chunk_data and "content" in chunk_data["message"]:
                            yield chunk_data["message"]["content"]
                        
                        if chunk_data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error(f"Fallback LLM connection error: {e}")
        yield f"Fallback Connection Error: {e}"

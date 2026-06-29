from dotenv import load_dotenv
import os

# Load variables from .env file
load_dotenv()

import json
import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

# Inter-module imports
from src.vector_db import generate_embeddings, qdrant_client
from src.ingestion import fetch_tavily_context, scrape_with_jina
import time
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

genai_client = None
try:
    # Attempt to initialize using Vertex AI (consumes actual Google Cloud credits)
    genai_client = genai.Client(
        vertexai=True,
        project="gen-lang-client-0682780765",
        location="us-central1"
    )
    logger.info("Successfully initialized Gemini using Vertex AI backend.")
except Exception as e:
    logger.warning(f"Vertex AI initialization failed: {e}. Falling back to AI Studio API key...")
    try:
        if os.getenv("GEMINI_API_KEY"):
            genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            logger.info("Successfully initialized Gemini using AI Studio API Key.")
    except Exception as inner_e:
        logger.error(f"Failed to initialize Gemini Client completely: {inner_e}")
    genai_client = None

# ------------------------------------------------------------------
# Structured JSON Schema Definitions using Pydantic
# ------------------------------------------------------------------
class AgentResponse(BaseModel):
    reply: str = Field(description="The direct, synthesized response from the Chief of Staff.")
    action_items: List[str] = Field(description="A list of actionable tasks or explicit next steps.")

# ------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------
def requires_real_time_search(message: str) -> bool:
    """
    Heuristic to determine if the user's message requires real-time information.
    Checks for temporal keywords or explicit URLs.
    """
    keywords = ['latest', 'current', 'today', 'now', 'news', 'search', 'recent', 'update']
    msg_lower = message.lower()
    
    if any(k in msg_lower for k in keywords):
        return True
    if 'http://' in msg_lower or 'https://' in msg_lower:
        return True
    return False

from google.genai import errors

# ... (other imports remain, just need to make sure we can import fallback)
from src.fallback_llm import generate_fallback_stream

# ------------------------------------------------------------------
# Core Processing Function — Streaming Generator
# ------------------------------------------------------------------
def process_user_query_stream(user_message: str, collection_name: str = "lorekeeper_memory", enable_jina: bool = False):
    """
    Generator that yields SSE event dicts at each pipeline stage.
    The final yield is a 'complete' event with the full response payload.
    """
    if not genai_client:
        yield {"event": "error", "message": "Google GenAI client is not initialized."}
        return

    logger.info(f"Processing user query (stream): '{user_message}'")

    latencies = {}
    start_total = time.perf_counter()
    memory_sources = []
    web_sources = []
    jina_sources = []

    # ── Stage 1: Qdrant Retrieval ──────────────────────
    yield {"event": "stage", "stage": "qdrant_retrieval_started"}

    start_qdrant = time.perf_counter()
    query_embeddings = generate_embeddings([user_message])
    qdrant_context = ""

    if query_embeddings and query_embeddings[0]:
        query_vector = query_embeddings[0]
        try:
            search_result = qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=5
            )
            for hit in search_result:
                payload = hit.payload or {}
                text = payload.get("text", "")
                qdrant_context += f"- [Memory Context Score {hit.score:.2f}]: {text}\n"
                memory_sources.append({"text": text[:200], "score": round(hit.score, 2)})
        except Exception as e:
            logger.error(f"Error querying Qdrant memory cluster: {e}")
            qdrant_context = "Warning: Qdrant retrieval failed.\n"

    latencies["qdrant"] = round((time.perf_counter() - start_qdrant) * 1000, 2)
    yield {"event": "stage", "stage": "qdrant_retrieval_done", "chunks": len(memory_sources), "latency_ms": latencies["qdrant"]}

    # ── Stage 2: Tavily Web Search ─────────────────────
    tavily_context = ""
    needs_tavily = requires_real_time_search(user_message)

    if needs_tavily:
        yield {"event": "stage", "stage": "tavily_fetch_started"}

    start_tavily = time.perf_counter()
    if needs_tavily:
        logger.info("Real-time context requested by heuristic. Searching Tavily...")
        web_data = fetch_tavily_context(user_message)
        if web_data and "results" in web_data:
            for res in web_data["results"]:
                tavily_context += f"- {res.get('title')}: {res.get('content')}\n"
                web_sources.append({
                    "title": res.get("title", "Untitled"),
                    "url": res.get("url", "")
                })
    latencies["tavily"] = round((time.perf_counter() - start_tavily) * 1000, 2)

    if needs_tavily:
        yield {"event": "stage", "stage": "tavily_fetch_done", "results": len(web_sources), "latency_ms": latencies["tavily"]}

    # ── Stage 3: Jina Scraping ─────────────────────────
    jina_context = ""
    if enable_jina:
        urls = re.findall(r'(https?://[^\s]+)', user_message)
        if urls:
            yield {"event": "stage", "stage": "jina_scrape_started"}

        start_jina = time.perf_counter()
        for url in urls:
            logger.info(f"Scraping URL via Jina: {url}")
            scraped = scrape_with_jina(url)
            if scraped:
                jina_context += f"\n--- SCRAPED FROM {url} ---\n{scraped[:2000]}\n"
                jina_sources.append({"url": url})
        latencies["jina"] = round((time.perf_counter() - start_jina) * 1000, 2)

        if urls:
            yield {"event": "stage", "stage": "jina_scrape_done", "urls": len(jina_sources), "latency_ms": latencies["jina"]}
    else:
        latencies["jina"] = 0.0

    # ── Stage 4: Gemini Generation ─────────────────────
    bundled_context = f"""
    === RELEVANT PAST CONTEXT (QDRANT MEMORY) ===
    {qdrant_context if qdrant_context.strip() else "No historical context found."}
    
    === REAL-TIME WEB CONTEXT (TAVILY) ===
    {tavily_context if tavily_context.strip() else "No real-time web context deemed necessary."}
    
    === DIRECT URL SCRAPES (JINA) ===
    {jina_context if jina_context.strip() else "No direct URLs scraped."}
    """

    system_instruction = (
        "You are a strict, logical, highly analytical Chief of Staff. "
        "Your role is to process user inquiries, manage operational chaos, and provide decisive guidance. "
        "Review the provided past memory context and real-time web data to construct a highly informed response. "
        "You must isolate high-risk actions and explicitly break complex requests down into actionable next steps. "
        "Do not offer generic pleasantries. Output strictly in the enforced JSON schema."
    )

    prompt = f"SYSTEM INSTRUCTION: {system_instruction}\n\n" \
             f"USER MESSAGE:\n{user_message}\n\nCONTEXT BUNDLE:\n{bundled_context}\n\n" \
             "Synthesize your response using the provided data. YOU MUST RETURN ONLY STRICT, VALID JSON containing exactly two keys: 'reply' (string) and 'action_items' (array of strings). Do not include markdown blocks or any other text."

    yield {"event": "stage", "stage": "gemini_generation_started"}
    logger.info("Feeding bundled knowledge to Gemini (streaming)...")

    start_gemini = time.perf_counter()
    raw_text = ""
    fallback_used = False
    
    try:
        stream = genai_client.models.generate_content_stream(
            model='gemini-1.5-flash-001',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2
            )
        )
        for chunk in stream:
            chunk_text = chunk.text or ""
            if chunk_text:
                raw_text += chunk_text
                yield {"event": "gemini_chunk", "text": chunk_text}
                
    except Exception as e:
        error_str = str(e).lower()
        if "429" in error_str or "resource_exhausted" in error_str or "404" in error_str:
            logger.warning(f"Gemini API failure ({e}). Triggering Smart Switch to Fallback LLM...")
            yield {"event": "stage", "stage": "fallback_llm_started"}
            fallback_used = True
            
            # Reset text generation and stream from fallback instead
            raw_text = ""
            for fallback_chunk in generate_fallback_stream(prompt):
                raw_text += fallback_chunk
                # We yield as 'gemini_chunk' so the frontend seamlessly appends it to the bubble
                yield {"event": "gemini_chunk", "text": fallback_chunk}
        else:
            logger.error(f"Error during Gemini processing: {e}")
            latencies["gemini"] = round((time.perf_counter() - start_gemini) * 1000, 2)
            latencies["total"] = round((time.perf_counter() - start_total) * 1000, 2)
            fallback_response = {"reply": f"Internal Error: {e}", "action_items": [], "sources": {"memory": [], "web": [], "jina": []}, "latency": latencies}
            yield {"event": "complete", "data": fallback_response}
            return

    # Parsing block (runs for both successful Gemini or successful Fallback)
    latencies["gemini"] = round((time.perf_counter() - start_gemini) * 1000, 2)

    try:
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.endswith("```"):
            clean = clean[:-3]

        parsed = json.loads(clean.strip())
        parsed["sources"] = {"memory": memory_sources, "web": web_sources, "jina": jina_sources}
        if fallback_used:
            parsed["sources"]["fallback"] = True
            
        latencies["total"] = round((time.perf_counter() - start_total) * 1000, 2)
        parsed["latency"] = latencies

        yield {"event": "complete", "data": parsed}

    except json.JSONDecodeError:
        logger.error(f"Failed to parse LLM response as JSON: {raw_text[:200]}")
        latencies["total"] = round((time.perf_counter() - start_total) * 1000, 2)
        fallback_payload = {"reply": raw_text.strip(), "action_items": [], "sources": {"memory": memory_sources, "web": web_sources, "jina": jina_sources}, "latency": latencies}
        if fallback_used:
            fallback_payload["sources"]["fallback"] = True
        yield {"event": "complete", "data": fallback_payload}


# ------------------------------------------------------------------
# Non-streaming wrapper (preserves existing /discord-bot-receiver)
# ------------------------------------------------------------------
def process_user_query(user_message: str, collection_name: str = "lorekeeper_memory", enable_jina: bool = False) -> str:
    """
    Synchronous wrapper around the streaming generator.
    Returns the final JSON string exactly as before.
    """
    result = None
    for event in process_user_query_stream(user_message, collection_name, enable_jina):
        if event.get("event") == "complete":
            result = event["data"]
        elif event.get("event") == "error":
            raise ValueError(event.get("message", "Unknown error"))
    
    if result is None:
        raise ValueError("Pipeline did not produce a complete event.")
    
    return json.dumps(result)



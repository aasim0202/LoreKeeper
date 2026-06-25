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
from src.ingestion import fetch_tavily_context

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize the GenAI Client for gemini-1.5-flash
try:
    genai_client = genai.Client(http_options={'api_version': 'v1'})
except Exception as e:
    logger.warning(f"Could not initialize Google GenAI Client: {e}")
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

# ------------------------------------------------------------------
# Core Processing Function
# ------------------------------------------------------------------
def process_user_query(user_message: str, collection_name: str = "lorekeeper_memory") -> str:
    """
    Queries Qdrant for past context, uses Tavily if real-time data is needed,
    and injects everything into a strict Chief of Staff prompt.
    Forces Gemini 3.1 Pro to return a strict JSON schema containing a reply and action_items.
    """
    if not genai_client:
        raise ValueError("Google GenAI client is not initialized. Please ensure GEMINI_API_KEY is set.")
        
    logger.info(f"Processing user query: '{user_message}'")
    
    # 1. Retrieve relevant past context from Qdrant vector database
    logger.info("Generating embedding for the user message...")
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
        except Exception as e:
            logger.error(f"Error querying Qdrant memory cluster: {e}")
            qdrant_context = "Warning: Qdrant retrieval failed.\n"

    # 2. Use Tavily to search the web if the user's message requires real-time information
    tavily_context = ""
    if requires_real_time_search(user_message):
        logger.info("Real-time context requested by heuristic. Searching Tavily...")
        web_data = fetch_tavily_context(user_message)
        if web_data and "results" in web_data:
            for res in web_data["results"]:
                tavily_context += f"- {res.get('title')}: {res.get('content')}\n"

    # 3. Inject context into a strict Chief of Staff system prompt
    bundled_context = f"""
    === RELEVANT PAST CONTEXT (QDRANT MEMORY) ===
    {qdrant_context if qdrant_context.strip() else "No historical context found."}
    
    === REAL-TIME WEB CONTEXT (TAVILY) ===
    {tavily_context if tavily_context.strip() else "No real-time web context deemed necessary."}
    """

    system_instruction = (
        "You are a strict, logical, highly analytical Chief of Staff. "
        "Your role is to process user inquiries, manage operational chaos, and provide decisive guidance. "
        "Review the provided past memory context and real-time web data to construct a highly informed response. "
        "You must isolate high-risk actions and explicitly break complex requests down into actionable next steps. "
        "Do not offer generic pleasantries. Output strictly in the enforced JSON schema."
    )

    # Bake the system instruction directly into the prompt to bypass v1 limitations
    prompt = f"SYSTEM INSTRUCTION: {system_instruction}\n\n" \
             f"USER MESSAGE:\n{user_message}\n\nCONTEXT BUNDLE:\n{bundled_context}\n\n" \
             "Synthesize your response using the provided data. YOU MUST RETURN ONLY STRICT, VALID JSON containing exactly two keys: 'reply' (string) and 'action_items' (array of strings). Do not include markdown blocks or any other text."

    logger.info("Feeding bundled knowledge to Gemini...")

    try:
        response = genai_client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2  # Keep execution analytical and deterministic
            )
        )
        
        # Safely strip out markdown formatting if the model still returns it
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        return raw_text.strip()
    except Exception as e:
        logger.error(f"Error during Gemini processing: {e}")
        # Return fallback JSON matching schema to prevent app crashes
        fallback = {"reply": f"Internal Error: {e}", "action_items": []}
        return json.dumps(fallback)

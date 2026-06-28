from dotenv import load_dotenv
import os

# Load variables from .env file
load_dotenv()

import json
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
import time
import requests

# Inter-module imports
from src.agent import process_user_query
from src.ingestion import fetch_notion_data, fetch_google_tasks
from src.vector_db import qdrant_client, genai_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LoreKeeper 3.0 Server",
    description="FastAPI interface handling Discord payloads and background ingestion.",
    version="3.0"
)

# Enable CORS for local frontend testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# API Key Security Guard
# ------------------------------------------------------------------
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """
    Validates the X-API-Key header on every protected route.
    Returns 403 immediately if the key is missing or incorrect,
    consuming zero Gemini quota.
    """
    expected_key = os.getenv("API_SECRET_KEY")
    if not expected_key:
        logger.warning("API_SECRET_KEY is not set. Route is unprotected.")
        return
    if api_key != expected_key:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing X-API-Key header.")

# ------------------------------------------------------------------
# Request & Response Schemas
# ------------------------------------------------------------------
class DiscordWebhookPayload(BaseModel):
    content: str = Field(..., description="The text payload incoming from a Discord channel")
    author: Optional[str] = Field("unknown", description="Username of the message author")
    channel_id: Optional[str] = Field("unknown", description="ID of the Discord channel")
    enable_jina: bool = Field(False, description="Whether to scrape URLs found in the content using Jina")



# ------------------------------------------------------------------
# Background Tasks
# ------------------------------------------------------------------
def run_background_ingestion():
    """
    Triggers asynchronous data ingestion from your external data sources.
    """
    logger.info("Executing background data ingestion...")
    try:
        notion_records = fetch_notion_data()
        logger.info(f"Successfully scraped {len(notion_records)} records from Notion.")
        
        google_tasks = fetch_google_tasks()
        logger.info(f"Successfully scraped {len(google_tasks)} active tasks from Google Tasks.")
        
        # Typically, you would process and save these chunks into Qdrant via upsert_records() here.
        logger.info("Background data ingestion cycle completed seamlessly.")
    except Exception as e:
        logger.error(f"Error during background ingestion cycle: {e}")


# ------------------------------------------------------------------
# FastAPI API Endpoints
# ------------------------------------------------------------------
@app.post("/discord-bot-receiver", dependencies=[Security(verify_api_key)])
async def discord_bot_receiver(payload: DiscordWebhookPayload):
    """
    Accepts incoming JSON payloads from Discord, extracts the user's message, 
    passes it to process_user_query() from src/agent.py, and returns the strict JSON response.
    """
    raw_content = payload.content.strip()
    if not raw_content:
        raise HTTPException(status_code=400, detail="Payload content cannot be empty.")

    try:
        logger.info(f"Routing message from '{payload.author}' into Chief of Staff processing core...")
        
        # Engage the agent brain with the extracted message
        strategy_json_str = process_user_query(
            user_message=raw_content,
            collection_name="lorekeeper_memory",
            enable_jina=payload.enable_jina
        )
        
        # Load the structured JSON payload returned by gemini-1.5-flash and return it directly
        return json.loads(strategy_json_str)
        
    except Exception as e:
        logger.error(f"Failure in /discord-bot-receiver: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compile-strategy-alert", dependencies=[Security(verify_api_key)])
async def compile_strategy_alert(background_tasks: BackgroundTasks):
    """
    A secondary endpoint designed solely to trigger background data ingestion workflows.
    """
    try:
        logger.info("Trigger received on /compile-strategy-alert. Firing background ingestion tasks.")
        
        # Queue the ingestion routine to execute non-blocking asynchronously
        background_tasks.add_task(run_background_ingestion)
        
        return {
            "status": "success",
            "message": "Background data ingestion cycle triggered successfully."
        }

    except Exception as e:
        logger.error(f"Failure in /compile-strategy-alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks", dependencies=[Security(verify_api_key)])
async def get_notion_tasks():
    """
    Returns active tasks scraped directly from the connected Notion database.
    Provides a real-time read path for the frontend Notion Tasks Dashboard.
    """
    try:
        tasks = fetch_notion_data()
        return {"status": "success", "tasks": tasks}
    except Exception as e:
        logger.error(f"Failure fetching tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory", dependencies=[Security(verify_api_key)])
async def get_memory_explorer():
    """
    Retrieves indexed vectors and payloads from the Qdrant database using the scroll API.
    Used for the Knowledge Base Explorer transparency page.
    """
    try:
        results, next_page_offset = qdrant_client.scroll(
            collection_name="lorekeeper_memory",
            limit=50,
            with_payload=True,
            with_vectors=False
        )
        return {
            "status": "success", 
            "memory": [res.payload for res in results],
            "next_offset": next_page_offset
        }
    except Exception as e:
        logger.error(f"Failure reading from Qdrant: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", dependencies=[Security(verify_api_key)])
async def integration_health():
    """
    Lightweight ping to external integrations to determine up/down status and latency.
    """
    health_data = {}

    def ping_service(name, func, *args, **kwargs):
        start = time.perf_counter()
        try:
            func(*args, **kwargs)
            duration = round((time.perf_counter() - start) * 1000, 2)
            health_data[name] = {"status": "up", "latency_ms": duration}
        except Exception as e:
            duration = round((time.perf_counter() - start) * 1000, 2)
            health_data[name] = {"status": "down", "latency_ms": duration, "error": str(e)}

    # Ping Qdrant
    ping_service("qdrant", qdrant_client.get_collections)
    
    # Ping Notion
    notion_token = os.getenv("NOTION_TOKEN")
    def ping_notion():
        res = requests.get("https://api.notion.com/v1/users/me", headers={"Authorization": f"Bearer {notion_token}", "Notion-Version": "2022-06-28"}, timeout=5)
        res.raise_for_status()
    ping_service("notion", ping_notion)

    # Ping Tavily
    tavily_key = os.getenv("TAVILY_API_KEY")
    def ping_tavily():
        res = requests.post("https://api.tavily.com/search", json={"api_key": tavily_key, "query": "test"}, timeout=5)
        res.raise_for_status()
    ping_service("tavily", ping_tavily)

    # Ping Gemini
    def ping_gemini():
        genai_client.models.get_model('models/gemini-2.0-flash-lite')
    ping_service("gemini", ping_gemini)

    return health_data


# ------------------------------------------------------------------
# Server Initialization (Google Cloud Run Compatible)
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # Pull dynamic PORT environment variable assigned by Cloud Run, falling back to 8080 locally
    port = int(os.getenv("PORT", 8080))
    # Listen on host 0.0.0.0 to safely map external ingress traffic
    uvicorn.run("src.app:app", host="0.0.0.0", port=port, reload=False)

from dotenv import load_dotenv
import os

# Load variables from .env file
load_dotenv()

import json
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

# Inter-module imports
from src.agent import process_user_query
from src.ingestion import fetch_notion_data, fetch_google_tasks

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
# Request & Response Schemas
# ------------------------------------------------------------------
class DiscordWebhookPayload(BaseModel):
    content: str = Field(..., description="The text payload incoming from a Discord channel")
    author: Optional[str] = Field("unknown", description="Username of the message author")
    channel_id: Optional[str] = Field("unknown", description="ID of the Discord channel")


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
@app.post("/discord-bot-receiver")
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
            collection_name="lorekeeper_memory"
        )
        
        # Load the structured JSON payload returned by gemini-1.5-flash and return it directly
        return json.loads(strategy_json_str)
        
    except Exception as e:
        logger.error(f"Failure in /discord-bot-receiver: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compile-strategy-alert")
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


# ------------------------------------------------------------------
# Server Initialization (Google Cloud Run Compatible)
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # Pull dynamic PORT environment variable assigned by Cloud Run, falling back to 8080 locally
    port = int(os.getenv("PORT", 8080))
    # Listen on host 0.0.0.0 to safely map external ingress traffic
    uvicorn.run("src.app:app", host="0.0.0.0", port=port, reload=False)

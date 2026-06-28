import os
import re
import uuid
import logging
from typing import List, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from google import genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants for Embedding Generation
EMBEDDING_MODEL = 'gemini-embedding-2'
EMBEDDING_DIMENSION = 768  # Default output dimensionality for text-embedding-004


def chunk_markdown_text(text: str, max_chunk_size: int = 1500) -> List[str]:
    """
    Splits unstructured markdown text from Notion, Discord, or Google Tasks into logical chunks.
    Specifically engineered so headers or sub-tasks don't get awkwardly chopped in half.
    Falls back to splitting by paragraph (double newline) if a semantic block is too long.
    """
    if not text:
        return []
        
    # Split text into logical blocks by looking for markdown headings.
    # Positive lookahead `(?=#+ )` splits immediately BEFORE a heading starts.
    blocks = re.split(r'\n(?=#+ )', text)
    
    chunks = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
            
        # If the semantic block (Header + contents) is small enough, keep it unified
        if len(block) <= max_chunk_size:
            chunks.append(block)
        else:
            # Block is too large. Sub-split by double newlines to ensure bullet lists and sub-tasks
            # (which usually only have single newlines between them) stay grouped together.
            paragraphs = re.split(r'\n\s*\n', block)
            current_chunk = ""
            
            for p in paragraphs:
                p = p.strip()
                if not p:
                    continue
                # Aggregate paragraphs safely under the maximum threshold
                if len(current_chunk) + len(p) + 2 <= max_chunk_size:
                    current_chunk += ("\n\n" + p) if current_chunk else p
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = p
            
            if current_chunk:
                chunks.append(current_chunk)
                
    return chunks


def get_qdrant_client() -> QdrantClient:
    """
    Initializes and returns a connection to the remote Qdrant Cloud cluster.
    Requires QDRANT_URL and QDRANT_API_KEY from environment variables.
    """
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    
    if not qdrant_url or not qdrant_api_key:
        logger.warning("Missing QDRANT_URL or QDRANT_API_KEY. Remote vector DB operations may fail.")
        
    return QdrantClient(
        url=qdrant_url,
        api_key=qdrant_api_key,
        timeout=15.0  # Added timeout for production reliability
    )

# Establish singleton clients
qdrant_client = get_qdrant_client()

try:
    # Google GenAI SDK automatically utilizes the GEMINI_API_KEY env variable
    genai_client = genai.Client(http_options={'api_version': 'v1beta'})
except Exception as e:
    logger.warning(f"Could not initialize Google GenAI Client: {e}")
    genai_client = None


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Interacts with the official Google GenAI SDK to call text-embedding-004.
    Converts a list of text chunks into numerical vectors.
    """
    if not texts:
        return []
    if not genai_client:
        logger.error("GenAI client not initialized. Cannot generate embeddings.")
        return []

    try:
        response = genai_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=texts,
        )
        return [embedding.values for embedding in response.embeddings]
    except Exception as e:
        logger.error(f"Error calling Google GenAI {EMBEDDING_MODEL}: {e}")
        return []


def ensure_collection(collection_name: str, vector_size: int = EMBEDDING_DIMENSION):
    """
    Automated configuration check that spins up a collection inside Qdrant if it doesn't already exist.
    """
    try:
        if not qdrant_client.collection_exists(collection_name=collection_name):
            logger.info(f"Collection '{collection_name}' not found. Creating it...")
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE
                )
            )
            logger.info(f"Successfully created vector collection '{collection_name}'.")
    except Exception as e:
        logger.error(f"Error checking/creating Qdrant collection: {e}")


def upsert_records(collection_name: str, texts: List[str], metadata_list: List[Dict[str, Any]]):
    """
    Commits text chunks, vector arrays, and source metadata tags seamlessly into our cloud cluster.
    """
    if not texts:
        logger.info("No texts provided for upsert.")
        return
        
    if len(texts) != len(metadata_list):
        logger.error("Length mismatch between texts and metadata_list.")
        return

    # 1. Automated configuration check
    ensure_collection(collection_name)
    
    # 2. Call text-embedding-004 to convert chunks into vectors
    logger.info(f"Generating embeddings for {len(texts)} chunk(s)...")
    vectors = generate_embeddings(texts)
    
    if not vectors or len(vectors) != len(texts):
        logger.error("Failed to generate vectors for all chunks. Aborting upsert.")
        return
    
    # 3. Compile point structures dynamically
    points = []
    for text, vector, meta in zip(texts, vectors, metadata_list):
        point_id = str(uuid.uuid4())
        
        # Merge raw chunk text into the payload dictionary so it can be retrieved alongside the vectors
        payload = {"text": text}
        if meta:
            payload.update(meta)
            
        points.append(
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            )
        )
        
    # 4. Upsert payload bundle to the Qdrant cluster
    try:
        logger.info(f"Upserting {len(points)} records into Qdrant '{collection_name}'...")
        qdrant_client.upsert(
            collection_name=collection_name,
            points=points
        )
        logger.info("Upsert completed successfully.")
    except Exception as e:
        logger.error(f"Error upserting records to Qdrant: {e}")

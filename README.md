# LoreKeeper — Chief of Staff AI Agent

> Production-grade, highly autonomous RAG productivity agent. Enriches user queries with real-time web data and personal workspaces (Notion, Google Tasks), grounds it via vector memory, and uses Gemini 3.5 Flash to generate a **structured, validated, and actionable** strategy response.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg) ![FastAPI](https://img.shields.io/badge/FastAPI-0.135-teal.svg) ![Gemini](https://img.shields.io/badge/Gemini-3.5_Flash-orange.svg) ![Qdrant](https://img.shields.io/badge/Qdrant-RAG-red.svg) ![Cloud Run](https://img.shields.io/badge/GCP-Cloud_Run-blue.svg)

> Full deployment walkthrough: see [DEPLOYMENT.md](DEPLOYMENT.md).

## Architecture

```text
Frontend (HTML)  ──POST /discord-bot-receiver──▶  JSON Payload
      │
FastAPI Backend
      ├── Step 1 → Ingestion     Fetch Notion, Google Tasks, Tavily (Web), Jina AI
      ├── Step 2 → Qdrant DB     Chunk markdown, embed (gemini-embedding-2), top-5 RAG retrieval
      ├── Step 3 → Gemini 3.5    Inject context bundle into strict Chief of Staff prompt
      ├── Step 4 → JSON Parsing  Extract 'reply' string and 'action_items' array
      └── Step 5 → Output        Return strict JSON to Frontend / Discord Webhook
```

## Local Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/aasim0202/LoreKeeper.git
   cd LoreKeeper
   ```

2. **Install dependencies:**
   ```bash
   pip install --no-cache-dir -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file and securely inject your tokens:
   ```env
   GEMINI_API_KEY=your_key
   QDRANT_URL=your_qdrant_url
   QDRANT_API_KEY=your_qdrant_key
   NOTION_TOKEN=your_notion_token
   NOTION_DATABASE_ID=your_db_id
   TAVILY_API_KEY=your_tavily_key
   ```

4. **Start the API Server:**
   ```bash
   python -m src.app
   ```
   *(The server will start locally at `http://127.0.0.1:8080`)*

5. **Launch the UI:**
   Simply open `index.html` in your web browser to access your dashboard.

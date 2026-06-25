# 🌌 LoreKeeper 3.0: Chief of Staff AI Agent

LoreKeeper is a production-grade, highly autonomous RAG (Retrieval-Augmented Generation) productivity agent designed to serve as a digital "Chief of Staff". Powered by Google's **Gemini 3.5 Flash**, LoreKeeper ingests data from your active workspaces and orchestrates complex schedules, tasks, and strategy execution.

## 🚀 Key Features

- **Multi-Source Ingestion**: Automatically syncs and scrapes data from Notion databases, Google Tasks, Tavily (real-time web search), and Jina AI markdown scrapers.
- **Persistent Vector Memory**: Utilizes a Qdrant Cloud cluster and `gemini-embedding-2` models to semantically chunk and recall past context natively.
- **Strict JSON Intelligence**: Gemini is prompt-engineered to enforce strict JSON schemas, automatically generating action items and checklists instead of unstructured text walls.
- **Sleek Standalone UI**: Includes a custom-built, glassmorphism dark-mode HTML/JS frontend that interacts with the API and renders dynamic task lists.
- **Discord Bot Ready**: Exposes a `/discord-bot-receiver` endpoint specifically tailored for Discord webhook payloads.
- **Cloud Run Optimized**: Pre-configured with a lightweight `python:3.11-slim` Docker container and `cloudbuild.yaml` for instant serverless deployment on Google Cloud Run.

## 🛠️ Technology Stack
- **Backend Framework**: FastAPI & Uvicorn
- **AI Core**: Google GenAI SDK (Gemini 3.5 Flash)
- **Database**: Qdrant Vector Search
- **Deployment**: Google Cloud Build & Cloud Run
- **Frontend**: Vanilla HTML / CSS / JavaScript

## 📦 Local Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/aasim0202/LoreKeeper.git
   cd LoreKeeper
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
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
   Simply open `index.html` in your web browser to access your Chief of Staff dashboard!

## ☁️ Cloud Deployment

For detailed deployment instructions mapping to Google Cloud Run, refer to the included [DEPLOYMENT.md](DEPLOYMENT.md) guide.

---
*Architected and Built for the Vibe2Ship Hackathon.*

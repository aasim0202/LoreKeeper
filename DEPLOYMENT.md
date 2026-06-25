# Google Cloud Run Deployment Guide: LoreKeeper 3.0

This guide documents the step-by-step terminal commands using the `gcloud` CLI to build, containerize, and deploy your multi-source RAG agent to Google Cloud Run.

---

## Prerequisites
Ensure the Google Cloud SDK (`gcloud`) is installed on your Linux machine. If not, download it from [Google Cloud SDK docs](https://cloud.google.com/sdk/docs/install).

---

## Step 1: Authenticate and Set Up Your Project

Open your terminal and authenticate your Google account:
```bash
gcloud auth login
```

Set your active target GCP Project ID (replace `YOUR_PROJECT_ID` with your actual project identifier):
```bash
gcloud config set project YOUR_PROJECT_ID
```

Verify your active configuration:
```bash
gcloud config list
```

---

## Step 2: Enable Mandatory APIs

LoreKeeper requires Cloud Build to package the Docker image, Artifact Registry to store it, and Cloud Run to serve the API. Enable them via a single command:
```bash
gcloud services enable \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    run.googleapis.com
```

---

## Step 3: Create an Artifact Registry Repository

Create a Docker repository in your preferred GCP region (e.g., `us-central1`):
```bash
gcloud artifacts repositories create lorekeeper-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="Docker repository for LoreKeeper 3.0 container images"
```

---

## Step 4: Build and Submit Your Container Using Cloud Build

Compile your multi-stage Dockerfile and push it straight to Artifact Registry using Google's remote build workers. Run this from the root of your `lorekeeper` project directory:
```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/lorekeeper-repo/lorekeeper-app:latest .
```

---

## Step 5: Deploy to Google Cloud Run with Secure Parameters

Deploy the image to a public URL instance, injecting your API configurations as environment variables.

> [!IMPORTANT]
> Replace the placeholder credentials (`your_...`) below with your actual credentials before running the command, or inject secrets directly from Google Secret Manager for enterprise security.

```bash
gcloud run deploy lorekeeper-service \
    --image=us-central1-docker.pkg.dev/YOUR_PROJECT_ID/lorekeeper-repo/lorekeeper-app:latest \
    --platform=managed \
    --region=us-central1 \
    --allow-unauthenticated \
    --port=8080 \
    --set-env-vars="GEMINI_API_KEY=your_gemini_api_key,\
NOTION_TOKEN=your_notion_token,\
NOTION_DATABASE_ID=your_notion_database_id,\
TAVILY_API_KEY=your_tavily_api_key,\
QDRANT_URL=your_qdrant_url,\
QDRANT_API_KEY=your_qdrant_api_key,\
DISCORD_BOT_TOKEN=your_discord_bot_token,\
DISCORD_WEBHOOK_URL=your_discord_webhook_url"
```

### Options Explained:
* `--image`: The container location in your Artifact Registry.
* `--allow-unauthenticated`: Makes the FastAPI application accessible to public webhooks (like Discord webhook requests).
* `--port=8080`: Maps Cloud Run container ingress traffic to match the FastAPI uvicorn listener port.
* `--set-env-vars`: Securely injects environment variables into the runtime container.

---

## Step 6: Test Your Endpoints

Once the deployment finishes successfully, the CLI will output a Service URL resembling:
`https://lorekeeper-service-xxxxxx-uc.a.run.app`

Test the API receiver structure using `curl`:
```bash
curl -X POST "https://lorekeeper-service-xxxxxx-uc.a.run.app/discord-bot-receiver" \
     -H "Content-Type: application/json" \
     -d '{"content": "# Hackathon Deadline\nSubmission date is June 29, 2026.", "author": "dev-user", "channel_id": "main-channel"}'
```

# Google Cloud Run Deployment Guide: LoreKeeper 3.0

This guide documents the step-by-step terminal commands using the `gcloud` CLI to build, containerize, and deploy your full-stack RAG agent (backend and frontend assets) to Google Cloud Run.

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

---

## Step 2: Enable Mandatory APIs

LoreKeeper requires Cloud Build to package the Docker image and Cloud Run to serve the API. Enable them via a single command:
```bash
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com
```

---

## Step 3: Build and Deploy (Full-Stack Container)

We use a unified `cloudbuild.yaml` to build the Docker image (which now includes `index.html`, `app.js`, and `styles.css`) and push it to Google Container Registry (GCR). Then, we deploy it to Cloud Run.

Run this combined command from the root of your `lorekeeper` project directory:
```bash
# 1. Build and push the image via Cloud Build
gcloud builds submit 

# 2. Deploy to Cloud Run
gcloud run deploy lorekeeper-backend \
  --image gcr.io/YOUR_PROJECT_ID/lorekeeper-backend:latest \
  --port 8080 \
  --region us-central1 \
  --allow-unauthenticated
```

### Options Explained:
* `--image`: The container location in your GCR registry.
* `--allow-unauthenticated`: Makes the FastAPI application accessible to public webhooks (like Discord webhook requests) and allows users to load the UI.
* `--port=8080`: Maps Cloud Run container ingress traffic to match the FastAPI uvicorn listener port.

> [!IMPORTANT]
> **Environment Variables:** Once deployed, you must navigate to the **Google Cloud Console > Cloud Run > lorekeeper-backend > Edit & Deploy New Revision > Variables & Secrets** to securely inject your API keys (`GEMINI_API_KEY`, `QDRANT_API_KEY`, etc.) rather than passing them via CLI for maximum security.

---

## Step 4: Access Your Application

Once the deployment finishes successfully, the CLI will output a Service URL resembling:
`https://lorekeeper-backend-xxxxxx-uc.a.run.app`

1. **Web UI:** Simply visit that URL in your browser to access the Chief of Staff dashboard.
2. **Discord Receiver:** The webhook listener is located at `https://lorekeeper-backend-xxxxxx-uc.a.run.app/discord-bot-receiver`.

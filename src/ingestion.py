import os
import logging
import requests
from typing import List, Dict, Any, Optional

# Google API imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default timeout for network requests (in seconds) to prevent hanging
REQUEST_TIMEOUT = 15

def fetch_notion_data() -> List[Dict[str, Any]]:
    """
    Fetches rows from a Notion database where the Status is not 'Done'.
    Expects NOTION_TOKEN and NOTION_DATABASE_ID environment variables.
    """
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID", "61703c47-b568-4872-8cb7-1a5974edd14a")
    
    if not notion_token or not database_id:
        logger.error("Missing NOTION_TOKEN or NOTION_DATABASE_ID environment variables.")
        return []

    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # Filter out entries where Status is 'Done'
    payload = {
        "filter": {
            "property": "Status",
            "status": {
                "does_not_equal": "Done"
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except requests.exceptions.Timeout:
        logger.error("Network timeout while fetching Notion data.")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Network failure while fetching Notion data: {e}")
        return []


def write_notion_task(task_title: str, priority: str, deadline: str, action_plan: str, source_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Sends a POST request to Notion to create a new page in the database.
    """
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID", "61703c47-b568-4872-8cb7-1a5974edd14a")
    
    if not notion_token or not database_id:
        logger.error("Missing NOTION_TOKEN or NOTION_DATABASE_ID environment variables.")
        return None

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    properties = {
        "Task / Project": {"title": [{"text": {"content": task_title}}]},
        "Status": {"status": {"name": "Not started"}},
        "Priority": {"select": {"name": priority}},
        "AI Action Plan": {"rich_text": [{"text": {"content": action_plan}}]}
    }

    if deadline:
        properties["Deadline"] = {"date": {"start": deadline}}

    if source_url:
        properties["Source Link"] = {"url": source_url}

    payload = {
        "parent": {"database_id": database_id},
        "properties": properties
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error("Network timeout while writing to Notion.")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Network failure while writing to Notion: {e}")
        return None


def fetch_google_tasks() -> List[Dict[str, Any]]:
    """
    Fetches active lists and due dates from standard consumer Google Tasks.
    Relies on Google OAuth2 flow (credentials.json/token.json).
    """
    SCOPES = ['https://www.googleapis.com/auth/tasks.readonly']
    creds = None

    try:
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    logger.error("credentials.json missing. Cannot authenticate Google Tasks.")
                    return []
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        service = build('tasks', 'v1', credentials=creds)

        # Retrieves lists and limits to active status
        tasklists_result = service.tasklists().list(maxResults=10).execute()
        tasklists = tasklists_result.get('items', [])

        all_tasks = []
        for tasklist in tasklists:
            tasks_result = service.tasks().list(
                tasklist=tasklist['id'], 
                showHidden=False
            ).execute()
            
            tasks = tasks_result.get('items', [])
            for task in tasks:
                if task.get('status') != 'completed':
                    all_tasks.append({
                        "list_name": tasklist['title'],
                        "task_title": task.get('title'),
                        "due": task.get('due'),
                        "status": task.get('status'),
                        "updated": task.get('updated')
                    })
        
        return all_tasks
    except Exception as e:
        logger.error(f"Error fetching Google Tasks: {e}")
        return []


def scrape_with_jina(url: str) -> str:
    """
    Scrapes a target URL using Jina's public proxy and returns clean Markdown.
    """
    if not url:
        return ""
        
    jina_url = f"https://r.jina.ai/{url}"
    
    try:
        response = requests.get(jina_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout:
        logger.error(f"Network timeout while scraping {url} with Jina.")
        return ""
    except requests.exceptions.RequestException as e:
        logger.error(f"Network failure while scraping {url} with Jina: {e}")
        return ""


def fetch_tavily_context(query: str) -> Dict[str, Any]:
    """
    Fetches an AI-ready answer snippet from Tavily search endpoint.
    Expects TAVILY_API_KEY environment variable.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.error("Missing TAVILY_API_KEY environment variable.")
        return {}

    url = "https://api.tavily.com/search"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "api_key": api_key,
        "query": query,
        "include_answer": True,
        "search_depth": "basic"
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error("Network timeout while fetching Tavily context.")
        return {}
    except requests.exceptions.RequestException as e:
        logger.error(f"Network failure while fetching Tavily context: {e}")
        return {}
if __name__ == "__main__":
    print("🔄 Starting local authentication check...")
    import os
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    SCOPES = ['https://www.googleapis.com/auth/tasks.readonly']
    creds = None

    if os.path.exists('token.json'):
        print("Found existing token.json!")
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            print("🔑 Opening browser for Google login. Look for a popup window or link below!")
            # run_local_server(port=0) opens a browser. If it hangs, look at the console.
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            print("✅ Success! token.json has been created in your root folder.")
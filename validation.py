import google.auth
import google_auth_oauthlib.flow
import google.auth.transport.requests
import os

# Step 1: Load the client secrets file
CLIENT_SECRETS_FILE = "client_secret.json"

# Step 2: Define the scope (YouTube Data API v3)
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

def get_authenticated_service():
    # The 'run_local_server()' method is used to authenticate with a local web server.
    
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    credentials = flow.run_local_server(port=8080, prompt="consent")

# Get the authenticated service (run this once to get access token)
credentials = get_authenticated_service()

"""
One-time OAuth2 setup script for YouTube API.

Usage (run locally, NOT in CI):
    python -m scripts.auth_youtube

This opens a browser window for Google OAuth consent.
After authorizing, it prints the refresh token.
Save the token as YOUTUBE_REFRESH_TOKEN in your GitHub Secrets.

IMPORTANT: Your Google Cloud OAuth consent screen must be "Published"
(not "Testing"), otherwise the refresh token expires after 7 days.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    print("=" * 60)
    print("  YouTube OAuth2 Setup — One-Time Authorization")
    print("=" * 60)
    print()
    print("This will open a browser window for Google OAuth consent.")
    print("Make sure you've already:")
    print("  1. Created a project in Google Cloud Console")
    print("  2. Enabled YouTube Data API v3")
    print("  3. Created an OAuth 2.0 Client ID (Desktop app)")
    print("  4. Published the OAuth consent screen (NOT 'Testing')")
    print()

    client_id = input("Enter your OAuth Client ID: ").strip()
    client_secret = input("Enter your OAuth Client Secret: ").strip()

    if not client_id or not client_secret:
        print("Error: Client ID and Secret are required.")
        return

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print("\nOpening browser for authorization...")
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=8080, prompt="consent")

    print()
    print("=" * 60)
    print("  ✅  Authorization Successful!")
    print("=" * 60)
    print()
    print("Add these as GitHub Secrets (Settings → Secrets → Actions):")
    print()
    print(f"  YOUTUBE_CLIENT_ID       = {client_id}")
    print(f"  YOUTUBE_CLIENT_SECRET   = {client_secret}")
    print(f"  YOUTUBE_REFRESH_TOKEN   = {credentials.refresh_token}")
    print()
    print("=" * 60)
    print()
    print("REMINDER: Make sure your OAuth consent screen is 'Published'")
    print("(not 'Testing'), otherwise the refresh token expires in 7 days.")


if __name__ == "__main__":
    main()

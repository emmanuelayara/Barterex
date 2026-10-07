"""
One-time helper: generate a YOUTUBE_REFRESH_TOKEN for the official Barterex
YouTube channel.

Prerequisites (do this in Google Cloud Console first):
    1. Create/select a project, enable the "YouTube Data API v3".
    2. Create an OAuth 2.0 Client ID of type "Desktop app".
    3. Download its client secret JSON (or just note the Client ID/Secret).

Run this script on a machine with a browser, and sign in with the GOOGLE
ACCOUNT THAT OWNS THE OFFICIAL CHANNEL when prompted (not your personal admin
account, unless that's the same account):

    python get_youtube_refresh_token.py

It prints a refresh token at the end - put it in your .env as:
    YOUTUBE_CLIENT_ID=...
    YOUTUBE_CLIENT_SECRET=...
    YOUTUBE_REFRESH_TOKEN=...   <- printed by this script

This token does not expire unless revoked, so you only need to run this once.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']


def main():
    client_id = input('YouTube OAuth Client ID: ').strip()
    client_secret = input('YouTube OAuth Client Secret: ').strip()

    client_config = {
        'installed': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': ['http://localhost'],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0)

    print('\nSuccess! Add these to your .env:\n')
    print(f'YOUTUBE_CLIENT_ID={client_id}')
    print(f'YOUTUBE_CLIENT_SECRET={client_secret}')
    print(f'YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}')


if __name__ == '__main__':
    main()

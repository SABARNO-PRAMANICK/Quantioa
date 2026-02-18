
"""
Manual helper script to verify Zerodha login flow.

Run this script to generate the login URL and exchange the request token
for an access token.
"""
import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from quantioa.broker.zerodha_auth import ZerodhaOAuth2
from quantioa.config import settings

def main():
    print("=== Zerodha Authentication Helper ===")
    
    if not settings.zerodha_api_key:
        print("Error: ZERODHA_API_KEY not set in environment/config.")
        return

    auth = ZerodhaOAuth2()
    url = auth.get_authorization_url()
    
    print(f"\n1. Visit this URL to login:\n{url}\n")
    print("2. After login, you will be redirected to the callback URL.")
    print("3. Copy the 'request_token' parameter from the URL.")
    
    request_token = input("\nEnter request_token: ").strip()
    
    if request_token:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            print("\nExchanging token...")
            token = loop.run_until_complete(auth.exchange_token(request_token))
            print(f"Success! Access Token: {token.access_token}")
            if token.public_token:
                print(f"Public Token: {token.public_token}")
            print(f"Expires At: {token.expires_at}")
        except Exception as e:
            print(f"Error exchanging token: {e}")
        finally:
            loop.close()

if __name__ == "__main__":
    main()

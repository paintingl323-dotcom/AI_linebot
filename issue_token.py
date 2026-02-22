
import requests

channel_id = "2008936542"
channel_secret = "34c3de84fc4bc02ba8ef5bed8daf5439"

url = "https://api.line.me/v2/oauth/accessToken"
headers = {"Content-Type": "application/x-www-form-urlencoded"}
data = {
    "grant_type": "client_credentials",
    "client_id": channel_id,
    "client_secret": channel_secret
}

try:
    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    token_info = response.json()
    print("SUCCESS! New Access Token:")
    print(token_info['access_token'])
except Exception as e:
    print(f"Error issuing token: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(e.response.text)

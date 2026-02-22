
import requests
import json

token = "DrrrnpGl2KajfmVU0U1UMsJlgxrrSVF7uAA2wxgZqyPZskmmF4zrz+HGyr3qPOOsEMG2bDrX+E6pUY4Scq2ESzBVH+XoNpKfSkUMrmC874w2qpyaRI8N0fvPobBbNkPaH4huL9yDT7wgtwvU3C+dMAdB04t89/1O/w1cDnyilFU="
headers = {
    "Authorization": f"Bearer {token}"
}

try:
    response = requests.get("https://api.line.me/v2/bot/info", headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

import os
import sys

# Manual .env loader to avoid installing python-dotenv (reducing confirmation steps)
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    print(f"Loading environment from {env_path}")
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

from app import app

# This is the entry point for the application
# The actual app is initialized in app.py

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
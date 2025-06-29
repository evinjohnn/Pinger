

import os
import time
import requests
from flask import Flask, request, jsonify, send_from_directory
import redis


redis_url = os.environ.get('REDIS_URL')

# --- Check if the REDIS_URL exists ---
if not redis_url:
    print("--- [LOCAL DEV MODE] ---")
    print("--- REDIS_URL env var not found. Using in-memory MockKV. ---")
    
    class MockKV:
        def __init__(self):
            self._data = set()
        def sadd(self, key, *values):
            for value in values: self._data.add(value)
            print(f"[MockDB] Added '{values}'. Current data: {self._data}")
            return len(values)
        def smembers(self, key):
            print(f"[MockDB] Retrieving data. Current data: {self._data}")
            return self._data
            
    kv = MockKV()

else:
    # --- Connect to your Redis database using the single REDIS_URL ---
    print("--- [PRODUCTION MODE] REDIS_URL found. Connecting to Redis. ---")
    kv = redis.Redis.from_url(redis_url)



app = Flask(__name__, static_folder='../public', static_url_path='')

@app.route('/')
def serve_index():
    static_folder = app.static_folder or '../public'
    return send_from_directory(static_folder, 'index.html')

@app.route('/api/add-url', methods=['POST'])
def add_url():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "URL not provided"}), 400

    url_to_add = data['url']
    if not url_to_add.startswith(('http://', 'https://')):
        return jsonify({"error": "Invalid URL format"}), 400
    
    try:
        kv.sadd("urls_to_ping", url_to_add)
        return jsonify({"message": f"URL '{url_to_add}' added successfully."}), 200
    except Exception as e:
        print(f"Error adding URL: {e}")
        return jsonify({"error": "Could not save URL."}), 500

@app.route('/api/ping-all', methods=['GET'])
def ping_all():
    auth_header = request.headers.get('Authorization')
    cron_secret = os.environ.get('CRON_SECRET')

    if cron_secret and (not auth_header or auth_header != f"Bearer {cron_secret}"):
        print("Unauthorized attempt to access /api/ping-all")
        return "Unauthorized", 401

    try:
        # The smembers command returns bytes, so we need to decode them
        urls_bytes = kv.smembers("urls_to_ping")
        urls = {url.decode('utf-8') for url in urls_bytes}

        if not urls:
            print("No URLs to ping.")
            return jsonify({"message": "No URLs to ping."}), 200

        print(f"--- Pinging {len(urls)} URLs at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        ping_results = {}
        for url in urls:
            try:
                response = requests.get(url, timeout=10)
                status = response.status_code
                print(f"Pinged {url}: Status {status}")
                ping_results[url] = {"status": status, "timestamp": time.time()}
            except requests.RequestException as e:
                print(f"Failed to ping {url}: {e}")
                ping_results[url] = {"status": "Error", "error_message": str(e)}

        print("--- Ping cycle complete ---")
        return jsonify({"status": "success", "results": ping_results}), 200

    except Exception as e:
        print(f"An error occurred during the ping cycle: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)
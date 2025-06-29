
import os
import time
import requests
from flask import Flask, request, jsonify, send_from_directory



vercel_kv_url = os.environ.get('VERCEL_KV_URL')
vercel_kv_rest_api_url = os.environ.get('VERCEL_KV_REST_API_URL')
vercel_kv_rest_api_token = os.environ.get('VERCEL_KV_REST_API_TOKEN')

if not all([vercel_kv_url, vercel_kv_rest_api_url, vercel_kv_rest_api_token]):
    print("--- [LOCAL DEV MODE] ---")
    print("--- Vercel KV env vars not found. Using in-memory MockKV. ---")
    print("--- Data will be lost on server restart. ---")
    
    
    class MockKV:
        def __init__(self):
            # We'll just use a simple Python set to store URLs
            self._data = set()

        def sadd(self, key, value):
            # Mimics the Redis 'sadd' command
            self._data.add(value)
            print(f"[MockDB] Added '{value}'. Current data: {self._data}")
            return 1

        def smembers(self, key):
            # Mimics the Redis 'smembers' command
            print(f"[MockDB] Retrieving data. Current data: {self._data}")
            return self._data
            
    # Create an instance of our fake database
    kv = MockKV()

else:
    # This block runs ONLY when deployed on Vercel
    print("--- [PRODUCTION MODE] Vercel KV env vars found. ---")
    from vercel_kv import KV
    kv = KV()

# --- END: Mocking & Real KV Logic ---


# Point Flask to the 'public' folder for static files
app = Flask(__name__, static_folder='../public', static_url_path='')

# Route to serve your index.html from the 'public' folder
@app.route('/')
def serve_index():
    static_folder = app.static_folder or '../public'
    return send_from_directory(static_folder, 'index.html')

# API Endpoint for users to add a new URL
@app.route('/api/add-url', methods=['POST'])
def add_url():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "URL not provided"}), 400

    url_to_add = data['url']
    if not url_to_add.startswith(('http://', 'https://')):
        return jsonify({"error": "Invalid URL format"}), 400
    
    try:
        kv.sadd("urls_to_ping", url_to_add)  # type: ignore
        return jsonify({"message": f"URL '{url_to_add}' added successfully."}), 200
    except Exception as e:
        print(f"Error adding URL: {e}")
        return jsonify({"error": "Could not save URL."}), 500


# API Endpoint that the Cron Job will trigger
@app.route('/api/ping-all', methods=['GET'])
def ping_all():
    auth_header = request.headers.get('Authorization')
    cron_secret = os.environ.get('CRON_SECRET')

    if cron_secret and (not auth_header or auth_header != f"Bearer {cron_secret}"):
        print("Unauthorized attempt to access /api/ping-all")
        return "Unauthorized", 401

    try:
        urls = kv.smembers("urls_to_ping")   # type: ignore
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


# This block is only for local development
if __name__ == "__main__":
    app.run(debug=True, port=5001)
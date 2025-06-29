import os
import time
import requests
from flask import Flask, request, jsonify
from vercel_kv import KV

app = Flask(__name__)

# Initialize KV store
kv = KV()

# A simple health check route
@app.route('/')
def home():
    return "Pinger service is alive!"

# API Endpoint for users to add a new URL
@app.route('/api/add-url', methods=['POST'])
def add_url():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "URL not provided"}), 400

    url_to_add = data['url']

    # Basic validation (you can add more complex checks)
    if not url_to_add.startswith(('http://', 'https://')):
        return jsonify({"error": "Invalid URL format"}), 400
    
    try:
        # We use a Redis 'SET' to automatically handle duplicates.
        # 'sadd' adds the item to the set. If it's already there, it does nothing.
        kv.sadd("urls_to_ping", url_to_add)
        print(f"Added URL to the set: {url_to_add}")
        return jsonify({"message": f"URL '{url_to_add}' added successfully."}), 200
    except Exception as e:
        print(f"Error adding URL to KV store: {e}")
        return jsonify({"error": "Could not save URL."}), 500


# API Endpoint that the Cron Job will trigger
@app.route('/api/ping-all', methods=['GET'])
def ping_all():
    # A simple security check to prevent unauthorized triggers, 
    # Vercel will send this header for its cron jobs.
    auth_header = request.headers.get('Authorization')
    if not auth_header or auth_header != f"Bearer {os.environ.get('CRON_SECRET')}":
        return "Unauthorized", 401

    try:
        # 'smembers' gets all items from the set
        urls = kv.smembers("urls_to_ping")
        if not urls:
            print("No URLs to ping.")
            return jsonify({"message": "No URLs to ping."}), 200

        print(f"--- Pinging {len(urls)} URLs at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        ping_results = {}
        for url in urls:
            try:
                # We add a timeout to prevent the function from hanging
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

# This is for local development if you want to test it
if __name__ == "__main__":
    app.run(debug=True)
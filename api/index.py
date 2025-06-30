import os
import time
import requests
from flask import Flask, request, jsonify, send_from_directory
import redis

redis_url = os.environ.get('REDIS_URL')

# --- Rate Limiting Constants ---
RATE_LIMIT_COUNT = 10  # Max requests
RATE_LIMIT_WINDOW = 3600  # In seconds (1 hour)

# --- Database Connection ---
if not redis_url:
    print("--- [LOCAL DEV MODE] ---")
    print("--- REDIS_URL env var not found. Using in-memory MockKV. ---")
    
    class MockKV:
        def __init__(self):
            self._data = set()
            self._rate_limit = {}
        def sadd(self, key, *values):
            added_count = 0
            for value in values:
                if value not in self._data:
                    self._data.add(value)
                    added_count += 1
            print(f"[MockDB] Added '{values}'. Current data: {self._data}")
            return added_count
        def srem(self, key, value):
            if value in self._data:
                self._data.remove(value)
                print(f"[MockDB] Removed '{value}'. Current data: {self._data}")
                return 1
            return 0
        def smembers(self, key):
            print(f"[MockDB] Retrieving data. Current data: {self._data}")
            return self._data
        def incr(self, key):
            self._rate_limit[key] = self._rate_limit.get(key, 0) + 1
            return self._rate_limit[key]
        def expire(self, key, seconds):
            # Mock expire is not really needed for this logic
            pass
            
    kv = MockKV()

else:
    print("--- [PRODUCTION MODE] REDIS_URL found. Connecting to Redis. ---")
    kv = redis.Redis.from_url(redis_url)

app = Flask(__name__, static_folder='../public', static_url_path='')

def is_rate_limited(ip_address):
    """Checks if an IP address is rate-limited."""
    if not ip_address:
        return False # Don't rate limit if IP is not found
    
    key = f"rate_limit:{ip_address}"
    
    try:
        # Use a pipeline for atomic operations
        pipe = kv.pipeline()
        pipe.incr(key)
        pipe.expire(key, RATE_LIMIT_WINDOW, nx=True) # Set expiry only if key is new
        current_count, _ = pipe.execute()

        if int(current_count) > RATE_LIMIT_COUNT:
            print(f"Rate limit exceeded for IP: {ip_address}")
            return True
        return False
    except Exception as e:
        print(f"Rate limiting error: {e}")
        return False # Fail open in case of error

@app.route('/')
def serve_index():
    static_folder = app.static_folder or '../public'
    return send_from_directory(static_folder, 'index.html')

@app.route('/api/add-url', methods=['POST'])
def add_url():
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if is_rate_limited(ip_address):
        return jsonify({"error": "You are sending too many requests. Please wait a moment."}), 429

    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "URL not provided"}), 400

    url_to_add = data['url'].strip()
    if not url_to_add.startswith(('http://', 'https://')):
        return jsonify({"error": "Invalid URL format. Must start with http:// or https://"}), 400
    
    try:
        added_count = kv.sadd("urls_to_ping", url_to_add)
        if added_count > 0:
            return jsonify({"message": f"URL '{url_to_add}' added successfully!"}), 200
        else:
            return jsonify({"message": f"URL is already being monitored."}), 200
    except Exception as e:
        print(f"Error adding URL: {e}")
        return jsonify({"error": "Could not save URL."}), 500

@app.route('/api/remove-url', methods=['POST'])
def remove_url():
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if is_rate_limited(ip_address):
        return jsonify({"error": "You are sending too many requests. Please wait a moment."}), 429

    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({"error": "URL not provided"}), 400

    url_to_remove = data['url'].strip()
    if not url_to_remove.startswith(('http://', 'https://')):
        return jsonify({"error": "Invalid URL format"}), 400
        
    try:
        removed_count = kv.srem("urls_to_ping", url_to_remove)
        if removed_count > 0:
            return jsonify({"message": f"URL '{url_to_remove}' has been removed."}), 200
        else:
            return jsonify({"error": "URL not found in the monitoring list."}), 404
    except Exception as e:
        print(f"Error removing URL: {e}")
        return jsonify({"error": "Could not remove URL."}), 500

@app.route('/api/ping-all', methods=['GET'])
def ping_all():
    auth_header = request.headers.get('Authorization')
    cron_secret = os.environ.get('CRON_SECRET')

    if cron_secret and (not auth_header or auth_header != f"Bearer {cron_secret}"):
        print("Unauthorized attempt to access /api/ping-all")
        return "Unauthorized", 401

    try:
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
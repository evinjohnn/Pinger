import os
import time
import requests
import redis
import asyncio 
import aiohttp
import secrets
from flask import Flask, request, jsonify, send_from_directory
from collections.abc import Awaitable

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
            self._hashes = {}  # For hash storage
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
        def expire(self, key, seconds, **kwargs):
            # Mock expire is not really needed for this logic
            pass
        # --- Hash methods for mock Redis hash ---
        def hset(self, name, key, value):
            if name not in self._hashes:
                self._hashes[name] = {}
            self._hashes[name][key] = value
            print(f"[MockDB] hset: {name}[{key}] = {value}")
            return 1
        def hget(self, name, key):
            value = self._hashes.get(name, {}).get(key)
            print(f"[MockDB] hget: {name}[{key}] -> {value}")
            if value is not None:
                return value.encode('utf-8') if isinstance(value, str) else value
            return None
        def hdel(self, name, key):
            if name in self._hashes and key in self._hashes[name]:
                del self._hashes[name][key]
                print(f"[MockDB] hdel: {name}[{key}] deleted")
                return 1
            return 0
        def hkeys(self, name):
            keys = list(self._hashes.get(name, {}).keys())
            print(f"[MockDB] hkeys: {name} -> {keys}")
            return [k.encode('utf-8') if isinstance(k, str) else k for k in keys]
        def hexists(self, name, key):
            exists = key in self._hashes.get(name, {})
            print(f"[MockDB] hexists: {name}[{key}] -> {exists}")
            return exists
        def pipeline(self):
            # A minimal mock pipeline
            class MockPipeline:
                def __init__(self, parent):
                    self._parent = parent
                    self._commands = []
                def incr(self, key):
                    self._commands.append(('incr', key))
                def expire(self, key, seconds, nx=False):
                    self._commands.append(('expire', key, seconds))
                def execute(self):
                    results = []
                    for cmd in self._commands:
                        if cmd[0] == 'incr':
                            results.append(self._parent.incr(cmd[1]))
                        elif cmd[0] == 'expire':
                            results.append(self._parent.expire(cmd[1], cmd[2]))
                    return results
            return MockPipeline(self)
            
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
        pipe = kv.pipeline()
        pipe.incr(key)
        pipe.expire(key, RATE_LIMIT_WINDOW, nx=True)
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

def generate_removal_key():
    """Generates a secure, URL-safe random token."""
    return secrets.token_hex(8)

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
        if kv.hexists("monitored_urls", url_to_add):
            return jsonify({"message": "URL is already being monitored."}), 200

        removal_key = generate_removal_key()
        kv.hset("monitored_urls", url_to_add, removal_key)

        print(f"Added URL: {url_to_add} with key: {removal_key}")
        
        return jsonify({
            "message": f"URL '{url_to_add}' added successfully!",
            "removal_key": removal_key
        }), 200
        
    except Exception as e:
        print(f"Error adding URL: {e}")
        return jsonify({"error": "Could not save URL."}), 500

@app.route('/api/remove-url', methods=['POST'])
def remove_url():
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if is_rate_limited(ip_address):
        return jsonify({"error": "You are sending too many requests. Please wait a moment."}), 429

    data = request.get_json()
    if not data or 'url' not in data or 'removal_key' not in data:
        return jsonify({"error": "URL and removal_key must be provided"}), 400

    url_to_remove = data['url'].strip()
    key_provided = data['removal_key'].strip()

    try:
        stored_key_bytes = kv.hget("monitored_urls", url_to_remove)
        
        if stored_key_bytes:
            stored_key_decoded = stored_key_bytes.decode('utf-8')
            if stored_key_decoded == key_provided:
                kv.hdel("monitored_urls", url_to_remove)
                return jsonify({"message": f"URL '{url_to_remove}' has been removed."}), 200
            else:
                return jsonify({"error": "Invalid removal key for the given URL."}), 403
        else:
            return jsonify({"error": "URL not found in the monitoring list."}), 404
            
    except Exception as e:
        print(f"Error removing URL: {e}")
        return jsonify({"error": "Could not remove URL."}), 500

async def ping_one_url(session, url):
    """Asynchronously pings a single URL and returns the result."""
    try:
        async with session.get(url, timeout=10) as response:
            status = response.status
            print(f"Pinged {url}: Status {status}")
            return (url, {"status": status, "timestamp": time.time()})
    except Exception as e:
        print(f"Failed to ping {url}: {e}")
        return (url, {"status": "Error", "error_message": str(e)})

@app.route('/api/ping-all', methods=['GET'])
async def ping_all():
    auth_header = request.headers.get('Authorization')
    cron_secret = os.environ.get('CRON_SECRET')

    if cron_secret and (not auth_header or auth_header != f"Bearer {cron_secret}"):
        print("Unauthorized attempt to access /api/ping-all")
        return "Unauthorized", 401

    try:
        urls_bytes = kv.hkeys("monitored_urls")
        urls = {url.decode('utf-8') for url in urls_bytes}

        if not urls:
            print("No URLs to ping.")
            return jsonify({"message": "No URLs to ping."}), 200

        print(f"--- Concurrently pinging {len(urls)} URLs at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        async with aiohttp.ClientSession() as session:
            tasks = [ping_one_url(session, url) for url in urls]
            results = await asyncio.gather(*tasks)
        
        ping_results = {url: result for url, result in results}

        print("--- Ping cycle complete ---")
        return jsonify({"status": "success", "results": ping_results}), 200

    except Exception as e:
        print(f"An error occurred during the ping cycle: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)

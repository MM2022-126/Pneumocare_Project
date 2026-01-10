"""
Simple Python Load Balancer for PneumoCare
Distributes requests across multiple Flask backend instances
"""

from flask import Flask, request, jsonify, redirect
import requests
import threading
import time
from collections import deque
from datetime import datetime
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Get configuration from environment or command line
LOAD_BALANCER_PORT = int(os.environ.get('LOAD_BALANCER_PORT', 8080))
NUM_INSTANCES = int(os.environ.get('NUM_INSTANCES', 3))

class LoadBalancer:
    """Round-robin load balancer with health checking"""
    
    def __init__(self, backends):
        """
        Args:
            backends: List of dicts with 'url' and 'port' keys
        """
        self.backends = backends
        self.current_idx = 0
        self.health_status = {b['url']: True for b in backends}
        self.lock = threading.Lock()
        self.request_log = deque(maxlen=1000)
        self.start_health_check()
    
    def start_health_check(self):
        """Background thread to check backend health every 10 seconds"""
        def health_check():
            while True:
                time.sleep(10)
                for backend in self.backends:
                    try:
                        resp = requests.get(f"{backend['url']}/health", timeout=5)
                        self.health_status[backend['url']] = resp.status_code == 200
                        logger.info(f"✓ {backend['url']} is healthy")
                    except Exception as e:
                        self.health_status[backend['url']] = False
                        logger.warning(f"✗ {backend['url']} is DOWN: {e}")
        
        thread = threading.Thread(target=health_check, daemon=True)
        thread.start()
    
    def get_next_backend(self):
        """Get next healthy backend using round-robin"""
        with self.lock:
            healthy_backends = [
                b for b in self.backends 
                if self.health_status[b['url']]
            ]
            
            if not healthy_backends:
                logger.error("[!] No healthy backends available!")
                return None
            
            self.current_idx = (self.current_idx + 1) % len(healthy_backends)
            return healthy_backends[self.current_idx]
    
    def log_request(self, backend_url, path, status):
        """Log request for monitoring"""
        self.request_log.append({
            'timestamp': datetime.now().isoformat(),
            'backend': backend_url,
            'path': path,
            'status': status
        })
    
    def get_stats(self):
        """Return load balancer statistics"""
        total_requests = len(self.request_log)
        backend_counts = {}
        for log_entry in self.request_log:
            url = log_entry['backend']
            backend_counts[url] = backend_counts.get(url, 0) + 1
        
        return {
            'total_requests': total_requests,
            'requests_per_backend': backend_counts,
            'health_status': self.health_status,
            'healthy_count': sum(1 for v in self.health_status.values() if v),
            'total_backends': len(self.backends)
        }


# Initialize load balancer with dynamic backends
BACKENDS = [
    {'url': f'http://localhost:{5000+i}', 'port': 5000+i}
    for i in range(1, NUM_INSTANCES + 1)
]

lb = LoadBalancer(BACKENDS)


@app.route('/health', methods=['GET'])
def health():
    """Health check for this load balancer"""
    healthy_count = sum(1 for v in lb.health_status.values() if v)
    status = 'healthy' if healthy_count > 0 else 'unhealthy'
    return jsonify({'status': status, 'healthy_backends': healthy_count})


@app.route('/stats', methods=['GET'])
def stats():
    """Get load balancer statistics"""
    return jsonify(lb.get_stats())


@app.route('/predict', methods=['POST'])
def predict():
    """Route prediction requests to a backend"""
    backend = lb.get_next_backend()
    
    if not backend:
        lb.log_request('none', '/predict', 503)
        return jsonify({'error': 'No healthy backends available'}), 503
    
    try:
        # Forward the request to the backend
        files = request.files.getlist('image')
        data = request.form.to_dict()
        
        resp = requests.post(
            f"{backend['url']}/predict",
            files=[(f, f.stream) for f in files],
            data=data,
            timeout=90
        )
        
        lb.log_request(backend['url'], '/predict', resp.status_code)
        return jsonify(resp.json()), resp.status_code
    
    except Exception as e:
        logger.error(f"Error forwarding to {backend['url']}: {e}")
        lb.log_request(backend['url'], '/predict', 500)
        return jsonify({'error': str(e)}), 500


@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def forward_request(path):
    """Forward other requests to a backend"""
    backend = lb.get_next_backend()
    
    if not backend:
        return jsonify({'error': 'No healthy backends available'}), 503
    
    try:
        backend_url = f"{backend['url']}/{path}"
        
        # For GET requests with images, serve from backend
        if request.method == 'GET':
            resp = requests.get(backend_url, timeout=30)
            lb.log_request(backend['url'], f'/{path}', resp.status_code)
            
            if resp.headers.get('content-type', '').startswith('image'):
                return resp.content, resp.status_code, resp.headers
            return jsonify(resp.json()), resp.status_code
        
        # For other methods
        resp = requests.request(
            request.method,
            backend_url,
            json=request.get_json(silent=True),
            data=request.get_data(),
            headers=request.headers,
            timeout=30
        )
        lb.log_request(backend['url'], f'/{path}', resp.status_code)
        return resp.content, resp.status_code, resp.headers
    
    except Exception as e:
        logger.error(f"Error forwarding to {backend['url']}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/', methods=['GET'])
def index():
    """Redirect to first healthy backend"""
    backend = lb.get_next_backend()
    if backend:
        return redirect(f"{backend['url']}/")
    return jsonify({'error': 'No healthy backends'}), 503


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("PneumoCare Load Balancer Starting")
    logger.info("=" * 60)
    logger.info(f"Backends: {[b['url'] for b in BACKENDS]}")
    logger.info(f"Listening on http://localhost:{LOAD_BALANCER_PORT}")
    logger.info(f"Admin: http://localhost:{LOAD_BALANCER_PORT}/stats")
    logger.info("=" * 60)
    
    # Use waitress for production (no debug mode)
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=LOAD_BALANCER_PORT, threads=8, _quiet=True)
    except ImportError:
        app.run(host='0.0.0.0', port=LOAD_BALANCER_PORT, debug=False)

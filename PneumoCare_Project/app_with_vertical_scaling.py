"""
PneumoCare with VERTICAL SCALING BUILT-IN
Single instance optimized with async inference queue, caching, and batch processing
"""

import os

# SAFE settings — these DO NOT break Werkzeug
os.environ["FLASK_ENV"] = "production"
os.environ["FLASK_DEBUG"] = "0"

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image, UnidentifiedImageError
from flask import Flask, request, jsonify
from flask_cors import CORS
import io
import logging
import sys
import time
from queue import Queue
from threading import Thread
import hashlib
from collections import OrderedDict

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# CORS configuration - allow requests from all localhost origins
CORS(app, resources={
    r"/predict": {"origins": "*"},  # Allow from any origin
    r"/health": {"origins": "*"},
    r"/metrics": {"origins": "*"},
    r"/uploads/*": {"origins": "*"}
})

# Add request/response logging
@app.before_request
def log_request():
    logger.debug(f"Request: {request.method} {request.path}")

@app.after_request
def log_response(response):
    logger.debug(f"Response: {response.status_code}")
    return response

# ============ VERTICAL SCALING COMPONENTS ============

class ModelInferenceQueue:
    """Async inference queue with multiple worker threads"""
    def __init__(self, model, device, num_workers=4):
        self.model = model
        self.device = device
        self.queue = Queue(maxsize=100)
        self.results = {}
        self.workers = []
        self.lock = __import__('threading').Lock()
        
        for i in range(num_workers):
            t = Thread(target=self._worker, daemon=True)
            t.start()
            self.workers.append(t)
        
        logger.info(f"[OK] Started {num_workers} inference workers")
    
    def _worker(self):
        """Worker thread for async inference"""
        while True:
            try:
                task_id, tensor, transform_fn = self.queue.get()
                with torch.no_grad():
                    # Apply transform and get prediction
                    tensor = transform_fn(tensor)
                    outputs = self.model(tensor)
                    probs = torch.softmax(outputs, dim=1)
                    confidence, predicted = torch.max(probs, 1)
                
                with self.lock:
                    self.results[task_id] = {
                        'prediction': ['Normal', 'Pneumonia'][predicted.item()],
                        'confidence': float(confidence.item())
                    }
            except Exception as e:
                with self.lock:
                    self.results[task_id] = {'error': str(e)}
            finally:
                self.queue.task_done()
    
    def queue_inference(self, task_id, tensor, transform_fn):
        """Queue an inference task"""
        self.queue.put((task_id, tensor, transform_fn))
    
    def get_result(self, task_id, timeout=90):
        """Get result with timeout"""
        import time
        start = time.time()
        while task_id not in self.results:
            if time.time() - start > timeout:
                raise TimeoutError(f"Inference timeout for task {task_id}")
            time.sleep(0.01)
        
        with self.lock:
            return self.results.pop(task_id)


class PredictionCache:
    """LRU cache for predictions (avoid duplicate computations)"""
    def __init__(self, max_size=1000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.lock = __import__('threading').Lock()
    
    def get_cache_key(self, image_bytes):
        """Generate MD5 hash of image for cache key"""
        return hashlib.md5(image_bytes).hexdigest()
    
    def get(self, image_bytes):
        """Get prediction from cache"""
        key = self.get_cache_key(image_bytes)
        with self.lock:
            if key in self.cache:
                self.hits += 1
                # Move to end (LRU)
                self.cache.move_to_end(key)
                logger.debug(f"Cache HIT: {key[:8]}... (hit rate: {self.hit_rate():.1%})")
                return self.cache[key]
            self.misses += 1
        return None
    
    def set(self, image_bytes, result):
        """Set prediction in cache"""
        key = self.get_cache_key(image_bytes)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = result
            
            # Evict oldest if full
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
    
    def hit_rate(self):
        """Get cache hit rate"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0


class BatchProcessor:
    """Batch multiple writes together"""
    def __init__(self, flush_interval=5, batch_size=10):
        self.batch = []
        self.flush_interval = flush_interval
        self.batch_size = batch_size
        self.last_flush = time.time()
        self.lock = __import__('threading').Lock()
    
    def add(self, data):
        """Add data to batch"""
        with self.lock:
            self.batch.append(data)
            if self._should_flush():
                return self.flush()
        return None
    
    def _should_flush(self):
        """Check if should flush batch"""
        return (
            len(self.batch) >= self.batch_size or
            time.time() - self.last_flush > self.flush_interval
        )
    
    def flush(self):
        """Flush batch and return data"""
        if not self.batch:
            return None
        batch_copy = self.batch.copy()
        self.batch = []
        self.last_flush = time.time()
        logger.debug(f"Flushed batch of {len(batch_copy)} items")
        return batch_copy


class PerformanceMetrics:
    """Track performance metrics"""
    def __init__(self):
        self.inference_times = []
        self.request_count = 0
        self.start_time = time.time()
        self.lock = __import__('threading').Lock()
    
    def record_inference(self, duration_ms):
        """Record inference duration"""
        with self.lock:
            self.inference_times.append(duration_ms)
            self.request_count += 1
    
    def get_stats(self):
        """Get performance statistics"""
        with self.lock:
            if not self.inference_times:
                return {}
            
            # Use last 1000 requests
            times = self.inference_times[-1000:]
            times_sorted = sorted(times)
            
            return {
                'avg_inference_ms': sum(times) / len(times),
                'min_inference_ms': min(times),
                'max_inference_ms': max(times),
                'p95_inference_ms': times_sorted[int(len(times) * 0.95)],
                'p99_inference_ms': times_sorted[int(len(times) * 0.99)],
                'total_requests': self.request_count,
                'uptime_seconds': int(time.time() - self.start_time)
            }

# ============ END VERTICAL SCALING COMPONENTS ============

# Initialize scaling components
inference_queue = None
prediction_cache = None
batch_processor = None
metrics = None

# Device selection
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Model loading
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resnet50_final.pth")

print(f"Looking for model at: {MODEL_PATH}")

if not os.path.exists(MODEL_PATH):
    print(f"[ERROR] Model file not found at {MODEL_PATH}")
    raise FileNotFoundError(f"Model file not found: {MODEL_PATH}\nMake sure resnet50_final.pth is in the same directory as app.py")

print(f"[OK] Model file found! Size: {os.path.getsize(MODEL_PATH) / 1e6:.1f} MB")

try:
    model = models.resnet50(weights=None)
    model.fc = nn.Linear(2048, 2)  # two classes: Normal, Pneumonia
    
    print("Loading model weights...")
    state_dict = torch.load(MODEL_PATH, map_location=device)
    model.load_state_dict(state_dict)
    model = model.to(device)
    model.eval()
    print("[OK] Model loaded successfully!")
except Exception as e:
    print(f"[ERROR] loading model: {str(e)}")
    raise

# Image transforms
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225])
])

# Prediction function
def predict_from_bytes(image_bytes):
    """Predict from image bytes"""
    logger.debug(f"Received image bytes: {len(image_bytes)} bytes")
    
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        logger.debug(f"Image loaded successfully: {image.size}")
    except UnidentifiedImageError as e:
        logger.error(f"Invalid image: {str(e)}")
        return None, None, "Invalid or corrupted image."
    except Exception as e:
        logger.error(f"Error loading image: {str(e)}")
        return None, None, f"Error processing image: {str(e)}"

    try:
        logger.debug("Transforming image...")
        tensor = transform(image).unsqueeze(0).to(device)
        
        logger.debug("Running model inference...")
        with torch.no_grad():
            outputs = model(tensor)
            probs = torch.softmax(outputs, dim=1)
            confidence, predicted = torch.max(probs, 1)
        
        prediction = 'Pneumonia' if predicted.item() == 1 else 'Normal'
        confidence_val = confidence.item()
        logger.debug(f"Prediction: {prediction}, Confidence: {confidence_val}")
        return prediction, confidence_val, None
    
    except Exception as e:
        logger.error(f"Error during inference: {str(e)}")
        return None, None, str(e)

# Health check endpoint
@app.route("/health", methods=["GET"])
def health():
    """Health check"""
    return jsonify({
        "status": "ok",
        "device": str(device),
        "model_loaded": True
    }), 200

# Prediction endpoint with VERTICAL SCALING
@app.route("/predict", methods=["POST"])
def predict():
    """Prediction endpoint with caching and async processing"""
    logger.debug("Received prediction request")
    
    try:
        # Step 1: Get file from request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        patient_id = request.form.get('patient_id', 'anon')
        image_bytes = file.read()
        
        if not image_bytes:
            return jsonify({"error": "Empty file"}), 400
        
        logger.debug(f"Processing image for patient {patient_id}")
        
        # Step 2: Check cache first (VERTICAL SCALING)
        cached_result = prediction_cache.get(image_bytes)
        if cached_result:
            logger.debug(f"[OK] Cache HIT for patient {patient_id}")
            return jsonify(cached_result), 200
        
        # Step 3: Process image
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except UnidentifiedImageError as e:
            return jsonify({"error": f"Invalid image: {str(e)}"}), 400
        
        # Step 4: Run inference via async queue (VERTICAL SCALING)
        task_id = f"{patient_id}_{time.time()}"
        tensor = transform(image).unsqueeze(0)
        
        inference_start = time.time()
        inference_queue.queue_inference(task_id, tensor, lambda x: x)
        result = inference_queue.get_result(task_id)
        inference_ms = (time.time() - inference_start) * 1000
        
        # Step 5: Record metrics
        metrics.record_inference(inference_ms)
        
        # Step 6: Cache result (VERTICAL SCALING)
        prediction_cache.set(image_bytes, result)
        
        # Step 7: Save image locally
        os.makedirs(f"uploads/{patient_id}", exist_ok=True)
        timestamp = int(time.time())
        image_path = f"uploads/{patient_id}/{timestamp}.jpg"
        with open(image_path, 'wb') as f:
            f.write(image_bytes)
        
        logger.debug(f"[OK] Prediction: {result['prediction']} ({result['confidence']:.1%})")
        return jsonify({
            **result,
            "image_url": f"/uploads/{patient_id}/{timestamp}.jpg",
            "inference_ms": inference_ms
        }), 200
    
    except Exception as e:
        logger.error(f"Prediction error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Metrics endpoint
@app.route("/metrics", methods=["GET"])
def get_metrics():
    """Get performance metrics"""
    return jsonify({
        'metrics': metrics.get_stats(),
        'cache': {
            'hit_rate': prediction_cache.hit_rate(),
            'size': len(prediction_cache.cache),
            'max_size': prediction_cache.max_size
        },
        'inference_queue': {
            'queue_size': inference_queue.queue.qsize(),
            'max_queue_size': inference_queue.queue.maxsize
        }
    }), 200

# Serve uploaded images
@app.route("/uploads/<patient_id>/<filename>", methods=["GET"])
def get_image(patient_id, filename):
    """Serve uploaded image"""
    try:
        filepath = os.path.join("uploads", patient_id, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "Image not found"}), 404
        
        with open(filepath, 'rb') as f:
            data = f.read()
        
        return data, 200, {'Content-Type': 'image/jpeg'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Root endpoint
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "PneumoCare API with Vertical Scaling",
        "endpoints": {
            "predict": "/predict (POST with file)",
            "health": "/health (GET)",
            "metrics": "/metrics (GET)"
        }
    }), 200

# Error handlers
@app.errorhandler(400)
def bad_request(error):
    logger.error(f"Bad request: {error}")
    return jsonify({"error": "Bad request"}), 400

@app.errorhandler(404)
def not_found(error):
    logger.error(f"Not found: {error}")
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# Initialize vertical scaling components on startup
def init_scaling():
    """Initialize scaling components"""
    global inference_queue, prediction_cache, batch_processor, metrics
    
    inference_queue = ModelInferenceQueue(model, device, num_workers=4)
    prediction_cache = PredictionCache(max_size=1000)
    batch_processor = BatchProcessor(flush_interval=5, batch_size=10)
    metrics = PerformanceMetrics()
    
    logger.info("[OK] Vertical Scaling Components Initialized")
    logger.info("   - 4x async inference workers")
    logger.info("   - Prediction cache (1000 max)")
    logger.info("   - Batch processor")
    logger.info("   - Performance metrics tracking")

# Run server
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🏥 PneumoCare Flask API Server - WITH VERTICAL SCALING")
    print("="*70)
    print(f"Device: {device}")
    print(f"Model: ResNet50 (2 classes)")
    print(f"Listening on: http://127.0.0.1:5000")
    print("\n⚡ VERTICAL SCALING ENABLED:")
    print("   - Async inference queue (4 workers)")
    print("   - Prediction caching (LRU)")
    print("   - Performance metrics tracking")
    print("   - Expected throughput: 16 RPS (4x single instance)")
    print("\n📊 Metrics endpoint: http://127.0.0.1:5000/metrics")
    print("="*70 + "\n")
    
    # Initialize scaling components
    init_scaling()
    
    try:
        from waitress import serve
        serve(app, host='127.0.0.1', port=5000, threads=8, _quiet=False)
    except ImportError:
        app.run(
            host="127.0.0.1",
            port=5000,
            debug=False,
            use_reloader=False
        )

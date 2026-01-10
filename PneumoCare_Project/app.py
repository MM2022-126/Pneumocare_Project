import os

# SAFE settings — these DO NOT break Werkzeug
os.environ["FLASK_ENV"] = "production"
os.environ["FLASK_DEBUG"] = "0"

# DO NOT USE THIS (CAUSES YOUR ERROR)
# os.environ["WERKZEUG_RUN_MAIN"] = "true"

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image, UnidentifiedImageError
from flask import Flask, request, jsonify
from flask_cors import CORS
import io
import logging
import sys

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# CORS configuration - allow requests from all localhost origins
CORS(app, resources={
    r"/predict": {"origins": "*"},  # Allow from any origin
    r"/health": {"origins": "*"},
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

# ----------------- DEVICE -----------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# ----------------- LOAD MODEL -----------------
# Get the absolute path to the model file
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

# ----------------- TRANSFORMS -----------------
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225])
])

# ----------------- PREDICTION FUNCTION -----------------
def predict_from_bytes(image_bytes):
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
        
        logger.debug(f"Prediction: {['Normal', 'Pneumonia'][predicted.item()]}, Confidence: {confidence.item()}")
        classes = ["Normal", "Pneumonia"]
        return classes[predicted.item()], float(confidence.item()), None
    except Exception as e:
        logger.error(f"Error during prediction: {str(e)}")
        return None, None, f"Error during prediction: {str(e)}"

# ----------------- API ROUTE -----------------
@app.route("/predict", methods=["OPTIONS"])
def predict_options():
    """Handle CORS preflight requests"""
    return jsonify({"status": "ok"}), 200

@app.route("/predict", methods=["POST"])
def predict():
    logger.info("=== PREDICT REQUEST START ===")
    
    try:
        if "file" not in request.files:
            logger.error("No file in request")
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        logger.debug(f"File received: {file.filename}, Size: {len(file.read())} bytes")
        file.seek(0)  # Reset file pointer
        
        img_bytes = file.read()
        logger.debug(f"Read {len(img_bytes)} bytes from file")

        prediction, confidence, error = predict_from_bytes(img_bytes)
        
        if error:
            logger.error(f"Prediction error: {error}")
            return jsonify({"error": error}), 400

        result = {"prediction": prediction, "confidence": confidence}
        logger.info(f"=== PREDICT REQUEST SUCCESS: {result} ===")
        return jsonify(result)
    
    except Exception as e:
        logger.exception(f"Unexpected error in predict: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Health check endpoint
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "device": str(device),
        "model_loaded": True
    }), 200

# Root endpoint
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "PneumoCare API",
        "endpoints": {
            "predict": "/predict (POST with file)",
            "health": "/health (GET)"
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

# ----------------- RUN SERVER -----------------
if __name__ == "__main__":
    print("\n" + "="*60)
    print("PneumoCare Flask API Server")
    print("="*60)
    print(f"Device: {device}")
    print(f"Model: ResNet50 (2 classes)")
    print(f"Listening on: http://127.0.0.1:5000")
    print("="*60 + "\n")
    
    from waitress import serve
    
    port = int(os.environ.get("FLASK_PORT", 5000))
    serve(app, host="0.0.0.0", port=port, threads=4, _quiet=False)

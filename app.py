import hmac
import logging
import os
from flask import Flask, jsonify, request
from dotenv import load_dotenv
import MetaTrader5 as mt5
from flasgger import Swagger
from werkzeug.middleware.proxy_fix import ProxyFix
from swagger import swagger_config

# Import routes
from routes.health import health_bp
from routes.symbol import symbol_bp
from routes.data import data_bp
from routes.position import position_bp
from routes.order import order_bp
from routes.history import history_bp
from routes.error import error_bp

load_dotenv()
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['PREFERRED_URL_SCHEME'] = 'https'

swagger = Swagger(app, config=swagger_config)

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(symbol_bp)
app.register_blueprint(data_bp)
app.register_blueprint(position_bp)
app.register_blueprint(order_bp)
app.register_blueprint(history_bp)
app.register_blueprint(error_bp)

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Paths that don't require authentication (Swagger UI)
_PUBLIC_PREFIXES = ('/apidocs', '/flasgger_static', '/apispec_1.json', '/health')

@app.before_request
def require_api_key():
    if request.path.startswith(_PUBLIC_PREFIXES):
        return None
    api_key = os.environ.get('API_KEY', '')
    if not api_key:
        return None  # Auth not configured — allow all (dev/test mode)
    provided = request.headers.get('X-API-Key', '')
    if not provided:
        return jsonify({"error": "Missing X-API-Key header"}), 401
    if not hmac.compare_digest(provided, api_key):
        return jsonify({"error": "Invalid API key"}), 403

if __name__ == '__main__':
    if not mt5.initialize():
        logger.error("Failed to initialize MT5.")
    app.run(host='0.0.0.0', port=int(os.environ.get('MT5_API_PORT', 5000)))
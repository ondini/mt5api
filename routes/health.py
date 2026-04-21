from flask import Blueprint, jsonify
import MetaTrader5 as mt5
from flasgger import swag_from

health_bp = Blueprint('health', __name__)

@health_bp.route('/health')
@swag_from({
    'tags': ['Health'],
    'responses': {
        200: {
            'description': 'Health check successful',
            'schema': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string'},
                    'mt5_connected': {'type': 'boolean'},
                    'mt5_initialized': {'type': 'boolean'}
                }
            }
        }
    }
})
def health_check():
    """
    Health Check Endpoint
    ---
    description: Check the health status of the application and MT5 connection.
    responses:
      200:
        description: Health check successful
    """
    terminal = mt5.terminal_info()
    account = mt5.account_info()
    return jsonify({
        "status": "healthy",
        "mt5_terminal_connected": terminal is not None,
        "mt5_account_logged_in": account is not None,
        "mt5_account": account.login if account else None,
    }), 200
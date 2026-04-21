from flask import Blueprint, jsonify, request
import MetaTrader5 as mt5
import logging
from flasgger import swag_from

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


@auth_bp.route('/login', methods=['POST'])
@swag_from({
    'tags': ['Auth'],
    'parameters': [
        {
            'name': 'account',
            'in': 'query',
            'type': 'integer',
            'required': True,
            'description': 'MT5 account number.'
        },
        {
            'name': 'password',
            'in': 'query',
            'type': 'string',
            'required': True,
            'description': 'MT5 account password.'
        },
        {
            'name': 'server',
            'in': 'query',
            'type': 'string',
            'required': True,
            'description': 'MT5 broker server name.'
        },
    ],
    'responses': {
        200: {
            'description': 'Login successful.',
            'schema': {
                'type': 'object',
                'properties': {
                    'login': {'type': 'integer'},
                    'server': {'type': 'string'},
                    'currency': {'type': 'string'},
                    'balance': {'type': 'number'},
                }
            }
        },
        400: {'description': 'Missing required parameters.'},
        401: {'description': 'Login failed — invalid credentials.'},
        500: {'description': 'Internal server error.'},
    }
})
def login():
    """
    Login to MT5 Account
    ---
    description: Initialize the MT5 terminal and authenticate with the given account credentials.
    """
    try:
        account = request.args.get('account')
        password = request.args.get('password')
        server = request.args.get('server')

        if not all([account, password, server]):
            return jsonify({"error": "account, password, and server parameters are required"}), 400

        account = int(account)

        if not mt5.initialize():
            return jsonify({"error": "Failed to initialize MT5 terminal", "last_error": mt5.last_error()}), 500

        authorized = mt5.login(account, password=password, server=server)
        if not authorized:
            code, msg = mt5.last_error()
            return jsonify({"error": f"Login failed: {msg}", "error_code": code}), 401

        info = mt5.account_info()
        return jsonify({
            "login": info.login,
            "server": info.server,
            "currency": info.currency,
            "balance": info.balance,
        }), 200

    except ValueError:
        return jsonify({"error": "Invalid account format"}), 400
    except Exception as e:
        logger.error(f"Error in login: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@auth_bp.route('/logout', methods=['POST'])
@swag_from({
    'tags': ['Auth'],
    'responses': {
        200: {'description': 'Logout successful.'},
        500: {'description': 'Internal server error.'},
    }
})
def logout():
    """
    Logout from MT5
    ---
    description: Shut down the MT5 terminal connection.
    """
    try:
        mt5.shutdown()
        return jsonify({"status": "logged out"}), 200
    except Exception as e:
        logger.error(f"Error in logout: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

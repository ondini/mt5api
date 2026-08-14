"""
Combined login + history-fetch endpoint, backed by sync_worker's single
background worker thread. See sync_worker.py for why this closes the
cross-account race that exists between separate /login + /history_deals_get
calls, and for the known limitation that other routes are not synchronized
against this worker.
"""
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flasgger import swag_from

import sync_worker

sync_bp = Blueprint('sync', __name__)
logger = logging.getLogger(__name__)


@sync_bp.route('/sync_account_history', methods=['POST'])
@swag_from({
    'tags': ['Sync'],
    'parameters': [
        {'name': 'account', 'in': 'query', 'type': 'integer', 'required': True,
         'description': 'MT5 account number.'},
        {'name': 'password', 'in': 'query', 'type': 'string', 'required': True,
         'description': 'MT5 account password.'},
        {'name': 'server', 'in': 'query', 'type': 'string', 'required': True,
         'description': 'MT5 broker server name.'},
        {'name': 'from_date', 'in': 'query', 'type': 'string', 'format': 'date-time', 'required': True,
         'description': 'Start date in ISO format.'},
        {'name': 'to_date', 'in': 'query', 'type': 'string', 'format': 'date-time', 'required': True,
         'description': 'End date in ISO format.'},
    ],
    'responses': {
        202: {
            'description': 'Sync job accepted and queued. Never rejects for capacity reasons.',
            'schema': {'type': 'object'}
        },
        400: {'description': 'Missing or invalid parameters.'},
        500: {'description': 'Internal server error.'},
    }
})
def sync_account_history_endpoint():
    """
    Queue a login + history-fetch job for an account
    ---
    description: Enqueues a combined login and deal-history fetch for the given account, processed serially by a single background worker so concurrent requests for different accounts can never race each other.
    """
    try:
        account = request.args.get('account')
        password = request.args.get('password')
        server = request.args.get('server')
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')

        if not all([account, password, server, from_date, to_date]):
            return jsonify({
                "error": "account, password, server, from_date, and to_date parameters are required"
            }), 400

        try:
            account = int(account)
        except ValueError:
            return jsonify({"error": "Invalid account format"}), 400

        try:
            from_dt = datetime.fromisoformat(from_date.replace('Z', '+00:00'))
            to_dt = datetime.fromisoformat(to_date.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({"error": "Invalid parameter format"}), 400

        from_timestamp = int(from_dt.timestamp())
        to_timestamp = int(to_dt.timestamp())

        job_id = sync_worker.enqueue_sync_job(
            account, password, server, from_date, to_date, from_timestamp, to_timestamp
        )
        return jsonify(sync_worker.get_job_view(job_id)), 202

    except Exception as e:
        logger.error(f"Error in sync_account_history: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@sync_bp.route('/sync_account_history/<job_id>', methods=['GET'])
@swag_from({
    'tags': ['Sync'],
    'parameters': [
        {'name': 'job_id', 'in': 'path', 'type': 'string', 'required': True,
         'description': 'Job ID returned by POST /sync_account_history.'},
    ],
    'responses': {
        200: {'description': 'Job status and result (if done).', 'schema': {'type': 'object'}},
        404: {'description': 'Job not found.'},
        500: {'description': 'Internal server error.'},
    }
})
def sync_account_history_status_endpoint(job_id):
    """
    Get the status/result of a queued sync job
    ---
    description: Returns the current status of a sync job (queued, processing, done, failed), including the fetched deals once done.
    """
    try:
        job_view = sync_worker.get_job_view(job_id)
        if job_view is None:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(job_view), 200
    except Exception as e:
        logger.error(f"Error in sync_account_history_status: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

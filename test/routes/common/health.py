from flask import Blueprint

health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    """Liveness/readiness probe endpoint"""
    return {'status': 'ok'}, 200
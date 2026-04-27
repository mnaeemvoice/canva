# middleware.py
import logging

logger = logging.getLogger(__name__)

class RequestLoggerMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        logger.warning(f"""
🔥 REQUEST HIT:
METHOD: {request.method}
PATH: {request.path}
IP: {request.META.get('REMOTE_ADDR')}
BODY: {request.body[:200]}
""")

        response = self.get_response(request)
        return response
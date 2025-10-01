from django.utils.deprecation import MiddlewareMixin
# from django.core.cache import cache
# from rest_framework.exceptions import APIException


class PreventDuplicateSubmissionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # pass
        # Avoid duplicate submission protection for Django admin site
        if request.path.startswith('/admin/'):
            return  # Skip middleware for admin site

        # request_id = request.headers.get('X-Request-ID')
        # if request.method == "POST":
        #     if not request_id:
        #         raise APIException("Missing X-Request-ID header")
        #     cache_key = f"req-id:{request_id}"
        #     if cache.get(cache_key):
        #         raise APIException("Duplicate submission detected")
        #     cache.set(cache_key, True, timeout=60)  # prevent reuse for 60 seconds # noqa


# --- NGROK BYPASS MIDDLEWARE ---
class NgrokBypassMiddleware:
    """
    Middleware to bypass the ngrok browser warning page by setting the
    'ngrok-skip-browser-warning' header in the response if not present in the request. # noqa
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # If the header is not present, set it in the response
        response = self.get_response(request)
        if 'ngrok-skip-browser-warning' not in request.headers:
            response['ngrok-skip-browser-warning'] = 'true'
        return response

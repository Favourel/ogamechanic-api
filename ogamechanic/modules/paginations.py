from rest_framework.pagination import BasePagination
from rest_framework.response import Response


class CustomLimitOffsetPagination(BasePagination):
    """Custom pagination class using limit and offset"""
    default_limit = 10
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100

    def get_limit(self, request):
        """Get the limit from request query params"""
        try:
            limit = int(request.query_params.get(
                self.limit_query_param,
                self.default_limit
            ))
            return min(limit, self.max_limit)
        except (TypeError, ValueError):
            return self.default_limit

    def get_offset(self, request):
        """Get the offset from request query params"""
        try:
            return int(request.query_params.get(self.offset_query_param, 0))
        except (TypeError, ValueError):
            return 0

    def paginate_queryset(self, queryset, request, view=None):
        """Paginate the queryset"""
        self.limit = self.get_limit(request)
        self.offset = self.get_offset(request)
        self.count = queryset.count()
        self.request = request
        self.queryset = queryset[self.offset:self.offset + self.limit]
        return self.queryset

    def get_paginated_response(self, data):
        """Return paginated response"""
        return Response({
            'count': self.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })

    def get_next_link(self):
        """Get the next page link"""
        if self.offset + self.limit >= self.count:
            return None

        url = self.request.build_absolute_uri()
        offset = self.offset + self.limit
        return self._get_link(url, offset)

    def get_previous_link(self):
        """Get the previous page link"""
        if self.offset <= 0:
            return None

        url = self.request.build_absolute_uri()
        offset = max(0, self.offset - self.limit)
        return self._get_link(url, offset)

    def _get_link(self, url, offset):
        """Helper method to build pagination links"""
        from urllib.parse import urlparse, parse_qs, urlencode
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        query_params[self.offset_query_param] = [str(offset)]
        query_params[self.limit_query_param] = [str(self.limit)]

        return (
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            f"?{urlencode(query_params, doseq=True)}"
        )


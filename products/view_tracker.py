import logging
import re
from datetime import timedelta
from django.utils import timezone
from django.db.models import F
from .models import Product, ProductView

logger = logging.getLogger(__name__)

# Regular expression pattern to detect common crawlers, spiders, and automated agents
BOT_REGEX = re.compile(
    r'(bot|crawl|spider|slurp|mediapartners|headless|python-requests|'
    r'curl|wget|lighthouse|scraper|feedfetcher|facebookexternalhit|'
    r'twitterbot|whatsapp|postmanruntime|ahrefs|semrush|yandex|bingbot|googlebot)',
    re.IGNORECASE
)

DEFAULT_COOLDOWN_MINUTES = 15


def get_client_ip(request) -> str:
    """
    Extracts the client's real IP address from HTTP headers,
    handling reverse proxies and load balancers.
    """
    if not request:
        return None

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # X-Forwarded-For can be a comma-separated list of IPs.
        # The client IP is the first one.
        parts = [ip.strip() for ip in x_forwarded_for.split(',') if ip.strip()]
        if parts:
            return parts[0]

    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        return x_real_ip.strip()

    remote_addr = request.META.get('REMOTE_ADDR')
    if remote_addr:
        return remote_addr.strip()

    return None


def is_bot_request(request) -> bool:
    """
    Checks if the incoming request originates from a known bot, web scraper, or crawler.
    """
    if not request:
        return False

    user_agent = request.META.get('HTTP_USER_AGENT', '')
    if not user_agent:
        # Missing user agent is often suspicious or automated
        return False

    return bool(BOT_REGEX.search(user_agent))


def record_product_view(product, request, cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES):
    """
    Records a product view with robust defenses:
    1. Ignores bots and automated crawlers to avoid false traffic.
    2. Ignores self-views when the merchant views their own product.
    3. Implements a cooldown window per viewer (user or IP) to prevent F5/refresh spam.
    4. Tracks registered customers when authenticated, or guest IP when anonymous.
    5. Updates denormalized counters on Product atomically using F() expressions.
    6. Fails safely without raising exceptions to protect the main detail response.

    Returns:
        tuple (bool, str): (whether a view increment was recorded, reason or status code)
    """
    if not product or not request:
        return False, "invalid_args"

    try:
        # 1. Filter out bots
        if is_bot_request(request):
            return False, "bot_detected"

        # 2. Filter out self-views (merchants viewing their own product)
        if request.user.is_authenticated and product.merchant_id == request.user.id:
            return False, "self_view"

        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        now = timezone.now()

        # 3. Check for existing viewer record
        if request.user.is_authenticated:
            existing_view = ProductView.objects.filter(
                product=product, user=request.user
            ).first()
        else:
            if not ip_address:
                return False, "no_identifier"
            existing_view = ProductView.objects.filter(
                product=product, user__isnull=True, ip_address=ip_address
            ).first()

        # 4. Handle first-time view vs repeat view with cooldown
        if not existing_view:
            # First time this customer/guest has viewed the product
            ProductView.objects.create(
                product=product,
                user=request.user if request.user.is_authenticated else None,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else None,
                view_count=1,
            )
            # Atomically increment total views and unique views
            Product.objects.filter(id=product.id).update(
                views_count=F('views_count') + 1,
                unique_views_count=F('unique_views_count') + 1,
            )
            # Update memory representation if available
            if hasattr(product, 'views_count') and product.views_count is not None:
                product.views_count += 1
            if hasattr(product, 'unique_views_count') and product.unique_views_count is not None:
                product.unique_views_count += 1

            return True, "new_unique_view"

        # Repeat viewer: check cooldown
        time_since_last_view = now - existing_view.last_viewed_at
        if time_since_last_view < timedelta(minutes=cooldown_minutes):
            return False, "cooldown_active"

        # Outside cooldown: increment view count
        ProductView.objects.filter(id=existing_view.id).update(
            view_count=F('view_count') + 1,
            last_viewed_at=now,
        )
        Product.objects.filter(id=product.id).update(
            views_count=F('views_count') + 1
        )
        if hasattr(product, 'views_count') and product.views_count is not None:
            product.views_count += 1

        return True, "repeat_view_incremented"

    except Exception as e:
        logger.warning(
            f"Error recording product view for product {getattr(product, 'id', None)}: {e}",
            exc_info=True
        )
        return False, f"error: {str(e)}"

from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from products.models import Order, Product
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.template.loader import render_to_string
import logging
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


User = get_user_model()


def send_html_email(subject, to_email, text_content, html_template, context):
    html_content = render_to_string(html_template, context)
    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()


@shared_task
def send_order_confirmation_email(order_id, customer_email):
    try:
        order = Order.objects.select_related("customer").get(id=order_id)
        customer_name = order.customer.get_full_name() or order.customer.email
        order_date = order.created_at.strftime("%Y-%m-%d %H:%M")
    except Order.DoesNotExist:
        customer_name = customer_email
        order_date = timezone.now().strftime("%Y-%m-%d %H:%M")
    subject = "Order Confirmation - Thank you for your purchase!"
    text_content = f"""
        Dear {customer_name},

        Thank you for your order!
        Order ID: {order_id}
        Order Date: {order_date}
        We have received your order and will begin processing it shortly.
        You will receive another email once your order status is updated.
        If you have any questions, please reply to this email.
        Best regards,
        The Ogamechanic Team
        """
    context = {
        "customer_name": customer_name,
        "order_id": order_id,
        "order_date": order_date,
    }
    send_html_email(
        subject,
        customer_email,
        text_content,
        "products/emails/order_confirmation.html",
        context,
    )


@shared_task
def send_order_status_update_email(order_id, customer_email, new_status):
    try:
        order = Order.objects.select_related("customer").get(id=order_id)
        customer_name = order.customer.get_full_name() or order.customer.email
    except Order.DoesNotExist:
        customer_name = customer_email
    subject = "Order Update - Your order status has changed"
    text_content = f"""
        Dear {customer_name},
        Your order (ID: {order_id}) status has been updated to: {new_status}.
        You can log in to your account to view more details.
        Thank you for choosing Ogamechanic!
        Best regards,
        The Ogamechanic Team
        """
    context = {
        "customer_name": customer_name,
        "order_id": order_id,
        "new_status": new_status,
    }
    send_html_email(
        subject,
        customer_email,
        text_content,
        "products/emails/order_status_update.html",
        context,
    )


@shared_task
def send_new_review_notification_email(product_id, merchant_email):
    try:
        product = Product.objects.select_related("merchant").get(id=product_id)
        merchant = product.merchant
        merchant_name = merchant.get_full_name() or merchant.email
        latest_review = (
            product.reviews.select_related("user").order_by("-created_at").first()  # noqa
        )
        if latest_review:
            reviewer_name = (
                latest_review.user.get_full_name() or latest_review.user.email
            )
            rating = latest_review.rating
            comment = latest_review.comment
        else:
            reviewer_name = "A customer"
            rating = "N/A"
            comment = ""
        product_name = product.name
    except Product.DoesNotExist:
        merchant_name = merchant_email
        product_name = str(product_id)
        reviewer_name = "A customer"
        rating = "N/A"
        comment = ""
    subject = "New Review for Your Product"
    text_content = f"""
        Hello {merchant_name},
        Your product "{product_name}" has received a new review.
        Reviewer: {reviewer_name}
        Rating: {rating}/5
        Comment: "{comment}"
        Log in to your dashboard to see more details.
        Best regards,
        The Ogamechanic Team
        """
    context = {
        "merchant_name": merchant_name,
        "product_name": product_name,
        "reviewer_name": reviewer_name,
        "rating": rating,
        "comment": comment,
    }
    send_html_email(
        subject,
        merchant_email,
        text_content,
        "products/emails/new_review_notification.html",
        context,
    )


# --- Additional Email Scenarios ---


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_merchant_new_order_email(self, order_id, merchant_email):
    """
    Sends an email notification to the merchant when a new order is received.
    Retries up to 3 times in case of failure with exponential backoff.
    """

    logger = logging.getLogger(__name__)

    subject = "New Order Received!"
    order_url = f"{settings.FRONTEND_URL}/orders/{order_id}/status/"
    text_content = (
        f"You have received a new order: {order_id}.\n" f"View order: {order_url}"  # noqa
    )
    context = {
        "order_id": order_id,
        "order_url": order_url,
    }

    # Validate merchant email before sending
    try:
        validate_email(merchant_email)
    except ValidationError:
        logger.error(
            f"Invalid merchant email: {merchant_email} for order {order_id}"
        )
        return

    try:
        send_html_email(
            subject,
            merchant_email,
            text_content,
            "products/emails/merchant_new_order.html",
            context,
        )
        logger.info(
            f"Merchant new order email sent to {merchant_email} for order {order_id}"  # noqa
        )  # noqa
    except Exception as exc:
        logger.error(
            f"Failed to send merchant new order email to {merchant_email} for order {order_id}: {exc}"  # noqa
        )  # noqa
        # Exponential backoff: delay = 60 * (2 ** (self.request.retries - 1))
        retry_delay = 60 * (2 ** (self.request.retries)) if self.request.retries else 60  # noqa
        self.retry(exc=exc, countdown=retry_delay)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_customer_order_shipped_email(self, order_id, customer_email):
    logger = logging.getLogger(__name__)
    subject = "Your Order Has Shipped!"
    text_content = f"Your order {order_id} has been shipped."
    context = {
        "order_id": order_id,
    }

    try:
        validate_email(customer_email)
    except ValidationError:
        logger.error(f"Invalid customer email: {customer_email} for order {order_id}")  # noqa
        return

    try:
        send_html_email(
            subject,
            customer_email,
            text_content,
            "products/emails/customer_order_shipped.html",
            context,
        )
        logger.info(
            f"Order shipped email sent to {customer_email} for order {order_id}"  # noqa
        )
    except Exception as exc:
        logger.error(
            f"Failed to send order shipped email to {customer_email} for order {order_id}: {exc}"  # noqa
        )
        self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_customer_order_completed_email(self, order_id, customer_email):
    logger = logging.getLogger(__name__)
    subject = "Order Delivered/Completed"
    text_content = f"Your order {order_id} has been delivered/completed."
    context = {
        "order_id": order_id,
    }

    try:
        validate_email(customer_email)
    except ValidationError:
        logger.error(f"Invalid customer email: {customer_email} for order {order_id}")  # noqa
        return

    try:
        send_html_email(
            subject,
            customer_email,
            text_content,
            "products/emails/customer_order_completed.html",
            context,
        )
        logger.info(
            f"Order completed email sent to {customer_email} for order {order_id}"  # noqa
        )
    except Exception as exc:
        logger.error(
            f"Failed to send order completed email to {customer_email} for order {order_id}: {exc}"  # noqa
        )
        self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_merchant_order_cancelled_email(self, order_id, merchant_email):
    logger = logging.getLogger(__name__)
    subject = "Order Cancelled"
    text_content = f"Order {order_id} has been cancelled."
    context = {
        "order_id": order_id,
    }

    try:
        validate_email(merchant_email)
    except ValidationError:
        logger.error(f"Invalid merchant email: {merchant_email} for order {order_id}")  # noqa
        return

    try:
        send_html_email(
            subject,
            merchant_email,
            text_content,
            "products/emails/merchant_order_cancelled.html",
            context,
        )
        logger.info(
            f"Order cancelled email sent to {merchant_email} for order {order_id}"  # noqa
        )
    except Exception as exc:
        logger.error(
            f"Failed to send order cancelled email to {merchant_email} for order {order_id}: {exc}"  # noqa
        )
        self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_customer_refund_email(self, order_id, customer_email):
    logger = logging.getLogger(__name__)
    subject = "Refund Processed"
    text_content = f"A refund for order {order_id} has been processed."
    context = {
        "order_id": order_id,
    }

    try:
        validate_email(customer_email)
    except ValidationError:
        logger.error(f"Invalid customer email: {customer_email} for order {order_id}")  # noqa
        return

    try:
        send_html_email(
            subject,
            customer_email,
            text_content,
            "products/emails/customer_refund.html",
            context,
        )
        logger.info(f"Refund email sent to {customer_email} for order {order_id}")  # noqa
    except Exception as exc:
        logger.error(
            f"Failed to send refund email to {customer_email} for order {order_id}: {exc}"  # noqa
        )
        self.retry(exc=exc)

from multiprocessing import Value
from rest_framework.views import APIView
from rest_framework import permissions, status, parsers
from rest_framework.response import Response
from django.db import connection
from django.db.models import (Q, Sum, Count, F, DecimalField, 
                              ExpressionWrapper, 
                              Func, Avg, Prefetch, Exists, OuterRef)
from .models import (Product, Category, ProductImage, 
                     Order, Cart, CartItem, OrderItem, ProductReview,
                     FollowMerchant, FavoriteProduct)
from .serializers import (
    ProductSerializer, ProductCreateSerializer, CategorySerializer, 
    HomeResponseSerializer, OrderSerializer, CartSerializer, 
    ProductReviewSerializer, FollowMerchantSerializer,
    FollowMerchantListSerializer, FavoriteProductSerializer,
    FavoriteProductListSerializer, ProductImageSerializer,
    ProductImageUpdateSerializer
)
from ogamechanic.modules.utils import (
    api_response, get_incoming_request_checks, incoming_request_checks,
    resize_and_save_image
)
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from users.models import MechanicProfile
from users.serializers import MechanicProfileSerializer
import requests
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from products.tasks import (
    send_order_confirmation_email,
    send_order_status_update_email,
    send_new_review_notification_email,
    send_merchant_new_order_email,
    send_customer_order_shipped_email,
    send_customer_order_completed_email,
    send_merchant_order_cancelled_email,
    send_customer_refund_email,
)
from ogamechanic.modules.paginations import CustomLimitOffsetPagination
from users.throttling import UserRateThrottle
import logging
import traceback

from django.db.models.functions import Coalesce
from django.db import models

logger = logging.getLogger(__name__)


class ProductListCreateView(APIView):
    """
    API endpoint to list all products (optionally filterable by merchant, category, price, etc.) # noqa
    and to create a new product (merchant only).
    """
    parser_classes = [
        parsers.MultiPartParser,
        parsers.FormParser,
        parsers.JSONParser
    ]
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination
    throttle_classes = [UserRateThrottle]

    def get_paginated_response(self, queryset):
        """Return paginated response"""
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, self.request)
        serializer = ProductSerializer(
            page, many=True, context={'request': self.request})
        return paginator.get_paginated_response(serializer.data)

    @swagger_auto_schema(
        operation_description="List all products. Optionally filter by merchant, category, price, or rental status.", # noqa
        manual_parameters=[
            openapi.Parameter(
                'merchant',
                openapi.IN_QUERY,
                description="Filter by merchant user ID",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=False
            ),
            openapi.Parameter(
                'make',
                openapi.IN_QUERY,
                description="Filter by make ID",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'category',
                openapi.IN_QUERY,
                description="Filter by category ID",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'is_rental',
                openapi.IN_QUERY,
                description="Filter by rental status (true/false)",
                type=openapi.TYPE_BOOLEAN,
                required=False
            ),
            openapi.Parameter(
                'min_price',
                openapi.IN_QUERY,
                description="Filter by minimum price",
                type=openapi.TYPE_NUMBER,
                required=False
            ),
            openapi.Parameter(
                'max_price',
                openapi.IN_QUERY,
                description="Filter by maximum price",
                type=openapi.TYPE_NUMBER,
                required=False
            ),
        ],
        responses={
            200: ProductSerializer(many=True),
        }
    )
    def get(self, request):
        """
        List all products, with optional filters:
        - merchant: user ID of the merchant
        - category: category ID
        - is_rental: true/false
        - min_price: minimum price
        - max_price: maximum price
        """
        try:
            status_, data = get_incoming_request_checks(request)
            if not status_:
                return Response(
                    api_response(message=data, status=False), status=400
                )

            queryset = (
                Product.objects.select_related("merchant", "category")
                .prefetch_related(
                    Prefetch(
                        "images",
                        queryset=ProductImage.objects.order_by("ordering")
                    )
                )
                .annotate(
                    avg_rating=Avg("reviews__rating"),
                    total_purchased=Sum(
                        "orderitem__quantity",
                        filter=Q(orderitem__order__status="paid")
                    ),
                    is_in_favorite_list=Exists(
                        FavoriteProduct.objects.filter(
                            product=OuterRef("pk"), user=request.user)
                    ) if request.user.is_authenticated else None,
                    is_in_cart=Exists(
                        CartItem.objects.filter(
                            cart__user=request.user,
                            product=OuterRef("pk"))
                    ) if request.user.is_authenticated else None,
                ).order_by('-updated_at', '-created_at')
            )

            # Filtering
            merchant = request.query_params.get('merchant')
            category = request.query_params.get('category')
            is_rental = request.query_params.get('is_rental')
            min_price = request.query_params.get('min_price')
            max_price = request.query_params.get('max_price')
            make = request.query_params.get('make')

            # Exclude rented cars (is_rental=True) by default
            if is_rental is not None:
                if is_rental.lower() in ['true', '1']:
                    queryset = queryset.filter(is_rental=True)
                elif is_rental.lower() in ['false', '0']:
                    queryset = queryset.filter(is_rental=False)
                else:
                    return Response(
                        api_response(
                            message="Invalid is_rental value. Use true or false.", # noqa
                            status=False),
                        status=400
                    )
            else:
                queryset = queryset.filter(is_rental=False)

            if make:
                try:
                    queryset = queryset.filter(make__id=make)
                except (ValueError, TypeError):
                    return Response(
                        api_response(message="Invalid make ID.", status=False),
                        status=400
                    )

            if merchant:
                try:
                    queryset = queryset.filter(merchant__id=merchant)
                except (ValueError, TypeError):
                    return Response(
                        api_response(
                            message="Invalid merchant ID.", status=False),
                        status=400
                    )
            if category:
                try:
                    queryset = queryset.filter(category__id=category)
                except (ValueError, TypeError):
                    return Response(
                        api_response(
                            message="Invalid category ID.", status=False),
                        status=400
                    )
            if min_price is not None:
                try:
                    min_price_val = float(min_price)
                    queryset = queryset.filter(price__gte=min_price_val)
                except (ValueError, TypeError):
                    return Response(
                        api_response(
                            message="Invalid min_price value.", 
                            status=False),
                        status=400
                    )
            if max_price is not None:
                try:
                    max_price_val = float(max_price)
                    queryset = queryset.filter(price__lte=max_price_val)
                except (ValueError, TypeError):
                    return Response(
                        api_response(
                            message="Invalid max_price value.",
                            status=False),
                        status=400
                    )

            paginated_response = self.get_paginated_response(queryset)
            return Response(api_response(
                message="Product list retrieved successfully.",
                status=True,
                data=paginated_response.data
            ))
        except Exception as exc:
            logger.error(
                "Error in ProductListCreateView.get: %s", exc,
                exc_info=True)
            return Response(
                api_response(
                    message="An error occurred while retrieving products.",
                    status=False
                ),
                status=500
            )

    @swagger_auto_schema(
        operation_description="Create a new product (merchant only). "
                              "For spare parts, you can specify multiple vehicle " # noqa
                              "makes/models in the vehicle_compatibility field.", # noqa
        request_body=ProductCreateSerializer,
        responses={201: ProductSerializer()}
    )
    def post(self, request):
        try:
            status_, data = incoming_request_checks(request)
            if not status_:
                return Response(
                    api_response(message=data, status=False), status=400
                )
            user = request.user
            if (
                not user.is_authenticated
                or not user.roles.filter(name='merchant').exists()
                or not hasattr(user, 'merchant_profile')
                or not user.merchant_profile.is_approved
                # or not user.is_staff
            ):
                return Response(
                    api_response(
                        message="Only authenticated and approved merchants can create products.",  # noqa
                        status=False
                    ),
                    status=status.HTTP_403_FORBIDDEN
                )
            serializer = ProductCreateSerializer(data=data)
            if serializer.is_valid():
                product = serializer.save(merchant=user)
                # images = request.FILES.getlist('images')
                # for idx, image in enumerate(images):
                #     ProductImage.objects.create(
                #         product=product, image=image, ordering=idx
                #     )
                return Response(
                    api_response(
                        message="Product created successfully.",
                        status=True,
                        data=ProductSerializer(
                            product, context={'request': request}).data
                    ),
                    status=status.HTTP_201_CREATED
                )
            return Response(
                api_response(
                    message=(
                        ", ".join(
                            [
                                f"{field}: {', '.join(errors)}"
                                for field, errors in serializer.errors.items()
                            ]  # noqa
                        )
                        if serializer.errors
                        else "Invalid data"
                    ),
                    status=False,
                    errors=serializer.errors,
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Error in product creation: {str(e)}\n{tb_str}")
            return Response(
                api_response(
                    message="An error occurred while creating the product.",
                    status=False,
                    errors={"traceback": tb_str}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProductImageCreateView(APIView):
    """
    API endpoint to upload images for a product.
    Only the merchant who owns the product can upload images.
    """
    permission_classes = [permissions.IsAuthenticated]

    from drf_yasg import openapi

    @swagger_auto_schema(
        operation_summary="Upload Product Images",
        operation_description="Upload one or more images for a product (merchant only).", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["images"],
            properties={
                "images": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_FILE),
                    description="List of image files to upload (multipart/form-data)." # noqa
                )
            }
        ),
        responses={201: ProductImageSerializer(many=True)}
    )
    def post(self, request, product_id):
        from django.db import models
        # Validate UUID so invalid IDs return JSON instead of HTML 404
        try:
            from uuid import UUID
            product_uuid = UUID(str(product_id))
        except Exception:
            return Response(
                api_response(
                    message="Invalid product_id.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            product = Product.objects.get(id=product_uuid)
        except Product.DoesNotExist:
            return Response(
                api_response(
                    message="Product not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        # Only the merchant who owns the product can upload images
        if product.merchant != request.user:
            return Response(
                api_response(
                    message="You do not have permission to upload images for this product.", # noqa
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN
            )
        images = request.FILES.getlist('images')
        if not images:
            return Response(
                api_response(
                    message="No images provided.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        created_images = []

        # Get the current max ordering for this product's images
        max_ordering = product.images.aggregate(
            max_ordering=models.Max('ordering'))['max_ordering'] or 0

        for idx, uploaded_image in enumerate(images, start=1):
            # Use the image optimizer utility
            optimized_image = resize_and_save_image(uploaded_image, 400, 400)
            if not optimized_image:
                continue

            product_image = ProductImage.objects.create(
                product=product,
                image=optimized_image,
                ordering=max_ordering + idx
            )
            created_images.append(product_image)

        if not created_images:
            return Response(
                {"detail": "No valid images were uploaded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProductImageSerializer(
            created_images, many=True, context={'request': request})
        return Response(
            api_response(
                message="Images uploaded successfully.",
                status=True,
                data=serializer.data
            ),
            status=status.HTTP_201_CREATED
        )


class ProductImageListView(APIView):
    """
    API endpoint to list, update, and delete images for a product.
    - GET: List all images for a given product (public).
    - PATCH: Update an image's ordering (merchant only).
    - DELETE: Delete an image (merchant only).
    """
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="List Product Images",
        operation_description="List all images for a given product.",
        responses={200: ProductImageSerializer(many=True)}
    )
    def get(self, request, product_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=400
            )
        # Validate UUID so invalid IDs return JSON instead of HTML 404
        try:
            from uuid import UUID
            product_uuid = UUID(str(product_id))
        except Exception:
            return Response(
                api_response(
                    message="Invalid product_id.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            product = Product.objects.get(id=product_uuid)
        except Product.DoesNotExist:
            return Response(
                api_response(
                    message="Product not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        images = product.images.all().order_by('ordering', 'id')
        serializer = ProductImageSerializer(
            images, many=True, context={'request': request})
        return Response(
            api_response(
                message="Product images retrieved successfully.",
                status=True,
                data=serializer.data
            ),
            status=status.HTTP_200_OK
        )

    @swagger_auto_schema(
        operation_summary="Batch Update Product Images",
        operation_description="Update multiple product images (ordering or image file).", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "updates": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "image_id": openapi.Schema(
                                type=openapi.TYPE_INTEGER),
                            "ordering": openapi.Schema(
                                type=openapi.TYPE_INTEGER),
                            "image": openapi.Schema(
                                type=openapi.TYPE_STRING, 
                                format=openapi.FORMAT_BINARY),
                        },
                        required=["image_id"],
                    ),
                )
            },
        ),
        responses={200: ProductImageSerializer(many=True)}
    )
    def patch(self, request, product_id):
        """
        Batch update product images (ordering or file).
        """
        user = request.user

        if not user.is_authenticated:
            return Response(
                api_response("Authentication required.", False), 401)

        from uuid import UUID
        try:
            product_uuid = UUID(str(product_id))
        except Exception:
            return Response(
                api_response("Invalid product_id.", False), 400)

        try:
            product = Product.objects.get(id=product_uuid)
        except Product.DoesNotExist:
            return Response(api_response("Product not found.", False), 404)

        if product.merchant != user:
            return Response(
                api_response(
                    "You do not have permission to update this product's images.", False), 403) # noqa

        updates = request.data.get('updates')
        if not updates:
            return Response(api_response("`updates` array is required.", False), 400) # noqa

        # Handle case when request.data is QueryDict (multipart form)
        if isinstance(updates, str):
            import json
            try:
                updates = json.loads(updates)
            except json.JSONDecodeError:
                return Response(
                    api_response(
                        "Invalid JSON format in updates.",
                        False), 400)

        updated_images = []
        errors = []

        for update in updates:
            serializer = ProductImageUpdateSerializer(data=update)
            serializer.is_valid(raise_exception=True)

            image_id = serializer.validated_data["image_id"]
            ordering = serializer.validated_data.get("ordering")
            uploaded_file = serializer.validated_data.get("image") or request.FILES.get(f"image_{image_id}")  # noqa

            try:
                image_obj = product.images.get(id=image_id)
            except product.images.model.DoesNotExist:
                errors.append({"image_id": image_id, "error": "Image not found."}) # noqa
                continue

            changed = False

            if ordering is not None:
                image_obj.ordering = ordering
                changed = True

            if uploaded_file:
                resized = resize_and_save_image(uploaded_file, 400, 400)
                if resized is None:
                    errors.append(
                        {
                            "image_id": image_id, "error": "Invalid image file."}) # noqa
                    continue
                if image_obj.image:
                    image_obj.image.delete(save=False)
                image_obj.image = resized
                changed = True

            if changed:
                image_obj.save()
                updated_images.append(image_obj)

        serializer = ProductImageSerializer(
            updated_images, many=True, context={"request": request})
        return Response(
            api_response(
                "Batch product image update completed.",
                True,
                data={"updated": serializer.data, "errors": errors or None},
            ),
            200
        )

    @swagger_auto_schema(
        operation_summary="Delete Product Image",
        operation_description="Delete a product image. Only the merchant who owns the product can delete.", # noqa
        manual_parameters=[
            openapi.Parameter(
                'image_id', openapi.IN_QUERY, 
                description="ID of the image to delete",
                type=openapi.TYPE_INTEGER, required=True
            ),
        ],
        responses={204: "Product image deleted successfully."}
    )
    def delete(self, request, product_id):
        # Only authenticated merchants can delete images
        if not request.user.is_authenticated:
            return Response(
                api_response(
                    message="Authentication required.",
                    status=False
                ),
                status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            from uuid import UUID
            product_uuid = UUID(str(product_id))
        except Exception:
            return Response(
                api_response(
                    message="Invalid product_id.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            product = Product.objects.get(id=product_uuid)
        except Product.DoesNotExist:
            return Response(
                api_response(
                    message="Product not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        if product.merchant != request.user: # noqa
            return Response(
                api_response(
                    message="You do not have permission to delete images for this product.", # noqa
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN
            )
        image_id = request.query_params.get('image_id')
        if not image_id:
            return Response(
                api_response(
                    message="image_id query parameter is required.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            image_obj = product.images.get(id=image_id)
        except ProductImage.DoesNotExist:
            return Response(
                api_response(
                    message="Product image not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        image_obj.delete()
        return Response(
            api_response(
                message="Product image deleted successfully.",
                status=True,
                data={}
            ),
            status=status.HTTP_200_OK
        )


class ProductDetailView(APIView):
    """
    Retrieve, update, or delete a product by ID.

    - GET: Anyone can view product details.
    - PUT/PATCH: Only the merchant who owns the product can update it.
    - DELETE: Only the merchant who owns the product can delete it.
    """
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_description="Retrieve product details by ID",
        responses={200: ProductSerializer()}
    )
    def get(self, request, id):
        # Validate UUID so invalid IDs return JSON instead of HTML 404
        try:
            from uuid import UUID
            product_uuid = UUID(str(id))
        except Exception:
            return Response(
                api_response(
                    message="Invalid product_id.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=400
            )

        try:
            # product = Product.objects.select_related(
            #     'merchant', 'category'
            # ).prefetch_related('images').get(id=product_uuid)
            product = (
                Product.objects.select_related("merchant", "category")
                .prefetch_related(
                    Prefetch(
                        "images",
                        queryset=ProductImage.objects.order_by("ordering")
                    )
                )
                .annotate(
                    avg_rating=Avg("reviews__rating"),
                    total_purchased=Sum(
                        "orderitem__quantity",
                        filter=Q(orderitem__order__status="paid")
                    ),
                    is_in_favorite_list=Exists(
                        FavoriteProduct.objects.filter(
                            product=OuterRef("pk"), user=request.user)
                    ) if request.user.is_authenticated else None,
                    is_in_cart=Exists(
                        CartItem.objects.filter(
                            cart__user=request.user,
                            product=OuterRef("pk"))
                    ) if request.user.is_authenticated else None,
                ).get(id=product_uuid)
            )
        except Product.DoesNotExist:
            return Response(
                api_response(
                    message="Product not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = ProductSerializer(
            product, context={'request': self.request})
        return Response(api_response(
            message="Product details retrieved successfully.",
            status=True,
            data=serializer.data
        ))

    @swagger_auto_schema(
        operation_summary="Update Product Details (merchant only)",
        operation_description="Update product details (merchant only)",
        request_body=ProductSerializer,
        responses={200: ProductSerializer()}
    )
    def put(self, request, id):
        # Validate UUID so invalid IDs return JSON instead of HTML 404
        try:
            from uuid import UUID
            product_uuid = UUID(str(id))
        except Exception:
            return Response(
                api_response(
                    message="Invalid product_id.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=400
            )
        # Only authenticated merchants can update their own products
        if not request.user.is_authenticated:
            return Response(
                api_response(
                    message="Authentication required.",
                    status=False
                ),
                status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            product = Product.objects.get(id=product_uuid)
        except Product.DoesNotExist:
            return Response(
                api_response(
                    message="Product not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        if product.merchant != request.user:
            return Response(
                api_response(
                    message="You do not have permission to update this product.",  # noqa
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = ProductCreateSerializer(
            product, data=data, partial=False, context={'request': self.request})  # noqa
        if serializer.is_valid():
            serializer.save()
            return Response(api_response(
                message="Product updated successfully.",
                status=True,
                data=serializer.data
            ))
        return Response(
            api_response(
                message="Invalid data.",
                status=False,
                errors=serializer.errors
            ),
            status=status.HTTP_400_BAD_REQUEST
        )

    @swagger_auto_schema(
        operation_summary="Partially update product details (merchant only)",
        operation_description="Partially update product details (merchant only)",  # noqa
        request_body=ProductSerializer,
        responses={200: ProductSerializer()}
    )
    def patch(self, request, id):
        # Validate UUID so invalid IDs return JSON instead of HTML 404
        try:
            from uuid import UUID
            product_uuid = UUID(str(id))
        except Exception:
            return Response(
                api_response(
                    message="Invalid product_id.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        # Only authenticated merchants can update their own products
        if not request.user.is_authenticated:
            return Response(
                api_response(
                    message="Authentication required.",
                    status=False
                ),
                status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            product = Product.objects.get(id=product_uuid)
        except Product.DoesNotExist:
            return Response(
                api_response(
                    message="Product not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        if product.merchant != request.user: # noqa
            return Response(
                api_response(
                    message="You do not have permission to update this product.",  # noqa
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN
            )
        serializer = ProductSerializer(product, data=request.data, partial=True, context={'request': self.request})  # noqa
        if serializer.is_valid():
            serializer.save()
            return Response(api_response(
                message="Product updated successfully.",
                status=True,
                data=serializer.data
            ))
        return Response(
            api_response(
                message="Invalid data.",
                status=False,
                errors=serializer.errors
            ),
            status=status.HTTP_400_BAD_REQUEST
        )

    @swagger_auto_schema(
        operation_summary="Delete a product (merchant only)",
        operation_description="Delete a product (merchant only)",
        responses={204: "Product deleted successfully."}
    )
    def delete(self, request, id):
        # Validate UUID so invalid IDs return JSON instead of HTML 404
        try:
            from uuid import UUID
            product_uuid = UUID(str(id))
        except Exception:
            return Response(
                api_response(
                    message="Invalid product_id.",
                    status=False
                ),
                status=status.HTTP_400_BAD_REQUEST
            )
        # Only authenticated merchants can delete their own products
        if not request.user.is_authenticated:
            return Response(
                api_response(
                    message="Authentication required.",
                    status=False
                ),
                status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            product = Product.objects.get(id=product_uuid)
        except Product.DoesNotExist:
            return Response(
                api_response(
                    message="Product not found.",
                    status=False
                ),
                status=status.HTTP_404_NOT_FOUND
            )
        if product.merchant != request.user: # noqa
            return Response(
                api_response(
                    message="You do not have permission to delete this product.",  # noqa
                    status=False
                ),
                status=status.HTTP_403_FORBIDDEN
            )
        product.delete()
        return Response(
            api_response(
                message="Product deleted successfully.",
                status=True
            ),
            status=status.HTTP_200_OK
        )


class ProductSearchView(APIView):
    permission_classes = [permissions.AllowAny]
    pagination_class = CustomLimitOffsetPagination
    throttle_classes = [UserRateThrottle]

    def get_paginated_response(self, queryset):
        """Return paginated response"""
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, self.request)
        serializer = ProductSerializer(
            page, many=True, context={'request': self.request})
        return paginator.get_paginated_response(serializer.data)

    @swagger_auto_schema(
        operation_description="Full-text search for products (by name, description, category)", # noqa
        manual_parameters=[
            openapi.Parameter(
                'q', openapi.IN_QUERY, description="Search query",
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'page', openapi.IN_QUERY, 
                description="Page number for pagination",
                type=openapi.TYPE_INTEGER, required=False
            ),
            openapi.Parameter(
                'page_size', openapi.IN_QUERY, 
                description="Number of items per page",
                type=openapi.TYPE_INTEGER, required=False
            ),

            openapi.Parameter(
                'merchant',
                openapi.IN_QUERY,
                description="Filter by merchant user ID",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=False
            ),
            openapi.Parameter(
                'make',
                openapi.IN_QUERY,
                description="Filter by make ID",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'category',
                openapi.IN_QUERY,
                description="Filter by category ID",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
            openapi.Parameter(
                'is_rental',
                openapi.IN_QUERY,
                description="Filter by rental status (true/false)",
                type=openapi.TYPE_BOOLEAN,
                required=False
            ),
            openapi.Parameter(
                'min_price',
                openapi.IN_QUERY,
                description="Filter by minimum price",
                type=openapi.TYPE_NUMBER,
                required=False
            ),
            openapi.Parameter(
                'max_price',
                openapi.IN_QUERY,
                description="Filter by maximum price",
                type=openapi.TYPE_NUMBER,
                required=False
            ),
        ],
        responses={200: ProductSerializer(many=True)}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=400
            )
        try:
            query = request.query_params.get('q', '').strip()
            if not query:
                return Response(
                    api_response(
                        message="No search query provided.",
                        status=False,
                        data=[]
                    ),
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if we're using PostgreSQL for full-text search
            if connection.vendor == 'postgresql':
                try:
                    from django.contrib.postgres.search import (
                        SearchVector, SearchQuery, SearchRank
                    )
                    vector = (
                        SearchVector('name', weight='A') +
                        SearchVector('description', weight='B') +
                        SearchVector('category__name', weight='B')
                    )
                    search_query = SearchQuery(query)
                    queryset = Product.objects.annotate(
                        rank=SearchRank(vector, search_query)
                    ).filter(rank__gte=0.1).order_by('-rank')
                except Exception:
                    # Fallback to basic search if PostgreSQL search fails
                    queryset = Product.objects.filter(
                        Q(name__icontains=query) |
                        Q(description__icontains=query) |
                        Q(category__name__icontains=query)
                    )
            else:
                queryset = Product.objects.filter(
                    Q(name__icontains=query) |
                    Q(description__icontains=query) |
                    Q(category__name__icontains=query)
                )

            # Filtering
            merchant = request.query_params.get('merchant')
            category = request.query_params.get('category')
            is_rental = request.query_params.get('is_rental')
            min_price = request.query_params.get('min_price')
            max_price = request.query_params.get('max_price')
            make = request.query_params.get('make')

            if make:
                try:
                    queryset = queryset.filter(make__id=make)
                except (ValueError, TypeError):
                    return Response(
                        api_response(message="Invalid make ID.", status=False),
                        status=400
                    )

            if merchant:
                try:
                    queryset = queryset.filter(merchant__id=merchant)
                except (ValueError, TypeError):
                    return Response(
                        api_response(
                            message="Invalid merchant ID.", status=False),
                        status=400
                    )
            if category:
                try:
                    queryset = queryset.filter(category__id=category)
                except (ValueError, TypeError):
                    return Response(
                        api_response(
                            message="Invalid category ID.", status=False),
                        status=400
                    )
            if is_rental is not None:
                if is_rental.lower() in ['true', '1']:
                    queryset = queryset.filter(is_rental=True)
                elif is_rental.lower() in ['false', '0']:
                    queryset = queryset.filter(is_rental=False)
                else:
                    return Response(
                        api_response(
                            message="Invalid is_rental value. Use true or false.", # noqa
                            status=False),
                        status=400
                    )
            if min_price is not None:
                try:
                    min_price_val = float(min_price)
                    queryset = queryset.filter(price__gte=min_price_val)
                except (ValueError, TypeError):
                    return Response(
                        api_response(
                            message="Invalid min_price value.",
                            status=False),
                        status=400
                    )
            if max_price is not None:
                try:
                    max_price_val = float(max_price)
                    queryset = queryset.filter(price__lte=max_price_val)
                except (ValueError, TypeError):
                    return Response(
                        api_response(
                            message="Invalid max_price value.",
                            status=False),
                        status=400
                    )

            serializer = self.get_paginated_response(queryset)

            return Response(api_response(
                message="Search results retrieved successfully.",
                status=True,
                data=serializer.data
            ))
        except Exception as e:
            import traceback
            logging.debug(traceback.format_exc())
            return Response(api_response(
                message="Something went wrong.",
                status=False,
                data=str(e)
            ), status=500)


class CategoryListView(APIView):
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="List all product categories",
        operation_description="List all product categories",
        responses={200: CategorySerializer(many=True)}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False), status=400
            )
        categories = Category.objects.all()
        serializer = CategorySerializer(
            categories, many=True, context={'request': self.request})
        return Response(api_response(
            message="Category list retrieved successfully.",
            status=True,
            data=serializer.data
        ))


class HomeView(APIView):
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_summary="Home view",
        operation_description=(
            "Home view: 15 random mechanics, best selling cars, "
            "best selling spare parts. Use ?requestType=mechanics, "
            "?requestType=best_selling_cars, or ?requestType=best_selling_spare_parts " # noqa
            "to fetch only a specific section for performance."
        ),
        manual_parameters=[
            openapi.Parameter(
                'requestType',
                openapi.IN_QUERY,
                description="Specify which data to fetch: 'mechanics', 'best_selling_cars', 'best_selling_spare_parts'. If omitted, all are returned.", # noqa
                type=openapi.TYPE_STRING,
                required=False
            ),
        ],
        responses={200: HomeResponseSerializer()}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        from users.models import MechanicReview  # make sure this import is present
        from django.db.models import Subquery, OuterRef, Avg

        request_type = request.query_params.get('requestType', '').strip().lower() # noqa

        # If requestType is invalid, return error
        if request_type not in {'mechanics', 'best_selling_cars', 'best_selling_spare_parts'}: # noqa
            return Response(
                api_response(
                    message="You must specify a valid query params as requestType. Valid values: 'mechanics', 'best_selling_cars', 'best_selling_spare_parts'.", # noqa
                    status=False
                ),
                status=400
            )
        response_data = {}

        # Only fetch what is needed based on requestType for performance
        if request_type == 'mechanics':
            mechanics = (
                MechanicProfile.objects
                .select_related('user')
                .filter(is_approved=True)
                # Annotate with average mechanic rating using MechanicReview
                .annotate(
                    rating=Subquery(
                        MechanicReview.objects.filter(
                            mechanic=OuterRef('pk')
                        ).values('mechanic').annotate(
                            avg_rating=Avg('rating')
                        ).values('avg_rating')[:1]
                    )
                )
                .order_by('?')[:15]
            )
            mechanics_data = MechanicProfileSerializer(
                mechanics, many=True, context={'request': self.request}
            ).data
            response_data['mechanics'] = mechanics_data

        if request_type == 'best_selling_cars':
            best_selling_cars = (
                Product.objects.select_related("merchant", "category")
                .prefetch_related(
                    Prefetch(
                        "images",
                        queryset=ProductImage.objects.order_by("ordering")
                    )
                )
                .annotate(
                    total_sales=Coalesce(Sum("orderitem__quantity"), 0),
                    avg_rating=Avg("reviews__rating"),
                    total_purchased=Coalesce(
                        Sum(
                            "orderitem__quantity",
                            filter=Q(orderitem__order__status="paid")
                        ),
                        0
                    ),
                    is_in_favorite_list=Exists(
                        FavoriteProduct.objects.filter(
                            product=OuterRef("pk"), user=request.user
                        )
                    ) if request.user.is_authenticated else Value(
                        False, output_field=models.BooleanField()),
                    is_in_cart=Exists(
                        CartItem.objects.filter(
                            cart__user=request.user,
                            product=OuterRef("pk")
                        )
                    ) if request.user.is_authenticated else Value(
                        False, output_field=models.BooleanField()),
                )
                .filter(category__name__iexact="car")
                .order_by("-total_sales", "-created_at")[:10]
            )
            best_selling_cars_data = ProductSerializer(
                best_selling_cars, many=True, context={'request': self.request}
            ).data
            response_data['best_selling_cars'] = best_selling_cars_data

        if request_type == 'best_selling_spare_parts':
            best_selling_spare_parts = (
                Product.objects.select_related("merchant", "category")
                .prefetch_related(
                    Prefetch(
                        "images",
                        queryset=ProductImage.objects.order_by("ordering")
                    )
                )
                .annotate(
                    total_sales=Coalesce(Sum("orderitem__quantity"), 0),
                    avg_rating=Avg("reviews__rating"),
                    total_purchased=Coalesce(
                        Sum(
                            "orderitem__quantity",
                            filter=Q(orderitem__order__status="paid")
                        ),
                        0
                    ),
                    is_in_favorite_list=Exists(
                        FavoriteProduct.objects.filter(
                            product=OuterRef("pk"), user=request.user
                        )
                    ) if request.user.is_authenticated else Value(
                        False, output_field=models.BooleanField()),
                    is_in_cart=Exists(
                        CartItem.objects.filter(
                            cart__user=request.user,
                            product=OuterRef("pk")
                        )
                    ) if request.user.is_authenticated else Value(
                        False, output_field=models.BooleanField()),
                )
                .filter(category__name__iexact="spare part")
                .order_by("-total_sales", "-created_at")[:10]
            )
            best_selling_spare_parts_data = ProductSerializer(
                best_selling_spare_parts, many=True, 
                context={'request': self.request}
            ).data
            response_data['best_selling_spare_parts'] = best_selling_spare_parts_data # noqa

        return Response(
            api_response(
                message="Home data retrieved successfully.",
                status=True,
                data=response_data
            ),
            status=200
        )


class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="View the authenticated user's cart",
        operation_description="View the authenticated user's cart",
        responses={200: CartSerializer()}
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        cart, _ = Cart.objects.get_or_create(user=request.user)
        serializer = CartSerializer(cart, context={'request': request})
        return Response(
            api_response(
                message="Cart retrieved successfully.",
                status=True,
                data=serializer.data
            )
        )

    @swagger_auto_schema(
        operation_summary="Add to Cart",
        operation_description=(
            "Add or update a cart item (product_id, quantity). "
            "If item exists, quantity is set. "
            "To increment/decrement, use PATCH. "
            "To remove, use DELETE."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (e.g., 'inbound', 'outbound')"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['product_id', 'quantity'],
                    properties={
                        'product_id': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format='uuid',
                            description="UUID of the product to add/update"
                        ),
                        'quantity': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="Quantity of the product"
                        ),
                    }
                ),
            }
        ),
        responses={200: CartSerializer()}
    )
    def post(self, request):
        try:
            status_, data = incoming_request_checks(request)
            if not status_:
                return Response(
                    api_response(message=data, status=False),
                    status=400
                )
            cart, _ = Cart.objects.get_or_create(user=request.user)
            product_id = data.get('product') or data.get('product_id')
            quantity = data.get('quantity', 1)
            if not product_id:
                return Response(
                    api_response(message="Product is required.", status=False),
                    status=400
                )
            if quantity < 1:
                return Response(
                    api_response(
                        message="Quantity must be at least 1.", 
                        status=False),
                    status=400
                )
            try:
                with transaction.atomic():
                    # Lock the product row for update to prevent race conditions # noqa
                    product_obj = (
                        Product.objects
                        .select_for_update()
                        .get(id=product_id)
                    )
                    if product_obj.stock is not None and quantity > product_obj.stock: # noqa
                        return Response(
                            api_response(
                                message="Not enough stock available.",
                                status=False
                            ),
                            status=400
                        )
                    cart_item, created = CartItem.objects.select_for_update().get_or_create( # noqa
                        cart=cart, product=product_obj
                    )
                    cart_item.quantity = quantity
                    cart_item.save()
            except Product.DoesNotExist:
                return Response(
                    api_response(message="Product not found.", status=False),
                    status=404
                )
            serializer = CartSerializer(cart, context={'request': request})
            return Response(
                api_response(
                    message="Cart updated successfully.",
                    status=True,
                    data=serializer.data
                )
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Error in cart update: {str(e)}\n{tb_str}")
            return Response(
                api_response(
                    message="An error occurred while updating the cart.",
                    status=False,
                    errors={"traceback": tb_str}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @swagger_auto_schema(
        operation_summary="Increment/Decrement Cart Item Quantity",
        operation_description=(
            "Increment or decrement a cart item's quantity. "
            "Send product_id and 'action' ('increment' or 'decrement'). "
            "If decrementing to 0, item will be removed."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (e.g., 'inbound', 'outbound')"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['product_id', 'action'],
                    properties={
                        'product_id': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format='uuid',
                            description="Product ID to increment/decrement"
                        ),
                        'action': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            enum=['increment', 'decrement'],
                            description="Action to perform"
                        )
                    }
                )
            }
        ),
        responses={200: CartSerializer()}
    )
    def patch(self, request):
        try:
            status_, data = incoming_request_checks(request)
            if not status_:
                return Response(
                    api_response(message=data, status=False),
                    status=400
                )
            cart, _ = Cart.objects.get_or_create(user=request.user)
            product_id = data.get('product_id')
            action = data.get('action')
            if not product_id or action not in ['increment', 'decrement']:
                return Response(
                    api_response(
                        message="product_id and valid action required.", 
                        status=False),
                    status=400
                )
            try:
                with transaction.atomic():
                    cart_item = CartItem.objects.select_for_update().get(
                        cart=cart, product_id=product_id
                    )
                    if action == 'increment':
                        # Check stock
                        product_obj = Product.objects.get(id=product_id)
                        if product_obj.stock is not None and cart_item.quantity + 1 > product_obj.stock: # noqa
                            return Response(
                                api_response(
                                    message="Not enough stock available.",
                                    status=False
                                ),
                                status=400
                            )
                        cart_item.quantity += 1
                        cart_item.save()
                    elif action == 'decrement':
                        if cart_item.quantity > 1:
                            cart_item.quantity -= 1
                            cart_item.save()
                        else:
                            cart_item.delete()
            except CartItem.DoesNotExist:
                return Response(
                    api_response(message="Cart item not found.", status=False),
                    status=404
                )
            except Product.DoesNotExist:
                return Response(
                    api_response(message="Product not found.", status=False),
                    status=404
                )
            serializer = CartSerializer(cart, context={'request': request})
            return Response(
                api_response(
                    message="Cart updated successfully.",
                    status=True,
                    data=serializer.data
                )
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            logger.error(f"Error in cart update: {str(e)}\n{tb_str}")
            return Response(
                api_response(
                    message="An error occurred while updating the cart.",
                    status=False,
                    errors={"traceback": tb_str}
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @swagger_auto_schema(
        operation_summary="Remove Cart Item or Clear Cart",
        operation_description="Remove a cart item (by product_id) or clear cart if no product_id", # noqa
        manual_parameters=[
            openapi.Parameter(
                'product_id',
                openapi.IN_QUERY,
                description="Product ID to remove",
                type=openapi.TYPE_STRING,
                format='uuid',
                required=False
            )
        ],
        responses={200: CartSerializer()}
    )
    def delete(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        cart, _ = Cart.objects.get_or_create(user=request.user)
        product_id = request.query_params.get('product_id')
        if product_id:
            try:
                product_obj = Product.objects.get(id=product_id)
                CartItem.objects.filter(cart=cart, product=product_obj).delete() # noqa
            except Product.DoesNotExist:
                return Response(
                    api_response(message="Product not found.", status=False),
                    status=404
                )
        else:
            cart.items.all().delete()
        serializer = CartSerializer(cart, context={'request': request})
        return Response(
            api_response(
                message="Cart updated successfully.",
                status=True,
                data=serializer.data
            )
        )


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Checkout: create an order from the cart. "
            "Requires payment_method (online/cash_on_delivery)"
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['payment_method'],
                    properties={
                        'payment_method': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            enum=['online', 'cash_on_delivery'],
                            description=(
                                'Payment method: online (Paystack) or cash_on_delivery' # noqa
                            )
                        ),
                        'mobile_callback_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description=(
                                'myapp://payment-callback' # noqa
                            )
                        ),
                    }
                ),
            },
        ),
        responses={201: OrderSerializer()}
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        payment_method = data.get('payment_method')
        if payment_method not in ['online', 'cash_on_delivery']:
            return Response(
                api_response(message="Invalid payment method.", status=False),
                status=400
            )
        cart, _ = Cart.objects.get_or_create(user=request.user)
        if not cart.items.exists():
            return Response(
                api_response(message="Cart is empty.", status=False),
                status=400
            )

        # --- PRODUCTION-GRADE LOGIC ---
        # 1. For online payment, do NOT clear cart or decrement stock until payment is successful.  # noqa
        # 2. For cash_on_delivery, proceed as before.

        if payment_method == 'cash_on_delivery':
            try:
                with transaction.atomic():
                    # Lock all products in the cart for update to prevent race conditions # noqa
                    product_ids = list(
                        cart.items.values_list('product_id', flat=True)
                    )
                    products = (
                        Product.objects
                        .select_for_update()
                        .filter(id__in=product_ids)
                    )
                    product_map = {p.id: p for p in products}
                    # Check stock for all items
                    for item in cart.items.select_related('product'):
                        product = product_map.get(item.product_id)
                        if product is None:
                            raise ValidationError(
                                f"Product with id {item.product_id} not found."
                            )
                        if (
                            product.stock is not None and
                            item.quantity > product.stock
                        ):
                            raise ValidationError(
                                f"Not enough stock for product "
                                f"'{product.name}'."
                            )
                    # Create order
                    order = Order.objects.create(
                        customer=request.user,
                        payment_method=payment_method,
                        status='pending',
                        payment_status='pending',
                    )
                    total = 0
                    merchant_emails = set()
                    for item in cart.items.select_related('product'):
                        product = product_map[item.product_id]
                        price = product.price
                        total += price * item.quantity
                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            quantity=item.quantity,
                            price=price
                        )
                        # Decrement stock
                        if product.stock is not None:
                            product.stock = F('stock') - item.quantity
                            product.save(update_fields=['stock'])
                        # Collect merchant emails
                        if hasattr(product, 'merchant') and product.merchant.email: # noqa
                            merchant_emails.add(product.merchant.email)
                    order.total_amount = total
                    order.save()
                    cart.items.all().delete()
            except ValidationError as e:
                # Make error message readable if it's a list (e.g., ["Not enough stock ..."]) # noqa
                error_message = str(e)
                if (
                    error_message.startswith("[") and
                    error_message.endswith("]") and
                    len(error_message) > 2
                ):
                    try:
                        import ast
                        parsed = ast.literal_eval(error_message)
                        if isinstance(parsed, list) and len(parsed) == 1:
                            error_message = parsed[0]
                    except Exception:
                        pass
                return Response(
                    api_response(message=error_message, status=False),
                    status=400
                )
            serializer = OrderSerializer(order, context={'request': request})

            # Send order confirmation email asynchronously
            send_order_confirmation_email.delay(
                str(order.id), request.user.email
            )
            # Notify all merchants of the new order
            for merchant_email in merchant_emails:
                send_merchant_new_order_email.delay(
                    str(order.id), merchant_email
                )
            return Response(
                api_response(
                    message="Order created successfully (Cash on Delivery).",
                    status=True,
                    data=serializer.data
                ),
                status=201
            )

        # --- ONLINE PAYMENT LOGIC ---
        # For online payment, do NOT clear cart or decrement stock until payment is confirmed. # noqa
        # Instead, check stock, create a "pending" order, but do NOT decrement stock or clear cart yet. # noqa
        try:
            with transaction.atomic():
                # Lock all products in the cart for update to prevent race conditions # noqa
                product_ids = list(
                    cart.items.values_list('product_id', flat=True)
                )
                products = (
                    Product.objects
                    .select_for_update()
                    .filter(id__in=product_ids)
                )
                product_map = {p.id: p for p in products}
                # Check stock for all items
                for item in cart.items.select_related('product'):
                    product = product_map.get(item.product_id)
                    if product is None:
                        raise ValidationError(
                            f"Product with id {item.product_id} not found."
                        )
                    if (
                        product.stock is not None and
                        item.quantity > product.stock
                    ):
                        raise ValidationError(
                            f"Not enough stock for product "
                            f"'{product.name}'."
                        )
                # Create order (do NOT decrement stock or clear cart yet)
                order = Order.objects.create(
                    customer=request.user,
                    payment_method=payment_method,
                    status='pending',
                    payment_status='pending',
                )
                total = 0
                merchant_emails = set()
                for item in cart.items.select_related('product'):
                    product = product_map[item.product_id]
                    price = product.price
                    total += price * item.quantity
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=item.quantity,
                        price=price
                    )
                    # Do NOT decrement stock yet
                    # Collect merchant emails
                    if hasattr(product, 'merchant') and product.merchant.email:
                        merchant_emails.add(product.merchant.email)
                order.total_amount = total
                order.save()
        except ValidationError as e:
            # Make error message readable if it's a list (e.g., ["Not enough stock ..."]) # noqa
            error_message = str(e)
            if (
                error_message.startswith("[") and
                error_message.endswith("]") and
                len(error_message) > 2
            ):
                try:
                    import ast
                    parsed = ast.literal_eval(error_message)
                    if isinstance(parsed, list) and len(parsed) == 1:
                        error_message = parsed[0]
                except Exception:
                    pass
            return Response(
                api_response(message=error_message, status=False),
                status=400
            )
        serializer = OrderSerializer(order, context={'request': request})

        # Only initialize payment if order is online and not already paid
        if order.payment_method != 'online' or order.payment_status == 'paid':
            return Response(
                api_response(
                    message="Invalid order for payment.",
                    status=False
                ),
                status=400
            )
        # Initialize Paystack transaction for both web and mobile apps

        paystack_secret = settings.PAYSTACK_SECRET_KEY
        callback_url = settings.PAYSTACK_CALLBACK_URL

        # For mobile: allow a custom callback URL from the app, fallback to default # noqa
        mobile_callback = (
            data.get('mobile_callback_url')
            or request.query_params.get('mobile_callback_url')
        )
        # Format: e.g., "myapp://payment-callback" (deep link for mobile)
        if mobile_callback:
            callback_url = mobile_callback

        headers = {
            'Authorization': f'Bearer {paystack_secret}',
            'Content-Type': 'application/json',
        }

        # Paystack expects callback_url to be HTTP(S) but for mobile apps,
        # deep links are supported if using webview or app redirection flows.
        # e.g., mobile_callback_url = "myapp://payment-callback"
        # or "https://yourfrontend.app.com/payment/callback"
        metadata = (
            request.data.get('metadata')
            or request.query_params.get('metadata')
        )
        payload = {
            'email': request.user.email,
            'amount': int(order.total_amount * 100),  # Paystack expects kobo
            'reference': str(order.id),
            'callback_url': callback_url,
        }
        if metadata:
            payload['metadata'] = metadata

        try:
            resp = requests.post(
                'https://api.paystack.co/transaction/initialize',
                json=payload,
                headers=headers,
                timeout=15  # Set a timeout for production reliability
            )
        except requests.RequestException as e:
            # Network failure, do NOT clear cart or decrement stock or finalize order # noqa
            order.status = 'failed'
            order.payment_status = 'failed'
            order.save(update_fields=['status', 'payment_status'])
            return Response(
                api_response(
                    message=(
                        "Network error: Failed to initialize payment. "
                        "Please try again."
                    ),
                    status=False,
                    data=str(e)
                ),
                status=502
            )
        if resp.status_code != 200:
            # Payment initialization failed, do NOT clear cart or decrement stock or finalize order # noqa
            order.status = 'failed'
            order.payment_status = 'failed'
            order.save(update_fields=['status', 'payment_status'])
            try:
                error_detail = resp.json()
            except Exception:
                error_detail = {}
            return Response(
                api_response(
                    message="Failed to initialize payment.",
                    status=False,
                    errors=error_detail
                ),
                status=400
            )
        resp_data = resp.json().get('data', {})
        order.payment_reference = resp_data.get('reference')
        order.save(update_fields=['payment_reference'])

        responses_dict = {
            'payment_reference': resp_data.get('reference'),
            'payment_url': resp_data.get('authorization_url'),
        }

        # Do NOT send order confirmation or merchant notification yet.
        # These will be sent after payment is confirmed by webhook.

        return Response(
            api_response(
                message="Order created successfully. Please complete payment to finalize your order.", # noqa
                status=True,
                data={**serializer.data, **responses_dict}
            ),
            status=201
        )


class PaystackWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        # Paystack sends event data in request.data
        event = request.data.get('event')
        data = request.data.get('data', {})
        reference = data.get('reference')
        if event == 'charge.success' and reference:
            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(
                        payment_reference=reference
                    )
                    if order.payment_status != 'paid':
                        # Double check: verify amount paid matches order
                        amount_paid = int(data.get('amount', 0)) / 100.0
                        if float(amount_paid) < float(order.total_amount):
                            # Optionally, mark as failed/partial
                            order.payment_status = 'failed'
                            order.status = 'failed'
                            order.save(update_fields=['payment_status', 'status'])  # noqa
                            return Response({'status': False, 'message': 'Amount paid does not match order total.'}, status=400) # noqa

                        order.payment_status = 'paid'
                        order.status = 'paid'
                        order.paid_at = timezone.now()
                        order.save()

                        # Decrement stock and clear cart atomically
                        cart = Cart.objects.filter(user=order.customer).first()
                        if cart:
                            product_ids = list(
                                cart.items.values_list('product_id', flat=True)
                            )
                            products = (
                                Product.objects
                                .select_for_update()
                                .filter(id__in=product_ids)
                            )
                            product_map = {p.id: p for p in products}
                            for item in cart.items.select_related('product'):
                                product = product_map.get(item.product_id)
                                if product and product.stock is not None:
                                    product.stock = F('stock') - item.quantity
                                    product.save(update_fields=['stock'])
                            cart.items.all().delete()

                        # Send order confirmation email asynchronously
                        send_order_confirmation_email.delay(
                            str(order.id), order.customer.email
                        )
                        # Notify all merchants of the new order
                        merchant_emails = set()
                        for order_item in order.items.select_related('product'): # noqa
                            product = order_item.product
                            if hasattr(product, 'merchant') and product.merchant.email: # noqa
                                merchant_emails.add(product.merchant.email)
                        for merchant_email in merchant_emails:
                            send_merchant_new_order_email.delay(
                                str(order.id), merchant_email
                            )
            except Order.DoesNotExist:
                return Response(
                    {'status': False, 'message': 'Order not found.'}, status=404)  # noqa
            except Exception as e:
                # Log error in production
                return Response({'status': False, 'message': str(e)}, status=500) # noqa
        return Response({'status': True})


class PaystackPaymentInitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Initialize Paystack payment for an order (online payment)", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['order_id'],
                    properties={
                        'order_id': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="ID of the order to initialize payment for"  # noqa
                        )
                    }
                ),
            },
        ),
        responses={200: openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'payment_reference': openapi.Schema(type=openapi.TYPE_STRING),
                'payment_url': openapi.Schema(type=openapi.TYPE_STRING),
            }
        )}
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        order_id = data.get('order_id')
        try:
            order = Order.objects.get(id=order_id, customer=request.user)
        except Order.DoesNotExist:
            return Response(
                api_response(message="Order not found.", status=False),
                status=404
            )
        if order.payment_method != 'online' or order.payment_status == 'paid':
            return Response(
                api_response(
                    message="Invalid order for payment.",
                    status=False
                ),
                status=400
            )
        # Initialize Paystack transaction
        paystack_secret = settings.PAYSTACK_SECRET_KEY
        callback_url = settings.PAYSTACK_CALLBACK_URL
        headers = {
            'Authorization': f'Bearer {paystack_secret}',
            'Content-Type': 'application/json',
        }
        payload = {
            'email': request.user.email,
            'amount': int(order.total_amount * 100),  # Paystack expects kobo
            'reference': str(order.id),
            'callback_url': callback_url,
        }
        resp = requests.post(
            'https://api.paystack.co/transaction/initialize',
            json=payload,
            headers=headers
        )
        if resp.status_code != 200:
            print(resp.json())
            return Response(
                api_response(
                    message="Failed to initialize payment.",
                    status=False
                ),
                status=400
            )
        resp_data = resp.json().get('data', {})
        order.payment_reference = resp_data.get('reference')
        order.save()
        return Response(
            api_response(
                message="Payment initialized.",
                status=True,
                data={
                    'payment_reference': resp_data.get('reference'),
                    'payment_url': resp_data.get('authorization_url'),
                }
            )
        )


class OrderListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="List all orders for the authenticated user, or all orders for one of the user's merchant accounts (if merchant_id is provided as a query parameter). You can also filter by order status (pending, paid, shipped, completed, cancelled) via the 'status' query parameter.", # noqa
        manual_parameters=[
            openapi.Parameter(
                name='merchant_id',
                in_=openapi.IN_QUERY,
                description="ID of the merchant (user id) whose orders will be listed. If not provided, returns orders for currently authenticated user as a customer.", # noqa
                type=openapi.TYPE_STRING,
                required=False
            ),
            openapi.Parameter(
                name='status',
                in_=openapi.IN_QUERY,
                description="Filter orders by status (pending, paid, shipped, completed, cancelled).", # noqa
                type=openapi.TYPE_STRING,
                required=False
            ),
        ],
        responses={200: OrderSerializer(many=True)}
    )
    def get(self, request):
        """
        Returns:
            - All orders where the authenticated user is the customer (default)
            - If `merchant_id` is provided and belongs to current user (or current user is merchant), returns all orders containing products owned by the merchant. # noqa
            - You can also filter the list by order status using the 'status' query parameter. # noqa
        """
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )

        merchant_id = request.query_params.get('merchant_id', None)
        status_filter = request.query_params.get('status', None)
        VALID_ORDER_STATUSES = {'pending', 'paid', 'shipped', 'completed', 'cancelled'} # noqa

        if status_filter is not None:
            status_filter = status_filter.lower()
            if status_filter not in VALID_ORDER_STATUSES:
                return Response(
                    api_response(
                        message=f"Invalid status filter: '{status_filter}'. Allowed values: {', '.join(VALID_ORDER_STATUSES)}.", status=False), # noqa
                    status=400
                )

        if merchant_id:
            # Only allow if the current user is the merchant or superuser
            if not (str(request.user.id) == str(merchant_id) or request.user.is_staff): # noqa
                return Response(
                    api_response(message="Permission denied: You cannot query orders for this merchant.", status=False), # noqa
                    status=403
                )
            order_ids = (
                Order.objects
                .filter(items__product__merchant_id=merchant_id)
                .distinct()
                .values_list('id', flat=True)
            )
            orders = (
                Order.objects
                .filter(id__in=order_ids)
                .prefetch_related(
                    'items',
                    'items__product',
                    'items__product__merchant',
                )
                .select_related('customer')
                .order_by('-created_at')
            )
        else:
            # Default: show all orders for authenticated customer (you)
            orders = (
                Order.objects
                .filter(customer=request.user)
                .prefetch_related(
                    'items',
                    'items__product',
                    'items__product__merchant'
                )
                .select_related('customer')
                .order_by('-created_at')
            )
        if status_filter is not None:
            orders = orders.filter(status=status_filter)

        serializer = OrderSerializer(orders, many=True)
        return Response(
            api_response(
                message="Order list retrieved successfully.",
                status=True,
                data=serializer.data
            )
        )


class OrderStatusUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Update order status (shipped, completed, cancelled, etc.)",  # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (inbound/outbound)"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['status'],
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            enum=['pending', 'paid', 'shipped', 'completed', 'cancelled'],  # noqa
                            description='New order status'
                        )
                    }
                ),
            },
        ),
        responses={200: OrderSerializer()}
    )
    def post(self, request, order_id):
        """
        Update the status of a particular order.
        Only merchants related to the order or staff are allowed to update.
        """
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST
            )

        new_status = data.get('status')
        if not new_status:
            return Response(
                api_response(message="Missing status field.", status=False),
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(id=order_id)

                # Production role checks
                is_merchant = order.items.filter(
                    product__merchant=request.user).exists()
                is_staff = getattr(request.user, 'is_staff', False)

                if not (is_merchant or is_staff):
                    return Response(
                        api_response(
                            message="You do not have permission to update this order's status.", # noqa
                            status=False
                        ),
                        status=status.HTTP_403_FORBIDDEN
                    )

                # Define allowed statuses for roles
                merchant_allowed = {'shipped', 'completed', 'cancelled'}
                staff_allowed = {'pending', 'paid', 'shipped', 'completed', 'cancelled'} # noqa

                if is_merchant:
                    allowed_statuses = merchant_allowed
                    error_msg = "Merchants can only mark orders as 'shipped', 'completed', or 'cancelled'." # noqa
                    error_code = status.HTTP_403_FORBIDDEN
                elif is_staff:
                    allowed_statuses = staff_allowed
                    error_msg = "Invalid status for staff."
                    error_code = status.HTTP_400_BAD_REQUEST
                else:
                    # Should not reach here due to previous check
                    return Response(
                        api_response(message="Not allowed.", status=False),
                        status=status.HTTP_403_FORBIDDEN
                    )

                if new_status not in allowed_statuses:
                    return Response(
                        api_response(message=error_msg, status=False),
                        status=error_code
                    )

                # Valid status transitions mapping
                valid_transitions = {
                    'pending': {'paid', 'cancelled'},
                    'paid': {'shipped', 'cancelled'},
                    'shipped': {'completed', 'cancelled'},
                    'completed': set(),
                    'cancelled': set(),
                }
                current_status = order.status
                if new_status not in valid_transitions.get(current_status, set()): # noqa
                    return Response(
                        api_response(
                            message=f"Invalid status transition from '{current_status}' to '{new_status}'.",  # noqa
                            status=False
                        ),
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Update order status and related fields
                order.status = new_status
                if new_status == 'paid':
                    order.payment_status = 'paid'
                    order.paid_at = timezone.now()
                order.save()

        except Order.DoesNotExist:
            return Response(
                api_response(message="Order not found.", status=False),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as exc:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.exception(f"Error updating order status for order {order_id}: {exc}\n{traceback.format_exc()}") # noqa
            return Response(
                api_response(message="An unexpected error occurred.", status=False), # noqa
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        serializer = OrderSerializer(order)

        # Send notifications asynchronously - never block
        try:
            send_order_status_update_email.delay(
                str(order.id), order.customer.email, order.status
            )
            if order.status == 'shipped':
                send_customer_order_shipped_email.delay(
                    str(order.id), order.customer.email
                )
            elif order.status == 'completed':
                send_customer_order_completed_email.delay(
                    str(order.id), order.customer.email
                )
            elif order.status == 'cancelled':
                merchant_emails = set(
                    item.product.merchant.email
                    for item in order.items.select_related('product__merchant')
                    if getattr(item.product, 'merchant', None) and item.product.merchant.email  # noqa
                )
                for merchant_email in merchant_emails:
                    send_merchant_order_cancelled_email.delay(
                        str(order.id), merchant_email
                    )
            if getattr(order, 'payment_status', None) == 'refunded':
                send_customer_refund_email.delay(
                    str(order.id), order.customer.email
                )
        except Exception as exc:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.warning(f"Order status updated but notification failed for order {order_id}: {exc}\n{traceback.format_exc()}")  # noqa

        return Response(
            api_response(
                message="Order status updated successfully.",
                status=True,
                data=serializer.data
            ),
            status=status.HTTP_200_OK
        )

    @swagger_auto_schema(
        operation_description="Retrieve the details of a particular order.",
        responses={200: OrderSerializer()}
    )
    def get(self, request, order_id):
        """
        Retrieve details of a particular order.
        - Staff can view any order.
        - Merchants can view orders containing their products.
        - Customers can view their own orders.
        """
        try:
            order = Order.objects.prefetch_related(
                'items',
                'items__product',
                'items__product__merchant'
            ).select_related('customer').get(id=order_id)

            user = request.user
            is_merchant = order.items.filter(product__merchant=user).exists()
            is_staff = getattr(user, 'is_staff', False)
            is_customer = order.customer == user

            if not (is_staff or is_merchant or is_customer):
                return Response(
                    api_response(
                        message="You do not have permission to view this order.", # noqa
                        status=False
                    ),
                    status=status.HTTP_403_FORBIDDEN
                )
            serializer = OrderSerializer(order)
            return Response(
                api_response(
                    message="Order details retrieved successfully.",
                    status=True,
                    data=serializer.data
                ),
                status=status.HTTP_200_OK
            )
        except Order.DoesNotExist:
            return Response(
                api_response(message="Order not found.", status=False),
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as exc:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.exception(f"Error retrieving order details for order {order_id}: {exc}\n{traceback.format_exc()}") # noqa
            return Response(
                api_response(message="An unexpected error occurred.", status=False), # noqa
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProductReviewListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    @swagger_auto_schema(
        operation_description="List and create reviews for a product",
        responses={200: ProductReviewSerializer(many=True)},
    )
    def get(self, request, product_id):
        reviews = ProductReview.objects.filter(
            product_id=product_id
        ).order_by('-created_at')
        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(
            api_response(
                message="Product reviews retrieved successfully.",
                status=True,
                data=serializer.data
            )
        )

    @swagger_auto_schema(
        operation_description="Create a new review for a product. Expects requestType and data keys in the request body.", # noqa
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (e.g., 'inbound', 'outbound')"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['rating', 'comment'],
                    properties={
                        'rating': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="Rating for the product (e.g., 1-5)"
                        ),
                        'comment': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Review comment"
                        ),
                    }
                ),
            }
        ),
        responses={
            201: ProductReviewSerializer(),
            400: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'message': openapi.Schema(type=openapi.TYPE_STRING),
                    'status': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'errors': openapi.Schema(type=openapi.TYPE_OBJECT),
                }
            ),
        },
    )
    def post(self, request, product_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        serializer = ProductReviewSerializer(
            data=data,
            context={'request': request}
        )
        if serializer.is_valid():
            review = serializer.save(user=request.user, product_id=product_id)
            # Send new review notification email asynchronously to merchant
            merchant_email = (
                review.product.merchant.email
                if hasattr(review.product, 'merchant') else None
            )
            if merchant_email:
                send_new_review_notification_email.delay(
                    str(product_id), merchant_email
                )
            return Response(
                api_response(
                    message="Review created successfully.",
                    status=True,
                    data=serializer.data
                ),
                status=201
            )
        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=400
        )


class MerchantAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get comprehensive analytics for the authenticated merchant",  # noqa
        responses={
            200: openapi.Response(
                description="Merchant analytics",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'total_sales': openapi.Schema(
                            type=openapi.TYPE_NUMBER
                        ),
                        'order_count': openapi.Schema(
                            type=openapi.TYPE_INTEGER
                        ),
                        'order_status_counts': openapi.Schema(
                            type=openapi.TYPE_OBJECT
                        ),
                        'product_count': openapi.Schema(
                            type=openapi.TYPE_INTEGER
                        ),
                        'rental_products': openapi.Schema(
                            type=openapi.TYPE_INTEGER
                        ),
                        'best_selling_products': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Items(type=openapi.TYPE_STRING)
                        ),
                        'revenue_by_month': openapi.Schema(
                            type=openapi.TYPE_OBJECT
                        ),
                        'rental_analytics': openapi.Schema(
                            type=openapi.TYPE_OBJECT
                        ),
                        'customer_insights': openapi.Schema(
                            type=openapi.TYPE_OBJECT
                        ),
                        'product_performance': openapi.Schema(
                            type=openapi.TYPE_OBJECT
                        ),
                    }
                )
            )
        }
    )
    def get(self, request):
        from django.db import connection
        from django.db.models.functions import TruncMonth

        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )
        user = request.user
        if not user.roles.filter(name='merchant').exists():
            return Response(
                api_response(
                    message="Only merchants can access analytics.",
                    status=False
                ),
                status=403
            )

        # Product analytics
        product_count = Product.objects.filter(merchant=user).count()
        rental_products = Product.objects.filter(
            merchant=user, is_rental=True).count()

        # Order analytics
        order_items = OrderItem.objects.filter(product__merchant=user)
        order_ids = order_items.values_list('order_id', flat=True).distinct()
        orders = Order.objects.filter(id__in=order_ids)

        # Sales analytics
        total_sales = order_items.filter(
            order__status__in=['paid', 'shipped', 'completed']
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    F('price') * F('quantity'),
                    output_field=DecimalField(
                        max_digits=12,
                        decimal_places=2
                    )
                )
            )
        )['total'] or 0

        order_count = orders.count()
        order_status_counts = (
            orders.values('status')
            .annotate(count=Count('id'))
        )
        status_counts = {
            item['status']: item['count']
            for item in order_status_counts
        }

        # Best-selling products
        best_selling = (
            order_items.values('product__name')
            .annotate(total_quantity=Sum('quantity'))
            .order_by('-total_quantity')[:5]
        )
        best_selling_products = [
            item['product__name'] for item in best_selling
        ]

        # Revenue by month (handle both Postgres and SQLite)
        db_engine = connection.vendor  # 'postgresql', 'sqlite', etc.

        if db_engine == 'postgresql':
            # Use DATE_TRUNC for Postgres
            class TruncMonthPG(Func):
                function = 'DATE_TRUNC'
                template = "%(function)s('month', %(expressions)s)"
            month_annotate = TruncMonthPG('order__created_at')
        elif db_engine == 'sqlite':
            # Use strftime for SQLite
            class TruncMonthSQLite(Func):
                function = 'strftime'
                template = "%(function)s('%%Y-%%m-01', %(expressions)s)"
            month_annotate = TruncMonthSQLite('order__created_at')
        else:
            # Fallback to Django's TruncMonth (works for supported backends)
            month_annotate = TruncMonth('order__created_at')

        try:
            revenue_by_month = order_items.filter(
                order__status__in=['paid', 'shipped', 'completed']
            ).annotate(
                month=month_annotate
            ).values('month').annotate(
                revenue=Sum(
                    ExpressionWrapper(
                        F('price') * F('quantity'),
                        output_field=DecimalField(
                            max_digits=12,
                            decimal_places=2
                        )
                    )
                )
            ).order_by('month')

            # For SQLite, month is a string, for Postgres it's a datetime
            revenue_by_month_dict = {}
            for item in revenue_by_month:
                month_val = item['month']
                if db_engine == 'sqlite':
                    # month_val is 'YYYY-MM-01'
                    key = month_val
                elif db_engine == 'postgresql':
                    # month_val is a datetime/date
                    key = str(item['month'].date())
                else:
                    # fallback
                    key = str(item['month'])
                revenue_by_month_dict[key] = float(item['revenue'])
        except Exception as e:
            # Fallback: empty dict if error
            logging.info(str(e))
            revenue_by_month_dict = {}

        # Rental analytics
        rental_analytics = self._get_rental_analytics(user)

        # Customer insights
        customer_insights = self._get_customer_insights(user)

        # Product performance
        product_performance = self._get_product_performance(user)

        return Response(
            api_response(
                message="Merchant analytics retrieved successfully.",
                status=True,
                data={
                    'total_sales': float(total_sales),
                    'order_count': order_count,
                    'order_status_counts': status_counts,
                    'product_count': product_count,
                    'rental_products': rental_products,
                    'best_selling_products': best_selling_products,
                    'revenue_by_month': revenue_by_month_dict,
                    'rental_analytics': rental_analytics,
                    'customer_insights': customer_insights,
                    'product_performance': product_performance,
                }
            )
        )

    def _get_rental_analytics(self, user):
        """Get rental-specific analytics for merchant"""
        try:
            from rentals.models import RentalBooking

            # Rental bookings for merchant's products
            rental_bookings = RentalBooking.objects.filter(
                product__merchant=user
            )

            total_rentals = rental_bookings.count()
            completed_rentals = rental_bookings.filter(
                status='completed').count()
            active_rentals = rental_bookings.filter(status='active').count()
            pending_rentals = rental_bookings.filter(status='pending').count()

            # Rental revenue
            rental_revenue = rental_bookings.filter(
                status__in=['completed', 'active']
            ).aggregate(
                total=Sum('total_amount')
            )['total'] or 0

            # Average rental duration
            from django.db.models import F, ExpressionWrapper, fields
            from django.db.models.functions import Cast

            completed_rentals = rental_bookings.filter(
                status='completed').annotate(
                duration=ExpressionWrapper(
                    F('end_date') - F('start_date'),
                    output_field=fields.DurationField()
                )
            )

            # Calculate average duration in days
            avg_duration = completed_rentals.aggregate(
                avg_duration=Avg(
                    ExpressionWrapper(
                        Cast(F('duration'), output_field=fields.DurationField()) / 86400.0,  # noqa
                        output_field=fields.FloatField()
                    )
                )
            )['avg_duration'] or 0

            return {
                'total_rentals': total_rentals,
                'completed_rentals': completed_rentals,
                'active_rentals': active_rentals,
                'pending_rentals': pending_rentals,
                'rental_revenue': float(rental_revenue),
                'avg_rental_duration': float(avg_duration),
                'completion_rate': (
                    completed_rentals / total_rentals * 100) if total_rentals > 0 else 0 # noqa
            }
        except ImportError:
            return {}

    def _get_customer_insights(self, user):
        """Get customer insights for merchant"""
        # Unique customers
        unique_customers = Order.objects.filter(
            items__product__merchant=user
        ).values('customer').distinct().count()

        # Repeat customers (customers with multiple orders)
        repeat_customers = Order.objects.filter(
            items__product__merchant=user
        ).values('customer').annotate(
            order_count=Count('id')
        ).filter(order_count__gt=1).count()

        # Average order value
        avg_order_value = Order.objects.filter(
            items__product__merchant=user,
            status__in=['paid', 'shipped', 'completed']
        ).aggregate(
            avg_value=Avg('total_amount')
        )['avg_value'] or 0

        # Customer retention rate
        retention_rate = (repeat_customers / unique_customers * 100) if unique_customers > 0 else 0  # noqa

        return {
            'unique_customers': unique_customers,
            'repeat_customers': repeat_customers,
            'avg_order_value': float(avg_order_value),
            'retention_rate': retention_rate,
            'repeat_customer_rate': retention_rate
        }

    def _get_product_performance(self, user):
        """Get product performance metrics"""
        from django.db.models import Avg

        # Product performance metrics
        products = Product.objects.filter(merchant=user)

        # Products with reviews
        products_with_reviews = products.filter(reviews__isnull=False).distinct().count() # noqa

        # Average rating
        avg_rating = products.aggregate(
            avg_rating=Avg('reviews__rating')
        )['avg_rating'] or 0

        # Top performing products (by sales)
        top_performing = OrderItem.objects.filter(
            product__merchant=user,
            order__status__in=['paid', 'shipped', 'completed']
        ).values('product__name').annotate(
            total_sales=Sum(
                ExpressionWrapper(
                    F('price') * F('quantity'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        ).order_by('-total_sales')[:5]

        top_performing_products = [
            {
                'name': item['product__name'],
                'total_sales': float(item['total_sales'])
            }
            for item in top_performing
        ]

        return {
            'products_with_reviews': products_with_reviews,
            'avg_rating': float(avg_rating),
            'top_performing_products': top_performing_products,
            'total_products': products.count()
        }


class FollowMerchantView(APIView):
    """
    API endpoint to follow/unfollow merchants
    """
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Follow a Merchant",
        operation_description="""
        Follow a merchant to get updates about their products and activities.
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (e.g., 'inbound', 'outbound')", # noqa
                    example='inbound'
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'merchant_id': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format=openapi.FORMAT_UUID,
                            description='ID of the merchant to follow',
                        )
                    },
                    required=['merchant_id']
                )
            },
            required=['requestType', 'data']
        ),
        responses={
            201: openapi.Response(
                description="Successfully followed merchant",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, example=True),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="Successfully followed merchant"),
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(
                                    type=openapi.TYPE_INTEGER),
                                'merchant': openapi.Schema(
                                    type=openapi.TYPE_OBJECT),
                                'created_at': openapi.Schema(
                                    type=openapi.TYPE_STRING, 
                                    format=openapi.FORMAT_DATETIME
                                )
                            }
                        )
                    }
                )
            ),
            400: openapi.Response(
                description="Invalid request data"),
            409: openapi.Response(
                description="Already following this merchant")
        }
    )
    def post(self, request):
        """Follow a merchant"""
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )

        serializer = FollowMerchantSerializer(
            data=data, context={'request': request})
        if serializer.is_valid():
            # Check if already following
            if FollowMerchant.objects.filter(
                user=request.user,
                merchant_id=serializer.validated_data['merchant_id']
            ).exists():
                return Response(
                    api_response(
                        message="You are already following this merchant.",
                        status=False
                    ),
                    status=409
                )

            # Create follow relationship
            follow = serializer.save(user=request.user)
            return Response(
                api_response(
                    message="Successfully followed merchant.",
                    status=True,
                    data=FollowMerchantListSerializer(
                        follow, context={'request': request}).data
                ),
                status=201
            )

        return Response(
            api_response(
                message="Invalid request data.",
                status=False,
                errors=serializer.errors
            ),
            status=400
        )

    @swagger_auto_schema(
        operation_summary="Unfollow a Merchant",
        operation_description="""
        Unfollow a merchant to stop receiving updates about their products.
        """,
        manual_parameters=[
            openapi.Parameter(
                'merchant_id',
                openapi.IN_QUERY,
                description="Merchant ID to unfollow",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="Successfully unfollowed merchant",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, 
                            example=True),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="Successfully unfollowed merchant")
                    }
                )
            ),
            404: openapi.Response(description="Not following this merchant")
        }
    )
    def delete(self, request):
        """Unfollow a merchant"""
        merchant_id = request.query_params.get('merchant_id')
        if not merchant_id:
            return Response(
                api_response(
                    message="Merchant ID is required.",
                    status=False
                ),
                status=400
            )

        try:
            follow = FollowMerchant.objects.get(
                user=request.user,
                merchant_id=merchant_id
            )
            follow.delete()
            return Response(
                api_response(
                    message="Successfully unfollowed merchant.",
                    status=True
                )
            )
        except FollowMerchant.DoesNotExist:
            return Response(
                api_response(
                    message="You are not following this merchant.",
                    status=False
                ),
                status=404
            )


class FollowedMerchantsListView(APIView):
    """
    API endpoint to list merchants followed by the authenticated user
    """
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Followed Merchants",
        operation_description="""
        Get a list of all merchants that the authenticated user is following.
        """,
        responses={
            200: openapi.Response(
                description="List of followed merchants",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, 
                            example=True),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="Followed merchants retrieved successfully"), # noqa
                        'data': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(
                                        type=openapi.TYPE_INTEGER),
                                    'merchant': openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(
                                                type=openapi.TYPE_INTEGER),
                                            'email': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                            'first_name': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                            'last_name': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                        }
                                    ),
                                    'merchant_profile': openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(
                                                type=openapi.TYPE_INTEGER),
                                            'cac_number': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                            'cac_document': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                            'selfie': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                            'location': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                            'lga': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                            'business_address': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                        }
                                    ),
                                    'created_at': openapi.Schema(
                                        type=openapi.TYPE_STRING, 
                                        format=openapi.FORMAT_DATETIME
                                    )
                                }
                            )
                        )
                    }
                )
            )
        }
    )
    def get(self, request):
        """Get list of followed merchants"""
        followed_merchants = FollowMerchant.objects.filter(
            user=request.user
        ).select_related('merchant', 'merchant__merchant_profile')
        
        serializer = FollowMerchantListSerializer(
            followed_merchants, many=True)
        return Response(
            api_response(
                message="Followed merchants retrieved successfully.",
                status=True,
                data=serializer.data
            )
        )


class FavoriteProductView(APIView):
    """
    API endpoint to add/remove products from favorites
    """
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Add Product to Favorites",
        operation_description="""
        Add a product to the user's favorites list.
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['requestType', 'data'],
            properties={
                'requestType': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Type of request (e.g., 'inbound', 'outbound')"
                ),
                'data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    required=['product_id'],
                    properties={
                        'product_id': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format='uuid',
                            description="UUID of the product to add to favorites"  # noqa
                        ),
                    }
                ),
            }
        ),
        responses={
            201: openapi.Response(
                description="Successfully added to favorites",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, 
                            example=True),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="Product added to favorites"), # noqa
                        'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(
                                    type=openapi.TYPE_INTEGER),
                                'product': openapi.Schema(
                                    type=openapi.TYPE_OBJECT,
                                    properties={
                                        'id': openapi.Schema(
                                            type=openapi.TYPE_INTEGER),
                                        # 'name': openapi.Schema(
                                        #     type=openapi.TYPE_STRING),
                                        # 'description': openapi.Schema(
                                        #     type=openapi.TYPE_STRING),
                                        # 'price': openapi.Schema(
                                        #     type=openapi.TYPE_NUMBER),
                                        # 'stock': openapi.Schema(
                                        #     type=openapi.TYPE_INTEGER),
                                        # 'is_rental': openapi.Schema(
                                        #     type=openapi.TYPE_BOOLEAN),
                                        # 'category': openapi.Schema(
                                        #     type=openapi.TYPE_OBJECT),
                                    }),
                                'created_at': openapi.Schema(
                                    type=openapi.TYPE_STRING, 
                                    format=openapi.FORMAT_DATETIME
                                )
                            }
                        )
                    }
                )
            ),
            400: openapi.Response(description="Invalid request data"),
            409: openapi.Response(description="Product already in favorites")
        }
    )
    def post(self, request):
        """Add product to favorites"""
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=400
            )

        serializer = FavoriteProductSerializer(
            data=data, context={'request': request})
        if serializer.is_valid():
            # Check if already favorited
            if FavoriteProduct.objects.filter(
                user=request.user,
                product__id=serializer.validated_data['product_id']
            ).exists():
                return Response(
                    api_response(
                        message="Product is already in your favorites.",
                        status=False
                    ),
                    status=409
                )

            # Create favorite
            favorite = serializer.save(user=request.user)
            return Response(
                api_response(
                    message="Product added to favorites.",
                    status=True,
                    data=FavoriteProductSerializer(
                        favorite, context={'request': request}).data
                ),
                status=201
            )

        return Response(
            api_response(
                message="Invalid request data.",
                status=False,
                errors=serializer.errors
            ),
            status=400
        )

    @swagger_auto_schema(
        operation_summary="Remove Product from Favorites",
        operation_description="""
        Remove a product from the user's favorites list.
        """,
        manual_parameters=[
            openapi.Parameter(
                'product_id',
                openapi.IN_QUERY,
                description="Product ID to remove from favorites",
                type=openapi.TYPE_STRING,
                format='uuid',
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="Successfully removed from favorites",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, 
                            example=True),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="Product removed from favorites"), # noqa
                    }
                )
            ),
            404: openapi.Response(description="Product not in favorites")
        }
    )
    def delete(self, request):
        """Remove product from favorites"""
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response(
                api_response(
                    message="Product ID is required.",
                    status=False
                ),
                status=400
            )

        try:
            favorite = FavoriteProduct.objects.get(
                user=request.user,
                product__id=product_id
            )
            favorite.delete()
            return Response(
                api_response(
                    message="Product removed from favorites.",
                    status=True
                )
            )
        except FavoriteProduct.DoesNotExist:
            return Response(
                api_response(
                    message="Product is not in your favorites.",
                    status=False
                ),
                status=404
            )


class FavoriteProductsListView(APIView):
    """
    API endpoint to list user's favorite products
    """
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Favorite Products",
        operation_description="""
        Get a list of all products that the authenticated user has favorited.
        """,
        responses={
            200: openapi.Response(
                description="List of favorite products",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(
                            type=openapi.TYPE_BOOLEAN, 
                            example=True),
                        'message': openapi.Schema(
                            type=openapi.TYPE_STRING, 
                            example="Favorite products retrieved successfully"), # noqa
                        'data': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(
                                        type=openapi.TYPE_INTEGER),
                                    'product': openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(
                                                type=openapi.TYPE_INTEGER),
                                            'name': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                        }),
                                    'category': openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(
                                                type=openapi.TYPE_INTEGER),
                                            'name': openapi.Schema(
                                                type=openapi.TYPE_STRING),
                                        }),
                                    'created_at': openapi.Schema(
                                        type=openapi.TYPE_STRING, 
                                        format=openapi.FORMAT_DATETIME
                                    )
                                }
                            )
                        )
                    }
                )
            )
        }
    )
    def get(self, request):
        """Get list of favorite products"""
        favorite_products = FavoriteProduct.objects.filter(
            user=request.user
        ).select_related('product', 'product__merchant', 'product__category')
        
        serializer = FavoriteProductListSerializer(
            favorite_products, many=True)
        return Response(
            api_response(
                message="Favorite products retrieved successfully.",
                status=True,
                data=serializer.data
            )
        )

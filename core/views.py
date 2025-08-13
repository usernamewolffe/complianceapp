# core/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

# Document the response for Swagger (optional but nice)
health_response = openapi.Response(
    description="Service is up",
    schema=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "status": openapi.Schema(type=openapi.TYPE_STRING, example="ok"),
        },
        required=["status"],
    ),
)

@swagger_auto_schema(method='get', responses={200: health_response})
@api_view(['GET'])
@permission_classes([AllowAny])
def health_view(request):
    return Response({"status": "ok"})

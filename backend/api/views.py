# Create your views here.

from socket import J1939_NLA_BYTES_ACKED

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from .serializers import UserSerializer

@api_view(['GET'])
def test(request):
    data = {
        'message': 'Hello World! - This is a test API endpoint.',
    }
    return Response(data)


@api_view(['POST'])
@permission_classes([AllowAny]) # in place because settings.py restricts annonymous users from requesting too often
def sign_up(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

"""
expects a JSON payload with the following attributes:
{ username, email, first_name, last_name, password, date_of_birth}
date of birth should be formatted as: YYYY-MM-DD
"""

from django.shortcuts import render

# Create your views here.

#test API

from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET'])
def test_api(request):
    data = {
        'message': 'Hello World! - This is a test API endpoint.',
    }
    return Response(data)

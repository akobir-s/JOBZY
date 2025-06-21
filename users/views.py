from django.shortcuts import render
from rest_framework.views import APIView
from .serializers import *
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from django.contrib.auth import authenticate
from .models import *
from rest_framework import status, generics
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAdminUser
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated


class RegisterUserView(APIView):
    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            user_data = UserRegisterSerializer(user).data
            return Response({
                'user': user_data,
                'refresh': str(refresh),
                'access': str(refresh.access_token)
            }, status=status.HTTP_201_CREATED)
        return Response({'error': serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST)


    

class LoginUserView(APIView):
    def post(self, request):
        serializer = LoginUserSerilalizer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data.get('username')
            password = serializer.validated_data.get('password')
            user = authenticate(username=username, password=password)
            if user:
                refresh = RefreshToken.for_user(user)
                return Response({
                    'user': user.username,
                    'refresh': str(refresh),
                    'access': str(refresh.access_token)
                }, status=status.HTTP_200_OK)
            
            return Response({'error': 'Username or password incorrect'},
                            status=status.HTTP_401_UNAUTHORIZED)
        return Response({'error': serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST)


class LogoutUserView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logged out successfully'},
            status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({'error': 'Invalid or expired token'},
            status=status.HTTP_400_BAD_REQUEST)

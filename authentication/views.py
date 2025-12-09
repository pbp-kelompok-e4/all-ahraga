from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.models import User
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt
from main.models import UserProfile


@csrf_exempt
def login(request):
    username = request.POST['username']
    password = request.POST['password']
    user = authenticate(username=username, password=password)
    if user is not None:
        if user.is_active:
            auth_login(request, user)
            # Mengambil role dari UserProfile
            try:
                user_profile = UserProfile.objects.get(user=user)
                if user_profile.is_venue_owner:
                    role_type = 'VENUE_OWNER'
                elif user_profile.is_coach:
                    role_type = 'COACH'
                else:
                    role_type = 'CUSTOMER'
            except UserProfile.DoesNotExist:
                role_type = 'CUSTOMER'  # Default fallback
            # Login status successful.
            return JsonResponse({
                "username": user.username,
                "status": True,
                "message": "Login successful!",
                "role_type": role_type  # Mengirimkan role ke Flutter
            }, status=200)
        else:
            return JsonResponse({
                "status": False,
                "message": "Login failed, account is disabled."
            }, status=401)

    else:
        return JsonResponse({
            "status": False,
            "message": "Login failed, please check your username or password."
        }, status=401)
    
@csrf_exempt
def register(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data['username']
        password1 = data['password1']
        password2 = data['password2']
        
        # Ambil role_type, default ke 'CUSTOMER' jika tidak ada
        role_type = data.get('role_type', 'CUSTOMER')

        # Check if the passwords match
        if password1 != password2:
            return JsonResponse({
                "status": False,
                "message": "Passwords do not match."
            }, status=400)
        
        # Check if the username is already taken
        if User.objects.filter(username=username).exists():
            return JsonResponse({
                "status": False,
                "message": "Username already exists."
            }, status=400)
        
        # Create the new user
        user = User.objects.create_user(username=username, password=password1)
        user.save()
        
        # Buat UserProfile sesuai role
        UserProfile.objects.create(
            user=user,
            phone_number=data.get('phone_number', ''),
            is_customer=(role_type == 'CUSTOMER'),
            is_venue_owner=(role_type == 'VENUE_OWNER'),
            is_coach=(role_type == 'COACH'),
        )
        
        return JsonResponse({
            "username": user.username,
            "status": 'success',
            "message": "User created successfully!"
        }, status=200)
    
    else:
        return JsonResponse({
            "status": False,
            "message": "Invalid request method."
        }, status=400)

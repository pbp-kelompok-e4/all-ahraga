from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth import logout as auth_logout
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

from main.models import UserProfile

ROLE_CUSTOMER = "CUSTOMER"
ROLE_VENUE_OWNER = "VENUE_OWNER"
ROLE_COACH = "COACH"


def get_role_type(user: User) -> str:
    """Baca role dari UserProfile dan kembalikan string seperti di form Django."""
    try:
        profile = user.profile  # related_name='profile'
    except UserProfile.DoesNotExist:
        return ROLE_CUSTOMER

    if profile.is_venue_owner:
        return ROLE_VENUE_OWNER
    if profile.is_coach:
        return ROLE_COACH
    return ROLE_CUSTOMER


def get_dashboard_redirect_name(user: User) -> str:
    """Mirror logika get_dashboard_redirect_url_name() versi HTML."""
    if not user.is_authenticated:
        return 'index'

    if user.is_superuser or user.is_staff:
        return 'admin_dashboard'

    try:
        profile = user.profile
        if profile.is_venue_owner:
            return 'venue_dashboard'
        elif profile.is_coach:
            return 'coach_profile'
        elif profile.is_customer:
            return 'home'
    except UserProfile.DoesNotExist:
        pass

    return 'home'

@csrf_exempt
def login(request):
    if request.method != 'POST':
        return JsonResponse({
            "status": False,
            "message": "Invalid request method."
        }, status=400)

    username = request.POST.get('username', '')
    password = request.POST.get('password', '')

    user = authenticate(username=username, password=password)
    if user is not None:
        if user.is_active:
            auth_login(request, user)

            role_type = get_role_type(user)
            redirect_name = get_dashboard_redirect_name(user)

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
                "role_type": role_type,          # untuk Flutter
                "redirect_to": redirect_name,   
                "message": "Login successful!"
            }, status=200)
        else:
            return JsonResponse({
                "status": False,
                "message": "Login failed, account is disabled."
            }, status=401)

    return JsonResponse({
        "status": False,
        "message": "Login failed, please check your username or password."
    }, status=401)

@csrf_exempt
def register(request):
    if request.method != 'POST':
        return JsonResponse({
            "status": False,
            "message": "Invalid request method."
        }, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({
            "status": False,
            "message": "Invalid JSON body."
        }, status=400)

    username = data.get('username', '').strip()
    password1 = data.get('password1', '')
    password2 = data.get('password2', '')
    role_type = data.get('role_type', ROLE_CUSTOMER)  # 🔹 kirim dari Flutter
    phone_number = data.get('phone_number')           # opsional, kalau mau
    email = data.get('email')                         # opsional

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

    # validasi role_type
    if role_type not in {ROLE_CUSTOMER, ROLE_VENUE_OWNER, ROLE_COACH}:
        return JsonResponse({
            "status": False,
            "message": "Invalid role type."
        }, status=400)

    # Create the new user
    user = User.objects.create_user(username=username, password=password1)
    if email:
        user.email = email
    user.save()

    # Create UserProfile with role flags
    profile = UserProfile.objects.create(
        user=user,
        phone_number=phone_number,
        is_customer=(role_type == ROLE_CUSTOMER),
        is_venue_owner=(role_type == ROLE_VENUE_OWNER),
        is_coach=(role_type == ROLE_COACH),
    )

    return JsonResponse({
        "username": user.username,
        "status": 'success',
        "role_type": role_type,
        "message": "User created successfully!"
    }, status=200)

@csrf_exempt
def logout(request):
    username = request.user.username
    try:
        auth_logout(request)
        return JsonResponse({
            "username": username,
            "status": True,
            "message": "Logged out successfully!"
        }, status=200)
    except:
        return JsonResponse({
            "status": False,
            "message": "Logout failed."
        }, status=401)

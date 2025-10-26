from django.db import transaction as db_transaction, IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm 
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum
from datetime import date, datetime, timedelta
from .forms import CustomUserCreationForm, ReviewForm, VenueForm, VenueScheduleForm, EquipmentForm, CoachProfileForm, CoachScheduleForm
from .models import Venue, SportCategory, LocationArea, CoachProfile, VenueSchedule, Transaction, Review, UserProfile, Booking, BookingEquipment, Equipment, CoachSchedule
from django.core.files.base import ContentFile
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import json
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.db.models import Q, Avg
import pytz
from django.contrib.auth.models import User 

def get_user_dashboard(user):
    # Disederhanakan menggunakan helper baru
    redirect_url_name = get_dashboard_redirect_url_name(user)
    return redirect(reverse(redirect_url_name))

def get_dashboard_redirect_url_name(user):
    """
    Mengembalikan 'nama' URL (name=...) untuk dashboard 
    berdasarkan role pengguna.
    """
    if not user.is_authenticated:
        return 'index' # Jika (entah bagaimana) dipanggil oleh user non-auth
    
    if user.is_superuser or user.is_staff:
        return 'admin_dashboard'  # Arahkan ke admin dashboard baru

    try:
        profile = user.profile
        if profile.is_venue_owner:
            return 'venue_dashboard'
        elif profile.is_coach:
            return 'coach_profile'
        elif profile.is_customer:
            return 'home' # 'home' sekarang adalah dashboard customer
    except UserProfile.DoesNotExist:
        pass # Lanjut ke default

    # Default untuk customer (tanpa profil), admin, atau staff
    return 'home'

def index_view(request):
    """
    View "Dispatcher" untuk root URL ('').
    - Pengguna non-auth -> Tampilkan landing.html
    - Pengguna auth -> Redirect ke dashboard masing-masing.
    """
    if request.user.is_authenticated:
        # Arahkan pengguna yang sudah login ke dashboard mereka
        redirect_url_name = get_dashboard_redirect_url_name(request.user)
        return redirect(reverse(redirect_url_name))
    
    # Pengguna anonim (visitor) akan melihat landing page
    return render(request, 'main/landing.html')

def is_admin(user):
    return user.is_superuser or user.is_staff

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': True, 'redirect': reverse('login')})
            messages.success(request, "Registration successful! Please log in.")
            return redirect('login')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
            messages.error(request, "Please check your input.")
    else:
        form = CustomUserCreationForm()
    return render(request, 'main/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return get_user_dashboard(request.user) # Tetap panggil ini

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
            
            # --- PERBAIKAN LOGIKA REDIRECT ---
            # Gunakan helper baru untuk menentukan URL
            redirect_url_name = get_dashboard_redirect_url_name(user)
            final_redirect_url = reverse(redirect_url_name)
            # --- AKHIR PERBAIKAN ---

            if is_ajax:
                return JsonResponse({'ok': True, 'redirect': final_redirect_url})
            else:
                messages.info(request, f"Welcome back, {user.username}.")
                return redirect(final_redirect_url)

        else: # Form tidak valid
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'main/login.html', {'form': form})

@login_required(login_url='login')
def logout_view(request):
    logout(request)
    return redirect(f"{reverse('landing')}?logout=1")

@login_required(login_url='login') # Ganti 'login' ke 'index' jika mau
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='index') # Arahkan non-customer ke index
def main_view(request):
    """Main page untuk customer - list venues dengan filter"""
    # Hanya customer yang bisa akses
    if not request.user.is_authenticated or not request.user.profile.is_customer:
        return redirect('home')
    
    venues = Venue.objects.all().select_related('location', 'sport_category', 'owner')
    
    # Get filter options
    locations = LocationArea.objects.all().order_by('name')
    sports = SportCategory.objects.all().order_by('name')
    
    context = {
        'venues': venues,
        'locations': locations,
        'sports': sports,
    }
    return render(request, 'main/home.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_dashboard_view(request):
    return redirect('home')

# ======================================================
# ======================================================
# ======================================================

def venue_detail_view(request, venue_id):
    venue = get_object_or_404(Venue, pk=venue_id)
    return render(request, 'main/venue_detail.html', {'venue': venue})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_dashboard_view(request):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        venues = Venue.objects.filter(owner=request.user)
        venues_data = []
        for venue in venues:
            venues_data.append({
                'id': venue.id,
                'name': venue.name,
                'category': venue.sport_category.name,
                'location': venue.location.name,
            })
        return JsonResponse({'venues': venues_data})
    
    venues = Venue.objects.filter(owner=request.user)
    locations = LocationArea.objects.all()
    categories = SportCategory.objects.all()
    
    context = {
        'venues': venues,
        'locations': locations,
        'categories': categories,
    }
    return render(request, 'main/venue_dashboard.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_revenue_view(request):
    # Check if it's an AJAX request
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    # 1. Ambil semua venue milik user ini
    venues = Venue.objects.filter(owner=request.user)
    venue_ids = venues.values_list('id', flat=True)
    
    # 2. Total revenue dari semua venue
    total_revenue = Transaction.objects.filter(
        booking__venue_schedule__venue__id__in=venue_ids,
        status='CONFIRMED'
    ).aggregate(total=Sum('revenue_venue'))['total'] or 0.00

    # 3. Revenue per venue dengan detail bookings
    venue_revenue_data = []
    for venue in venues:
        confirmed_bookings = Booking.objects.filter(
            venue_schedule__venue=venue,
            transaction__status='CONFIRMED'
        ).select_related(
            'customer',
            'venue_schedule',
            'transaction',
            'coach_schedule__coach__user'
        ).order_by('-booking_time')
        
        venue_total = Transaction.objects.filter(
            booking__venue_schedule__venue=venue,
            status='CONFIRMED'
        ).aggregate(total=Sum('revenue_venue'))['total'] or 0.00
        
        venue_data = {
            'venue': venue,
            'bookings': confirmed_bookings,
            'total_revenue': venue_total,
            'booking_count': confirmed_bookings.count()
        }
        
        # If AJAX, convert to serializable format
        if is_ajax:
            bookings_data = []
            for booking in confirmed_bookings:
                bookings_data.append({
                    'id': booking.id,
                    'customer_username': booking.customer.username,
                    'date': booking.venue_schedule.date.strftime('%a, %d %b %Y'),
                    'start_time': booking.venue_schedule.start_time.strftime('%H:%M'),
                    'end_time': booking.venue_schedule.end_time.strftime('%H:%M'),
                    'coach': booking.coach_schedule.coach.user.username if booking.coach_schedule else None,
                    'revenue': float(booking.transaction.revenue_venue)
                })
            
            venue_data = {
                'venue_id': venue.id,
                'venue_name': venue.name,
                'sport_category': venue.sport_category.name,
                'location': venue.location.name,
                'total_revenue': float(venue_total),
                'booking_count': confirmed_bookings.count(),
                'bookings': bookings_data
            }
        
        venue_revenue_data.append(venue_data)

    # Return JSON for AJAX requests
    if is_ajax:
        return JsonResponse({
            'success': True,
            'total_revenue': float(total_revenue),
            'venue_revenue_data': venue_revenue_data
        })

    # Return HTML for normal requests
    context = {
        'total_revenue': total_revenue,
        'venue_revenue_data': venue_revenue_data,
    }
    return render(request, 'main/venue_revenue.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_create_view(request):
    if request.method == 'POST':
        form = VenueForm(request.POST, request.FILES)
        if form.is_valid():
            user = request.user
            venue = form.save(commit=False)
            venue.owner = user
            venue.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f"Lapangan '{venue.name}' berhasil ditambahkan.",
                    'venue': {
                        'id': venue.id,
                        'name': venue.name,
                        'category': venue.sport_category.name,
                        'location': venue.location.name,
                        'manage_url': reverse('venue_manage', args=[venue.id])
                    }
                })
            
            messages.success(request, f"Lapangan '{venue.name}' berhasil ditambahkan.")
            return redirect('venue_dashboard')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'errors': form.errors}, status=400)
    else:
        form = VenueForm()

    return render(request, 'main/venue_form.html', {'form': form, 'page_title': 'Tambah Lapangan Baru'})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_manage_view(request, venue_id):
    venue = get_object_or_404(Venue, id=venue_id, owner=request.user)

    if request.method == 'POST':
        # Handle Venue Edit
        if 'submit_venue_edit' in request.POST:
            venue_edit_form = VenueForm(request.POST, request.FILES, instance=venue)
            if venue_edit_form.is_valid():
                venue_edit_form.save()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Data lapangan berhasil diperbarui.'
                    })
                
                messages.success(request, "Data lapangan berhasil diperbarui.")
                return redirect('venue_manage', venue_id=venue.id)
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'errors': venue_edit_form.errors}, status=400)

        # Handle Equipment Add
        elif 'submit_equipment' in request.POST:
            equipment_form = EquipmentForm(request.POST)
            if equipment_form.is_valid():
                equipment = equipment_form.save(commit=False)
                equipment.venue = venue 
                equipment.save()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    equipments_data = []
                    for item in venue.equipment.all():
                        equipments_data.append({
                            'id': item.id,
                            'name': item.name,
                            'stock': item.stock_quantity,
                            'price': float(item.rental_price)
                        })
                    return JsonResponse({
                        'success': True,
                        'message': 'Equipment baru berhasil ditambahkan.',
                        'equipments': equipments_data
                    })
                
                messages.success(request, "Equipment baru berhasil ditambahkan.")
                return redirect('venue_manage', venue_id=venue.id)
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    errors_dict = {}
                    for field, error_list in equipment_form.errors.items():
                        errors_dict[field] = [str(error) for error in error_list]
                    
                    return JsonResponse({
                        'success': False, 
                        'errors': errors_dict,
                        'message': 'Validasi gagal. Periksa input Anda.'
                    }, status=400)

        # Handle Equipment Edit
        elif request.POST.get('action') == 'edit':
            equipment_id = request.POST.get('equipment_id')
            try:
                equipment = Equipment.objects.get(id=equipment_id, venue=venue)
                equipment_form = EquipmentForm(request.POST, instance=equipment)
                
                if equipment_form.is_valid():
                    equipment_form.save()
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        equipments_data = []
                        for item in venue.equipment.all():
                            equipments_data.append({
                                'id': item.id,
                                'name': item.name,
                                'stock': item.stock_quantity,
                                'price': float(item.rental_price)
                            })
                        return JsonResponse({
                            'success': True,
                            'message': 'Equipment berhasil diperbarui.',
                            'equipments': equipments_data
                        })
                    
                    messages.success(request, "Equipment berhasil diperbarui.")
                    return redirect('venue_manage', venue_id=venue.id)
                else:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        errors_dict = {}
                        for field, error_list in equipment_form.errors.items():
                            errors_dict[field] = [str(error) for error in error_list]
                        
                        return JsonResponse({
                            'success': False, 
                            'errors': errors_dict,
                            'message': 'Validasi gagal. Periksa input Anda.'
                        }, status=400)
            except Equipment.DoesNotExist:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': 'Equipment tidak ditemukan.'
                    }, status=404)

        # Handle Equipment Delete
        elif request.POST.get('action') == 'delete':
            equipment_id = request.POST.get('equipment_id')
            try:
                equipment = Equipment.objects.get(id=equipment_id, venue=venue)
                equipment_name = equipment.name
                equipment.delete()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    equipments_data = []
                    for item in venue.equipment.all():
                        equipments_data.append({
                            'id': item.id,
                            'name': item.name,
                            'stock': item.stock_quantity,
                            'price': float(item.rental_price)
                        })
                    return JsonResponse({
                        'success': True,
                        'message': f'Equipment "{equipment_name}" berhasil dihapus.',
                        'equipments': equipments_data
                    })
                
                messages.success(request, f'Equipment "{equipment_name}" berhasil dihapus.')
                return redirect('venue_manage', venue_id=venue.id)
            except Equipment.DoesNotExist:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': 'Equipment tidak ditemukan.'
                    }, status=404)

    # GET request - display forms
    venue_edit_form = VenueForm(instance=venue)
    equipment_form = EquipmentForm()
    venue_location = venue.location 
    available_coaches = CoachProfile.objects.filter(
        service_areas=venue_location, 
        is_verified=True
    )
    equipments = venue.equipment.all()

    context = {
        'venue': venue,
        'venue_edit_form': venue_edit_form,
        'equipment_form': equipment_form,
        'equipments': equipments,
        'available_coaches': available_coaches,
    }
    return render(request, 'main/venue_manage.html', context)


@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_manage_schedule_view(request, venue_id):
    venue = get_object_or_404(Venue, id=venue_id, owner=request.user)
    
    if request.method == 'POST':
        # --- LOGIKA AJAX DIMULAI DI SINI ---
        schedule_form = VenueScheduleForm(request.POST)
        
        if schedule_form.is_valid():
            # Ambil end_time_global dari form yang valid
            end_time_global_str = schedule_form.cleaned_data.get('end_time_global')

            cd = schedule_form.cleaned_data
            schedule_date = cd['date']
            start_time = cd['start_time']
            is_available = cd.get('is_available', True)

            try:
                start_dt = datetime.combine(schedule_date, start_time)
                # Ubah end_time_global_str menjadi objek datetime
                end_dt_time = datetime.strptime(end_time_global_str, '%H:%M').time()
                end_dt = datetime.combine(schedule_date, end_dt_time)
            except (ValueError, TypeError):
                return JsonResponse({"success": False, "message": "Format jam atau tanggal tidak valid."}, status=400)

            if end_dt <= start_dt:
                return JsonResponse({"success": False, "message": "Waktu selesai harus setelah waktu mulai."}, status=400)

            created = 0
            new_slots_data = [] # List untuk data slot baru

            current = start_dt
            while current < end_dt:
                slot_start = current.time()
                next_dt = current + timedelta(hours=1)
                slot_end = next_dt.time()
                
                # Handle jika slot terakhir > end_dt
                if next_dt > end_dt:
                    slot_end = end_dt.time()

                exists = VenueSchedule.objects.filter(
                    venue=venue, date=schedule_date, start_time=slot_start
                ).exists()

                if not exists:
                    new_schedule = VenueSchedule.objects.create(
                        venue=venue,
                        date=schedule_date,
                        start_time=slot_start,
                        end_time=slot_end,
                        is_available=is_available
                    )
                    created += 1
                    # Tambahkan data untuk dikirim kembali ke frontend
                    new_slots_data.append({
                        'id': new_schedule.id,
                        'date_str_iso': new_schedule.date.strftime('%Y-%m-%d'),
                        'date_str_display': new_schedule.date.strftime('%A, %d %b %Y'), # Format: "l, d M Y"
                        'start_time': new_schedule.start_time.strftime('%H:%M'),
                        'end_time': new_schedule.end_time.strftime('%H:%M'),
                        'is_booked': False,
                    })
                
                current = next_dt
            
            # Kirim respons JSON
            return JsonResponse({
                "success": True, 
                "message": f"{created} slot jadwal berhasil ditambahkan.",
                "new_slots": new_slots_data
            }, status=200)

        else:
            # Form tidak valid
            return JsonResponse({"success": False, "message": "Data form tidak valid.", "errors": schedule_form.errors}, status=400)
            
    # --- LOGIKA GET (Menampilkan halaman) ---
    schedule_form = VenueScheduleForm()
    schedules = venue.schedules.all().order_by('date', 'start_time')

    context = {
        'venue': venue,
        'schedule_form': schedule_form,
        'schedules': schedules,
    }
    return render(request, 'main/venue_manage_schedule.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_schedule_delete(request, venue_id):
    venue = get_object_or_404(Venue, id=venue_id)

    # Cek kepemilikan
    if venue.owner != request.user:
        return JsonResponse({"success": False, "message": "Anda tidak memiliki izin."}, status=403)

    if request.method != 'POST':
        return JsonResponse({"success": False, "message": "Metode tidak diizinkan."}, status=405)

    # --- LOGIKA AJAX DELETE ---
    try:
        data = json.loads(request.body)
        ids = data.get('selected_schedules', [])
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Format data JSON tidak valid."}, status=400)

    if not ids:
        return JsonResponse({"success": False, "message": "Tidak ada jadwal yang dipilih."}, status=400)

    deletable_qs = VenueSchedule.objects.filter(id__in=ids, venue_id=venue.id, is_booked=False)
    count = deletable_qs.count()
    
    if count == 0:
         return JsonResponse({"success": True, "message": "Tidak ada jadwal yang dapat dihapus (mungkin sudah dibooking)."})

    deletable_qs.delete()
    return JsonResponse({"success": True, "message": f"{count} jadwal berhasil dihapus."})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def delete_venue_view(request, venue_id):
    try:
        venue = get_object_or_404(Venue, pk=venue_id)
        
        if venue.owner != request.user:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': "You don't have permission to delete this venue."
                }, status=403)
            messages.error(request, "You don't have permission to delete this venue.")
            return redirect('venue_dashboard')
        
        if request.method == 'POST':
            schedules_count = venue.schedules.count()
            bookings_count = Booking.objects.filter(venue_schedule__venue=venue).count()
            
            bookings = Booking.objects.filter(venue_schedule__venue=venue)
            
            transactions = Transaction.objects.filter(booking__in=bookings)
            transactions_count = transactions.count()
            transactions.delete()
            
            BookingEquipment.objects.filter(booking__in=bookings).delete()
            
            bookings.delete()
            
            venue.schedules.all().delete()
            
            venue_name = venue.name
            venue.delete()
            
            success_message = f"Lapangan '{venue_name}' berhasil dihapus"
            if schedules_count > 0 or bookings_count > 0:
                success_message += f" beserta {schedules_count} jadwal dan {bookings_count} booking terkait"
            success_message += "."
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'deleted_stats': {
                        'schedules': schedules_count,
                        'bookings': bookings_count,
                        'transactions': transactions_count
                    }
                })
            
            messages.success(request, success_message)
            return redirect('venue_dashboard')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            schedules_count = venue.schedules.count()
            bookings_count = Booking.objects.filter(venue_schedule__venue=venue).count()
            
            return JsonResponse({
                'success': True,
                'venue': {
                    'id': venue.id,
                    'name': venue.name,
                    'schedules_count': schedules_count,
                    'bookings_count': bookings_count
                }
            })
        
        return redirect('venue_dashboard')
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting venue {venue_id}: {str(e)}")
        
        error_message = f"Terjadi kesalahan saat menghapus venue: {str(e)}"
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': error_message
            }, status=500)
        
        messages.error(request, error_message)
        return redirect('venue_dashboard')

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def get_available_coaches(request, schedule_id):
    editing_booking_id = request.GET.get('editing_booking_id')

    try:
        schedule_query = Q(id=schedule_id)
        schedule_booked_filter = Q(is_booked=False)
        if editing_booking_id:
            schedule_booked_filter |= Q(booking__id=editing_booking_id)
        
        schedule_query &= schedule_booked_filter
        
        schedule = VenueSchedule.objects.select_related('venue__location', 'venue__sport_category').get(schedule_query)
        venue = schedule.venue
    except VenueSchedule.DoesNotExist:
        return JsonResponse({'error': 'Jadwal tidak ditemukan atau sudah dibooking.'}, status=404)
    coach_schedule_query = Q(
        date=schedule.date,
        start_time=schedule.start_time,
        is_available=True,
    )
    
    coach_booked_filter = Q(is_booked=False)
    if editing_booking_id:
        coach_booked_filter |= Q(booking__id=editing_booking_id)

    coach_schedule_query &= coach_booked_filter

    available_coach_ids = CoachSchedule.objects.filter(
        coach_schedule_query
    ).values_list('coach_id', flat=True)

    coaches_for_schedule = CoachProfile.objects.filter(
        id__in=available_coach_ids,
        service_areas=venue.location,
        main_sport_trained=venue.sport_category
    ).distinct().select_related(
        'user', 'main_sport_trained'
    ).prefetch_related('service_areas')

    coaches_data = []
    for coach in coaches_for_schedule:
        full_name = coach.user.get_full_name() or coach.user.username
        profile_picture_url = None
        if coach.profile_picture:
            try:
                profile_picture_url = coach.profile_picture.url
            except ValueError:
                profile_picture_url = None 
        areas_list = [area.name for area in coach.service_areas.all()]
        coaches_data.append({
            'id': coach.id,
            'name': full_name,
            'rate_per_hour': float(coach.rate_per_hour or 0), 
            'sport': coach.main_sport_trained.name,
            'age': coach.age,
            'experience_desc': coach.experience_desc,
            'profile_picture_url': profile_picture_url,
            'areas': areas_list,
        })

    return JsonResponse({'coaches': coaches_data})

@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_profile_view(request):
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        coach_profile = None

    phone = ''
    try:
        phone = request.user.profile.phone_number or ''
    except Exception:
        phone = ''

    context = {
        'user_obj': request.user,
        'phone_number': phone,
        'coach_profile': coach_profile,
    }
    return render(request, 'main/coach_profile.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
@require_http_methods(["POST"])
def save_coach_profile_ajax(request):
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        coach_profile = CoachProfile(user=request.user)

    form = CoachProfileForm(request.POST, request.FILES, instance=coach_profile)
    
    if form.is_valid():
        profile = form.save()
        
        # Prepare response data
        response_data = {
            'success': True,
            'message': 'Profil berhasil disimpan!',
            'profile': {
                'age': profile.age,
                'experience_desc': profile.experience_desc,
                'rate_per_hour': float(profile.rate_per_hour),
                'main_sport_trained': profile.main_sport_trained.name,
                'service_areas': [area.name for area in profile.service_areas.all()],
                'is_verified': profile.is_verified,
                'profile_picture': profile.profile_picture.url if profile.profile_picture else None,
            }
        }
        return JsonResponse(response_data)
    else:
        # Return validation errors
        errors = {}
        for field, error_list in form.errors.items():
            errors[field] = [str(error) for error in error_list]
        
        return JsonResponse({
            'success': False,
            'message': 'Terjadi kesalahan validasi',
            'errors': errors
        }, status=400)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
@require_http_methods(["POST"])
def delete_coach_profile_ajax(request):
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
        coach_profile.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Profil pelatih berhasil dihapus!'
        })
    except CoachProfile.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Profil tidak ditemukan'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Terjadi kesalahan: {str(e)}'
        }, status=500)
    
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def get_coach_profile_form_ajax(request):
    """Return form HTML for modal"""
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        coach_profile = None
    
    form = CoachProfileForm(instance=coach_profile)
    
    context = {
        'form': form,
        'coach_profile': coach_profile,
    }
    
    return render(request, 'main/coach_profile_form.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_schedule(request):
    """Handles displaying and AJAX creation/deletion of coach schedules."""

    coach_profile = None
    schedules = CoachSchedule.objects.none() # Default: queryset kosong

    # --- Pengambilan Profil (Aman untuk GET & POST) ---
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
        # Jika GET, ambil jadwal yang ada
        if request.method == 'GET':
            schedules = coach_profile.schedules.all().order_by('date', 'start_time')
    except CoachProfile.DoesNotExist:
        if request.method == 'POST':
            # Untuk POST (AJAX), kembalikan error JSON jika profil tidak ada
            return JsonResponse({"success": False, "message": "Profil pelatih tidak ditemukan. Lengkapi profil Anda terlebih dahulu."}, status=400)
        else:
            # Untuk GET, beri pesan warning tapi biarkan halaman render
            pass # Lanjutkan ke rendering template dengan coach_profile=None

    # --- Inisialisasi Form ---
    # Gunakan request.POST hanya jika metodenya POST, jika tidak None
    form_data = request.POST if request.method == 'POST' else None
    form = CoachScheduleForm(form_data)

    # --- Logika Penambahan Jadwal (AJAX POST) ---
    if request.method == 'POST':
        # Pastikan profil ada sebelum memproses POST (double check)
        if not coach_profile:
             return JsonResponse({"success": False, "message": "Profil pelatih tidak ditemukan."}, status=400)

        # Re-inisialisasi form dengan data POST untuk validasi
        form = CoachScheduleForm(request.POST)
        if form.is_valid():
            end_time_global_str = form.cleaned_data.get('end_time_global')
            schedule_date = form.cleaned_data['date']
            start_time_slot = form.cleaned_data['start_time']
            # Nilai is_available dari form diabaikan saat create, selalu True

            try:
                start_dt = datetime.combine(schedule_date, start_time_slot)
                end_dt_time = datetime.strptime(end_time_global_str, '%H:%M').time()
                end_dt = datetime.combine(schedule_date, end_dt_time)
            except (ValueError, TypeError):
                return JsonResponse({"success": False, "message": "Format jam atau tanggal tidak valid."}, status=400)

            if end_dt <= start_dt:
                return JsonResponse({"success": False, "message": "Waktu selesai harus setelah waktu mulai."}, status=400)

            created = 0
            new_slots_data = []
            current = start_dt

            while current < end_dt:
                slot_start = current.time()
                next_dt = current + timedelta(hours=1)
                slot_end = next_dt.time()

                if next_dt > end_dt:
                    slot_end = end_dt.time()

                # Cek jika slot sudah ada
                exists = CoachSchedule.objects.filter(
                    coach=coach_profile, date=schedule_date, start_time=slot_start
                ).exists()

                if not exists:
                    # Buat jadwal baru dengan is_available=True
                    new_schedule = CoachSchedule.objects.create(
                        coach=coach_profile,
                        date=schedule_date,
                        start_time=slot_start,
                        end_time=slot_end,
                        is_available=True  # <-- PAKSA JADI TRUE
                    )
                    created += 1
                    # Tambahkan data untuk respons JSON
                    new_slots_data.append({
                        'id': new_schedule.id,
                        'date_str_iso': new_schedule.date.strftime('%Y-%m-%d'),
                        'date_str_display': new_schedule.date.strftime('%A, %d %b %Y'),
                        'start_time': new_schedule.start_time.strftime('%H:%M'),
                        'end_time': new_schedule.end_time.strftime('%H:%M'),
                        'is_booked': False, # Baru dibuat, pasti belum dibooking
                    })
                current = next_dt

            # Kirim respons sukses
            return JsonResponse({
                "success": True,
                "message": f"{created} slot jadwal berhasil ditambahkan.",
                "new_slots": new_slots_data
            }, status=200)
        else:
            # Jika form POST tidak valid
            return JsonResponse({"success": False, "message": "Data form tidak valid.", "errors": form.errors}, status=400)

    # --- Logika Menampilkan Halaman (GET Request) ---
    # Form sudah diinisialisasi di atas (kosong karena bukan POST)
    user_has_profile = coach_profile is not None
    context = {
        'coach_profile': coach_profile, # Bisa None
        'schedules': schedules,         # Bisa queryset kosong
        'form': form,                   # Form kosong
        'has_profile': user_has_profile
    }
    return render(request, 'main/coach_schedule.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_schedule_delete(request):
    if request.method != 'POST':
        return JsonResponse({"message": "Metode tidak diizinkan."}, status=405)

    # ... (Logic validasi profil dan mendapatkan data JSON) ...
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        return JsonResponse({"message": "Profil pelatih tidak ditemukan."}, status=400)

    try:
        data = json.loads(request.body)
        ids = data.get('selected_schedules', [])
    except json.JSONDecodeError:
        return JsonResponse({"message": "Format data JSON tidak valid."}, status=400)

    deleted = 0
    warning_count = 0
    
    deletable_qs = CoachSchedule.objects.filter(id__in=ids, coach=coach_profile)

    for cs in deletable_qs:
        if cs.is_booked:
            warning_count += 1
            continue
        
        cs.delete()
        deleted += 1

    message = f"{deleted} jadwal berhasil dihapus."
    if warning_count > 0:
        message += f" ({warning_count} slot dibatalkan karena sudah dibooking)."

    # FINAL FIX: GANTI REDIRECT DENGAN JSON RESPONSE
    return JsonResponse({"success": True, "message": message}, status=200)

def coach_list_view(request):
    """Menampilkan daftar semua coach dengan pagination"""
    coaches_list = CoachProfile.objects.all().select_related(
        'user', 'main_sport_trained'
    ).prefetch_related('service_areas').order_by('user__first_name')
    
    # Filter berdasarkan pencarian
    query = request.GET.get('q')
    if query:
        coaches_list = coaches_list.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )
    
    # Filter berdasarkan olahraga
    sport_filter = request.GET.get('sport')
    if sport_filter:
        coaches_list = coaches_list.filter(main_sport_trained__id=sport_filter)
    
    # Filter berdasarkan area
    area_filter = request.GET.get('area')
    if area_filter:
        coaches_list = coaches_list.filter(service_areas__id=area_filter)
    
    paginator = Paginator(coaches_list, 8)  
    page_number = request.GET.get('page')
    
    try:
        coaches = paginator.page(page_number)
    except PageNotAnInteger:
        coaches = paginator.page(1)
    except EmptyPage:
        coaches = paginator.page(paginator.num_pages)
    
    categories = SportCategory.objects.all()
    areas = LocationArea.objects.all()
    
    context = {
        'coaches': coaches, 
        'categories': categories,
        'areas': areas,
    }
    return render(request, 'main/coach_list.html', context)

def coach_detail_public_view(request, coach_id):
    """Menampilkan detail coach untuk publik"""
    coach = get_object_or_404(
        CoachProfile.objects.select_related('user', 'main_sport_trained')
        .prefetch_related('service_areas'),
        id=coach_id
    )
    
    # Ambil review untuk coach ini
    reviews = Review.objects.filter(target_coach=coach).select_related('customer').order_by('-created_at')[:5]
    
    # Hitung rata-rata rating
    avg_rating = reviews.aggregate(avg=Sum('rating'))['avg']
    if avg_rating and reviews.count() > 0:
        avg_rating = avg_rating / reviews.count()
    else:
        avg_rating = 0
    
    context = {
        'coach': coach,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'total_reviews': reviews.count(),
    }
    return render(request, 'main/coach_detail.html', context)

def filter_coaches_ajax(request):
    """
    View AJAX untuk memfilter dan paginasi daftar coach.
    Hanya mengembalikan potongan HTML dari daftar coach.
    """
    coaches_list = CoachProfile.objects.all().select_related(
        'user', 'main_sport_trained'
    ).prefetch_related('service_areas').order_by('user__first_name')
    
    # Ambil parameter GET
    query = request.GET.get('q')
    sport_filter = request.GET.get('sport')
    area_filter = request.GET.get('area')
    
    # Filter berdasarkan pencarian
    if query:
        coaches_list = coaches_list.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )
    
    # Filter berdasarkan olahraga
    if sport_filter:
        coaches_list = coaches_list.filter(main_sport_trained__id=sport_filter)
    
    # Filter berdasarkan area
    if area_filter:
        coaches_list = coaches_list.filter(service_areas__id=area_filter)
    
    paginator = Paginator(coaches_list, 8)
    page_number = request.GET.get('page')
    
    try:
        coaches = paginator.page(page_number)
    except PageNotAnInteger:
        coaches = paginator.page(1)
    except EmptyPage:
        # Jika request AJAX meminta halaman di luar jangkauan,
        # kembalikan halaman terakhir.
        coaches = paginator.page(paginator.num_pages)
    
    context = {
        'coaches': coaches,
        # Kita teruskan parameter GET agar pagination link tetap benar
        'query': query,
        'sport_filter': sport_filter,
        'area_filter': area_filter,
    }
    
    # Render potongan HTML parsial, BUKAN seluruh halaman
    html = render_to_string(
        'main/coach_list_partial.html', 
        context,
        request=request
    )
    return JsonResponse({'html': html})


def get_coach_detail_ajax(request, coach_id):
    """
    View AJAX untuk mengambil detail coach untuk ditampilkan di modal.
    """
    coach = get_object_or_404(
        CoachProfile.objects.select_related('user', 'main_sport_trained')
        .prefetch_related('service_areas'),
        id=coach_id
    )
    
    reviews = Review.objects.filter(target_coach=coach).select_related('customer').order_by('-created_at')[:5]
    
    avg_rating = reviews.aggregate(avg=Sum('rating'))['avg']
    if avg_rating and reviews.count() > 0:
        avg_rating = avg_rating / reviews.count()
    else:
        avg_rating = 0
    
    context = {
        'coach': coach,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'total_reviews': reviews.count(),
    }
    
    # Render potongan HTML parsial untuk modal
    html = render_to_string(
        'main/coach_detail_partial.html', 
        context,
        request=request
    )
    return JsonResponse({'html': html})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_revenue_report(request):
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
        has_profile = True
    except CoachProfile.DoesNotExist:
        coach_profile = None
        has_profile = False

    if has_profile:
        transactions = Transaction.objects.filter(
            booking__coach_schedule__coach=coach_profile, 
            status='CONFIRMED'
        )
        total_revenue = transactions.aggregate(Sum('revenue_coach'))['revenue_coach__sum'] or 0
    else:
        transactions = []
        total_revenue = 0

    context = {
        'coach_profile': coach_profile,
        'has_profile': has_profile,
        'transactions': transactions,
        'total_revenue': total_revenue,
    }
    return render(request, 'main/coach_revenue_report.html', context)

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='home') 
def admin_dashboard_view(request):
    """
    Menampilkan dashboard kustom untuk admin (superuser atau staff).
    Hanya menampilkan 4 statistik utama.
    """
    
    # 1. Ambil 4 Statistik Utama
    total_users = User.objects.count()
    total_venues = Venue.objects.count()
    total_coaches = CoachProfile.objects.count()
    total_bookings = Booking.objects.count()

    # 2. Siapkan Context
    context = {
        'total_users': total_users,
        'total_venues': total_venues,
        'total_coaches': total_coaches,
        'total_bookings': total_bookings,
    }
    
    # 3. Render template
    return render(request, 'main/admin_dashboard.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def create_booking(request, venue_id):
    """Handles the display and processing of a new booking by a customer."""

    venue = get_object_or_404(Venue, id=venue_id)
    equipment_list = Equipment.objects.filter(venue=venue)

    try:
        jakarta_tz = pytz.timezone('Asia/Jakarta')
    except pytz.UnknownTimeZoneError:
        jakarta_tz = timezone.get_default_timezone()

    utc_now = timezone.now()
    now_in_jakarta = utc_now.astimezone(jakarta_tz)

    today = now_in_jakarta.date()
    current_time = now_in_jakarta.time()

    schedules = VenueSchedule.objects.filter(
        venue=venue,
        is_booked=False,  
        date__gte=today   
    ).exclude(
        date=today,
        start_time__lt=current_time
    ).order_by('date', 'start_time')

    if request.method == 'POST':
        schedule_id = request.POST.get('schedule_id')
        equipment_ids = request.POST.getlist('equipment') 
        coach_id = request.POST.get('coach') 
        payment_method = request.POST.get('payment_method', 'CASH') 

        if not schedule_id:
            messages.error(request, "Anda harus memilih jadwal terlebih dahulu!")
            return redirect('create_booking', venue_id=venue.id)

        try:
            with db_transaction.atomic():
                try:
                    schedule = VenueSchedule.objects.select_for_update().get(
                        id=schedule_id,
                        venue=venue,
                        is_booked=False,
                        date__gte=today
                    )
                    if schedule.date == today and schedule.start_time < current_time:
                         raise VenueSchedule.DoesNotExist("Jadwal yang dipilih sudah lewat.")

                except VenueSchedule.DoesNotExist as e:
                    messages.error(request, f"Jadwal tidak tersedia atau sudah dibooking. Silakan pilih jadwal lain. ({e})")
                    return redirect('create_booking', venue_id=venue.id)

                total_price = venue.price_per_hour or 0

                selected_equipment_data = [] 
                equipment_revenue = 0
                
                if equipment_ids:
                    equipment_queryset = Equipment.objects.filter(id__in=equipment_ids, venue=venue)
                    for eq in equipment_queryset:
                        quantity_str = request.POST.get(f'quantity_{eq.id}', '1')
                        try:
                            quantity = int(quantity_str)
                            if quantity <= 0: quantity = 1
                        except (ValueError, TypeError):
                            quantity = 1
                        
                        if quantity > eq.stock_quantity:
                            messages.error(request, f"Stock untuk {eq.name} tidak mencukupi (tersisa {eq.stock_quantity}).")
                            raise IntegrityError(f"Stock tidak cukup for {eq.name}.")
                    
                        item_sub_total = (eq.rental_price or 0) * quantity
                        equipment_revenue += item_sub_total
                        
                        selected_equipment_data.append((eq, quantity, item_sub_total))

                coach_obj = None
                coach_schedule_obj = None
                coach_revenue = 0 
                if coach_id:
                    try:
                        coach_obj = CoachProfile.objects.get(id=coach_id)
                        coach_schedule_obj = CoachSchedule.objects.select_for_update().get(
                            coach=coach_obj,
                            date=schedule.date,
                            start_time=schedule.start_time,
                            is_booked=False
                        )
                        coach_revenue = coach_obj.rate_per_hour or 0 
                    except CoachProfile.DoesNotExist:
                        raise IntegrityError("Coach profile does not exist.")
                    except CoachSchedule.DoesNotExist:
                        raise IntegrityError("Coach schedule not available.")

                total_price += equipment_revenue + coach_revenue 
                
                booking = Booking.objects.create(
                    customer=request.user,
                    venue_schedule=schedule,
                    coach_schedule=coach_schedule_obj,
                    total_price=total_price,
                )

                schedule.is_booked = True
                schedule.save()

                if coach_schedule_obj:
                    coach_schedule_obj.is_booked = True
                    coach_schedule_obj.save()

                booking_equipment_list = []
                for equipment, quantity, sub_total in selected_equipment_data: 
                    booking_equipment_list.append(
                        BookingEquipment(
                            booking=booking,
                            equipment=equipment,
                            quantity=quantity, 
                            sub_total=sub_total 
                        )
                    )
                if booking_equipment_list:
                    BookingEquipment.objects.bulk_create(booking_equipment_list)

                Transaction.objects.create(
                    booking=booking,
                    status='PENDING',
                    payment_method=payment_method,
                    revenue_venue=(venue.price_per_hour or 0) + equipment_revenue,
                    revenue_coach=coach_revenue, 
                    revenue_platform=0 
                )

        except IntegrityError as e:
             return redirect('create_booking', venue_id=venue.id)
        except Exception as e: 
             return redirect('create_booking', venue_id=venue.id)
        
        if payment_method.upper() == 'CASH':
            return redirect('my_bookings')
        else:
            return redirect('my_bookings')
    
    context = {
        'venue': venue,
        'schedules': schedules, 
        'equipment_list': equipment_list,
        'coaches': [], 
    }
    return render(request, 'main/create_booking.html', context)


# Pastikan impor ini ada di bagian atas file views.py Anda
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
# ... (impor Anda lainnya)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def customer_payment(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    transaction = booking.transaction
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if transaction.status == 'CONFIRMED':
        error_msg = "Booking ini sudah dikonfirmasi."
        
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_msg}, status=400)
        
        messages.success(request, error_msg)
        return redirect('my_bookings')

    if transaction.status == 'CANCELLED':
        return redirect('booking_history')

    if transaction.status != 'PENDING':
        messages.error(request, "Status booking tidak valid untuk pembayaran.")
        return redirect('my_bookings')

    if request.method == 'POST' or (transaction.payment_method and transaction.payment_method.upper() == 'CASH'):
        is_cash_auto_confirm = transaction.payment_method and transaction.payment_method.upper() == 'CASH' and request.method != 'POST'
        
        try:
            with db_transaction.atomic():
                venue_schedule = VenueSchedule.objects.select_for_update().get(id=booking.venue_schedule.id)
                already_booked_by_others = Booking.objects.filter(
                    venue_schedule=venue_schedule,
                    transaction__status='CONFIRMED'
                ).exclude(id=booking.id).exists()

                if already_booked_by_others:
                    transaction.status = 'CANCELLED'
                    transaction.save()
                    raise IntegrityError("Maaf, jadwal ini baru saja dikonfirmasi oleh pengguna lain.")
                
                booking_equipments = BookingEquipment.objects.filter(booking=booking).select_related('equipment')
                
                for be in booking_equipments:
                    equipment = Equipment.objects.select_for_update().get(id=be.equipment.id)
                    
                    if equipment.stock_quantity < be.quantity:
                        raise IntegrityError(f"Maaf, stok untuk {equipment.name} tidak mencukupi (tersisa {equipment.stock_quantity}).")
                    
                    equipment.stock_quantity -= be.quantity
                    equipment.save()
                
                venue_schedule.is_booked = True
                venue_schedule.is_available = False
                venue_schedule.save()
                
                if booking.coach_schedule:
                    coach_schedule = CoachSchedule.objects.select_for_update().get(id=booking.coach_schedule.id)
                    coach_schedule.is_booked = True
                    coach_schedule.is_available = False
                    coach_schedule.save()

                transaction.status = 'CONFIRMED'
                transaction.save()

                other_pending = Booking.objects.filter(
                    venue_schedule=venue_schedule,
                    transaction__status='PENDING'
                ).exclude(id=booking.id)

                for pending in other_pending:
                    pending.transaction.status = 'CANCELLED'
                    pending.transaction.save()

        except IntegrityError as e:
            error_msg = str(e) if ("stok" in str(e) or "jadwal" in str(e)) else "Terjadi kesalahan saat memproses pembayaran. Silakan coba lagi."
            
            if is_ajax and not is_cash_auto_confirm:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            
            messages.error(request, error_msg)
            return redirect('my_bookings')
        
        if is_ajax and not is_cash_auto_confirm:
            return JsonResponse({
                'success': True,
                'message': 'Pembayaran berhasil dikonfirmasi!',
                'redirect_url': reverse('my_bookings')
            })
        
        if is_cash_auto_confirm:
            redirect_url = reverse('my_bookings')
            toast_msg = 'Booking berhasil dikonfirmasi! Silakan bayar di tempat.'
            toast_type = 'success'
            return redirect(f"{redirect_url}?toast_msg={toast_msg}&toast_type={toast_type}")
                
        return redirect('my_bookings')

    context = {
        'booking': booking,
        'transaction': transaction,
    }
    return render(request, 'main/customer_payment.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def booking_history(request):
    bookings = (
        Booking.objects.filter(customer=request.user)
        .select_related(
            'venue_schedule__venue',
            'transaction',
            'coach_schedule__coach__user'
        )
        .prefetch_related('equipment_details__equipment')
        .order_by('-venue_schedule__date')
    )

    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if query:
        bookings = bookings.filter(
            Q(venue_schedule__venue__name__icontains=query) |
            Q(id__icontains=query)
        )

    if status:
        bookings = bookings.filter(transaction__status=status)

    user_reviews = Review.objects.filter(customer=request.user).select_related('target_venue', 'target_coach')

    venue_review_map, coach_review_map = {}, {}
    for r in user_reviews:
        if r.target_venue_id:
            prev = venue_review_map.get(r.target_venue_id)
            if prev is None or r.created_at > prev.created_at:
                venue_review_map[r.target_venue_id] = r
        if r.target_coach_id:
            prev = coach_review_map.get(r.target_coach_id)
            if prev is None or r.created_at > prev.created_at:
                coach_review_map[r.target_coach_id] = r

    for b in bookings:
        b.venue_review = None
        b.coach_review = None
        v_id = getattr(getattr(b, 'venue_schedule', None), 'venue_id', None)
        c_id = getattr(getattr(b, 'coach_schedule', None), 'coach_id', None)
        if v_id:
            b.venue_review = venue_review_map.get(v_id)
        if c_id:
            b.coach_review = coach_review_map.get(c_id)

    context = {'bookings': bookings}

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'main/_booking_list.html', context)

    return render(request, 'main/booking_history.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def my_bookings(request):
    bookings = Booking.objects.filter(
        customer=request.user, 
        transaction__status='PENDING'
    ).select_related(
        'venue_schedule__venue', 'transaction'
    ).order_by('-venue_schedule__date')

    query = request.GET.get('q', '').strip()
    if query:
        bookings = bookings.filter(
            Q(venue_schedule__venue__name__icontains=query) |
            Q(id__icontains=query) 
        )

    context = {
        'bookings' : bookings
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'main/_my_booking_list.html', context)
    
    return render(request, 'main/my_bookings.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def delete_booking(request, booking_id):
    if request.method != 'POST':
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Metode tidak diizinkan.'}, status=405)
        messages.error(request, "Metode tidak valid.")
        return redirect('my_bookings')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    try:
        booking = get_object_or_404(
            Booking.objects.select_related('transaction', 'venue_schedule', 'coach_schedule'), 
            id=booking_id, 
            customer=request.user
        )

        if booking.transaction and booking.transaction.status == 'PENDING':
            venue_schedule = booking.venue_schedule
            coach_schedule = booking.coach_schedule

            if venue_schedule:
                venue_schedule.is_booked = False
                venue_schedule.is_available = True
                venue_schedule.save()
            
            if coach_schedule:
                coach_schedule.is_booked = False
                coach_schedule.is_available = True
                coach_schedule.save()
            
            booking.transaction.status = 'CANCELLED'
            booking.transaction.delete()
            booking.delete()
            
            success_msg = 'Booking berhasil dibatalkan'
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': success_msg})
            
            messages.success(request, success_msg)
            return redirect('my_bookings')
        else:
            error_msg = 'Booking ini tidak dapat dibatalkan (status bukan PENDING).'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            
            messages.error(request, error_msg)
            return redirect('my_bookings')

    except Booking.DoesNotExist:
        error_msg = 'Booking tidak ditemukan.'
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_msg}, status=404)
        
        messages.error(request, error_msg)
        return redirect('my_bookings')

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def update_booking(request, booking_id):
    if request.method != 'POST':
        return JsonResponse({
            'success': False, 
            'message': 'Metode tidak diizinkan.'
        }, status=405)
    
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    try:
        booking = get_object_or_404(
            Booking.objects.select_related(
                'transaction', 
                'venue_schedule__venue', 
                'coach_schedule__coach'
            ), 
            id=booking_id, 
            customer=request.user
        )
        
        if booking.transaction.status != 'PENDING':
            error_msg = 'Hanya booking dengan status PENDING yang dapat diubah.'
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('my_bookings')
        
        new_schedule_id = request.POST.get('schedule_id')
        new_coach_id = request.POST.get('coach_id')  
        equipment_ids = request.POST.getlist('equipment')  
        new_payment_method = request.POST.get('payment_method', 'CASH') 
        
        if not new_schedule_id:
            return JsonResponse({
                'success': False, 
                'message': 'Jadwal harus dipilih.'
            }, status=400)
        
        with db_transaction.atomic():
            venue = booking.venue_schedule.venue
            now = timezone.localtime(timezone.now())
            today = now.date()
            current_time = now.time()
            
            try:
            # 1. Temukan jadwalnya dulu tanpa lock
                schedule_query = Q(id=new_schedule_id, venue=venue, date__gte=today)
                schedule_query &= (Q(is_booked=False) | Q(booking=booking))
                
                target_schedule = VenueSchedule.objects.get(schedule_query)
                
                # 2. Cek apakah sudah lewat
                if target_schedule.date == today and target_schedule.start_time < current_time:
                    raise VenueSchedule.DoesNotExist("Jadwal yang dipilih sudah lewat.")

                # 3. Kunci jadwal berdasarkan ID (query sederhana, aman untuk FOR UPDATE)
                new_schedule = VenueSchedule.objects.select_for_update().get(id=target_schedule.id)

                # 4. Cek ulang status setelah dikunci (mencegah race condition)
                if new_schedule.is_booked and new_schedule.booking_set.first() != booking:
                    raise IntegrityError("Jadwal ini baru saja dibooking oleh orang lain.")

            except VenueSchedule.DoesNotExist:
                return JsonResponse({ 'success': False, 'message': 'Jadwal tidak tersedia atau sudah dibooking.'}, status=400)
            except IntegrityError as e:
                return JsonResponse({ 'success': False, 'message': str(e)}, status=400)
            
            old_schedule = booking.venue_schedule
            if old_schedule.id != new_schedule.id:
                old_schedule.is_booked = False
                old_schedule.is_available = True
                old_schedule.save()
            
            if booking.coach_schedule:
                old_coach_schedule = booking.coach_schedule
                if (old_schedule.id != new_schedule.id) or (str(old_coach_schedule.coach.id) != new_coach_id):
                    old_coach_schedule.is_booked = False
                    old_coach_schedule.is_available = True
                    old_coach_schedule.save()
            
            total_price = venue.price_per_hour or 0
            coach_revenue = 0
            
            new_coach_schedule_obj = None
            if new_coach_id and new_coach_id != 'none' and new_coach_id != '':
                try:
                    coach_obj = CoachProfile.objects.get(id=new_coach_id)
                    coach_schedule_query = Q(coach=coach_obj, date=new_schedule.date, start_time=new_schedule.start_time)
                    coach_schedule_query &= (Q(is_booked=False) | Q(booking=booking))
                    
                    target_coach_schedule = CoachSchedule.objects.get(coach_schedule_query)

                    new_coach_schedule_obj = CoachSchedule.objects.select_for_update().get(id=target_coach_schedule.id)
                    
                    if new_coach_schedule_obj.is_booked and new_coach_schedule_obj.booking_set.first() != booking:
                        raise IntegrityError("Jadwal coach ini baru saja dibooking oleh orang lain.")

                    coach_revenue = coach_obj.rate_per_hour or 0 
                    
                    new_coach_schedule_obj.is_booked = True
                    new_coach_schedule_obj.save()
                    
                except (CoachProfile.DoesNotExist, CoachSchedule.DoesNotExist):
                    return JsonResponse({'success': False, 'message': 'Coach tidak tersedia pada jadwal yang dipilih.'}, status=400)
                except IntegrityError as e:
                    return JsonResponse({'success': False, 'message': str(e)}, status=400)
            
            BookingEquipment.objects.filter(booking=booking).delete() 
            
            equipment_revenue = 0 
            if equipment_ids:
                equipment_queryset = Equipment.objects.filter(id__in=equipment_ids, venue=venue)
                booking_equipment_list = []
                for eq in equipment_queryset:
                    quantity_str = request.POST.get(f'quantity_{eq.id}', '1')
                    try:
                        quantity = int(quantity_str)
                        if quantity <= 0: quantity = 1
                    except (ValueError, TypeError):
                        quantity = 1

                    if quantity > eq.stock_quantity:
                         return JsonResponse({'success': False, 'message': f"Stock untuk {eq.name} tidak mencukupi."}, status=400)
                    
                    item_sub_total = (eq.rental_price or 0) * quantity
                    equipment_revenue += item_sub_total 
                    
                    booking_equipment_list.append(
                        BookingEquipment(
                            booking=booking,
                            equipment=eq,
                            quantity=quantity, 
                            sub_total=item_sub_total 
                        )
                    )
                if booking_equipment_list:
                    BookingEquipment.objects.bulk_create(booking_equipment_list)
            
            booking.venue_schedule = new_schedule
            booking.coach_schedule = new_coach_schedule_obj
            booking.total_price = total_price + equipment_revenue + coach_revenue 
            booking.save()
            
            new_schedule.is_booked = True
            new_schedule.save()
            
            transaction = booking.transaction
            transaction.revenue_venue = (venue.price_per_hour or 0) + equipment_revenue 
            transaction.revenue_coach = coach_revenue 
            transaction.payment_method = new_payment_method
            transaction.save()
        
        success_msg = 'Booking berhasil diperbarui!'
        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': success_msg,
                'redirect_url': reverse('my_bookings')
            })
        
        messages.success(request, success_msg)
        return redirect('my_bookings')
        
    except Booking.DoesNotExist:
        error_msg = 'Booking tidak ditemukan.'
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_msg}, status=404)
        messages.error(request, error_msg)
        return redirect('my_bookings')
        
    except IntegrityError as e:
        error_msg = 'Terjadi konflik saat mengupdate booking. Silakan coba lagi.'
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('my_bookings')
        
    except Exception as e:
        error_msg = f'Terjadi kesalahan: {str(e)}'
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_msg}, status=500)
        messages.error(request, error_msg)
        return redirect('my_bookings')

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def update_booking_data(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related(
            'venue_schedule__venue', 
            'coach_schedule__coach__user'
        ), 
        id=booking_id,
        customer=request.user
    )
    venue = booking.venue_schedule.venue

    now = timezone.localtime(timezone.now())
    today = now.date()
    current_time = now.time()
    current_payment_method = booking.transaction.payment_method if booking.transaction else None

    current_schedule = booking.venue_schedule
    current_schedule_data = {
        'id': current_schedule.id,
        'date_str_display': current_schedule.date.strftime('%A, %d %B %Y'),
        'start_time': current_schedule.start_time.strftime('%H:%M'),
        'end_time': current_schedule.end_time.strftime('%H:%M'),
    }

    schedules = VenueSchedule.objects.filter(
        venue=venue,
        is_booked=False,
        date__gte=today
    ).exclude(
        id=current_schedule.id  
    ).exclude(
        date=today,
        start_time__lt=current_time
    ).order_by('date', 'start_time')

    schedules_data = [
        {
            'id': s.id,
            'date_str_display': s.date.strftime('%A, %d %B %Y'),
            'start_time': s.start_time.strftime('%H:%M'),
            'end_time': s.end_time.strftime('%H:%M'),
        }
        for s in schedules
    ]

    current_coach_id = None
    current_coach_data = None
    if booking.coach_schedule and booking.coach_schedule.coach:
        coach = booking.coach_schedule.coach
        current_coach_id = coach.id
        current_coach_data = {
            'id': coach.id,
            'name': coach.user.get_full_name() or coach.user.username,
            'rate': float(coach.rate_per_hour or 0)
        }

    selected_equipment_map = {
        item['equipment_id']: item['quantity']
        for item in BookingEquipment.objects.filter(booking=booking).values('equipment_id', 'quantity')
    }
    
    equipments = Equipment.objects.filter(venue=venue)
    available_equipments_data = [
        {
            'id': e.id,
            'name': e.name,
            'price': float(e.rental_price or 0),
            'stock_quantity': e.stock_quantity  
        }
        for e in equipments
    ]

    return JsonResponse({
        'success': True,
        'current_schedule': current_schedule_data,
        'schedules': schedules_data,
        'current_coach_id': current_coach_id,
        'current_coach_data': current_coach_data, 
        'selected_equipment_map': selected_equipment_map, 
        'available_equipments': available_equipments_data,
        'current_payment_method' : current_payment_method,
    })

def filter_venues_ajax(request):
    """AJAX endpoint untuk filter venues dengan pagination"""
    search = request.GET.get('search', '').strip()
    location_id = request.GET.get('location', '')
    sport_id = request.GET.get('sport', '')
    page = request.GET.get('page', 1)
    
    venues = Venue.objects.all().select_related('location', 'sport_category', 'owner')
    
    # Apply filters
    if search:
        venues = venues.filter(
            Q(name__icontains=search) | 
            Q(description__icontains=search)
        )
    
    if location_id:
        venues = venues.filter(location_id=location_id)
    
    if sport_id:
        venues = venues.filter(sport_category_id=sport_id)
    
    # Pagination dengan 6 item per halaman
    paginator = Paginator(venues, 6)
    try:
        venues_page = paginator.page(page)
    except PageNotAnInteger:
        venues_page = paginator.page(1)
    except EmptyPage:
        venues_page = paginator.page(paginator.num_pages)
    
    # Prepare JSON response
    venues_data = []
    for venue in venues_page:
        avg_rating = venue.reviews.aggregate(Avg('rating'))['rating__avg'] or 0
        
        venues_data.append({
            'id': venue.id,
            'name': venue.name,
            'description': venue.description[:100] + '...' if venue.description and len(venue.description) > 100 else (venue.description or 'Tidak ada deskripsi'),
            'location': venue.location.name if venue.location else '-',
            'sport': venue.sport_category.name,
            'price': float(venue.price_per_hour),
            'image': venue.main_image.url if venue.main_image else None,
            'rating': round(avg_rating, 1),
        })
    
    # Return dengan data pagination yang lengkap
    return JsonResponse({
        'success': True,
        'venues': venues_data,
        'has_next': venues_page.has_next(),
        'has_previous': venues_page.has_previous(),
        'current_page': venues_page.number,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count,
    })

def landing_page_view(request):
    """
    Selalu menampilkan landing page, tidak peduli status login.
    """
    return render(request, 'main/landing.html')


def _guard_confirmed_owner(request, booking):
    if booking.customer != request.user:
        raise Http404("Tidak ditemukan.")
    if getattr(booking, "transaction", None) and booking.transaction.status != "CONFIRMED":
        # Untuk XHR kirim JSON error, untuk non-XHR pakai messages
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({"success": False, "message": "Feedback hanya untuk booking berstatus CONFIRMED."}, status=400)
        messages.error(request, "Feedback hanya untuk booking berstatus CONFIRMED.")
        return False
    return True


@login_required
def upsert_review(request, booking_id):
    """Create/edit review berdasarkan target. ?target=venue|coach"""
    target = request.GET.get("target")
    booking = get_object_or_404(
        Booking.objects.select_related(
            "venue_schedule__venue", "coach_schedule__coach__user", "transaction"
        ),
        pk=booking_id,
        customer=request.user
    )

    # --- Guard kepemilikan & status booking ---
    guard = _guard_confirmed_owner(request, booking)
    if guard is False:
        return redirect("booking_history")
    if isinstance(guard, JsonResponse):
        return guard  # guard udah balikin JSON error kalau XHR

    # --- Tentukan target review ---
    instance = None
    if target == "venue":
        venue = getattr(getattr(booking, "venue_schedule", None), "venue", None)
        if not venue:
            msg = "Booking ini tidak memiliki venue yang valid."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("booking_history")

        instance = Review.objects.filter(customer=request.user, target_venue=venue).order_by("-created_at").first()
        title = "Edit Review Venue" if instance else "Beri Review Venue"
        target_ctx = {"target": "venue", "target_name": venue.name}

    elif target == "coach":
        coach = getattr(getattr(booking, "coach_schedule", None), "coach", None)
        if not coach:
            msg = "Booking ini tidak memiliki pelatih."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("booking_history")

        instance = Review.objects.filter(customer=request.user, target_coach=coach).order_by("-created_at").first()
        title = "Edit Review Coach" if instance else "Beri Review Coach"
        target_ctx = {"target": "coach", "target_name": getattr(coach, "user", coach).__str__()}

    else:
        raise Http404("Target tidak valid.")

    # --- Handle POST (submit form) ---
    if request.method == "POST":
        form = ReviewForm(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.customer = request.user
            if target == "venue":
                obj.target_venue, obj.target_coach = venue, None
            else:
                obj.target_coach, obj.target_venue = coach, None
            obj.save()

            msg = "Feedback diperbarui." if instance else "Feedback berhasil ditambahkan."

            # kalau AJAX, balikin JSON biar toast muncul
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True, "message": msg})

            # kalau bukan AJAX (misal user akses langsung)
            messages.success(request, msg)
            return redirect("booking_history")

        # kalau form invalid
        err = next(iter(form.errors.values()))[0] if form.errors else "Form tidak valid."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "message": err}, status=400)
        messages.error(request, err)
        return redirect(request.path)

    # --- Render form biasa ---
    else:
        form = ReviewForm(instance=instance)

    return render(request, "main/review_form.html", {
        "title": title,
        "form": form,
        "booking": booking,
        **target_ctx,
        "existing": instance is not None,
        "existing_id": getattr(instance, "id", None),
    })

@login_required
def delete_review(request, review_id):
    review = get_object_or_404(Review, pk=review_id, customer=request.user)
    if request.method == "POST":
        review.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({"success": True, "message": "Feedback dihapus."})
        messages.success(request, "Feedback dihapus.")
        return redirect("booking_history")

    # Metode selain POST
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({"success": False, "message": "Metode tidak diizinkan."}, status=405)
    messages.info(request, "Konfirmasi hapus dilakukan dari tombol di halaman.")
    return redirect("booking_history")

# ======================================================
# ======================================================
# ======================================================

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='home')
def admin_user_management_view(request):
    """Menampilkan halaman manajemen semua pengguna dengan pagination."""
    user_list = User.objects.select_related('profile').order_by('-date_joined')
    
    paginator = Paginator(user_list, 20) # 20 user per halaman
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'users_page': page_obj
    }
    return render(request, 'main/admin_users.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin, login_url='home')
def admin_venue_management_view(request):
    """Menampilkan halaman manajemen semua venue dengan pagination."""
    venue_list = Venue.objects.select_related('owner', 'sport_category', 'location').order_by('-id')
    
    paginator = Paginator(venue_list, 20) # 20 venue per halaman
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'venues_page': page_obj
    }
    return render(request, 'main/admin_venues.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin, login_url='home')
def admin_booking_management_view(request):
    """Menampilkan halaman manajemen semua booking/transaksi dengan pagination."""
    booking_list = Booking.objects.select_related(
        'customer', 
        'venue_schedule__venue', 
        'transaction', 
        'coach_schedule__coach__user'
    ).order_by('-booking_time')
    
    paginator = Paginator(booking_list, 20) # 20 booking per halaman
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'bookings_page': page_obj
    }
    return render(request, 'main/admin_bookings.html', context)

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='home')
def admin_coach_management_view(request):
    """Menampilkan halaman manajemen semua profil pelatih."""
    
    # Ambil semua CoachProfile, optimalkan query
    coach_list = CoachProfile.objects.select_related(
        'user', 
        'main_sport_trained'
    ).order_by('user__username')
    
    paginator = Paginator(coach_list, 20) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'coaches_page': page_obj
    }
    return render(request, 'main/admin_coaches.html', context)

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='home')
@require_http_methods(["POST"]) # Memastikan ini hanya bisa diakses via POST
def admin_toggle_coach_verification_view(request, coach_id):
    """
    Meng-toggle status is_verified seorang Coach via AJAX.
    """
    try:
        # Cari coach profile
        coach = get_object_or_404(CoachProfile, id=coach_id)

        # Balik statusnya (jika True -> False, jika False -> True)
        coach.is_verified = not coach.is_verified
        coach.save()

        # Kirim kembali status baru dalam format JSON
        return JsonResponse({
            'success': True,
            'is_verified': coach.is_verified, # Kirim status baru
            'message': 'Status coach berhasil diperbarui.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
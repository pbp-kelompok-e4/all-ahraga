from django.db import transaction as db_transaction, IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm 
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum
from datetime import date, datetime, timedelta
from .forms import CustomUserCreationForm, VenueForm, VenueScheduleForm, EquipmentForm, CoachProfileForm, CoachScheduleForm
from .models import Venue, SportCategory, LocationArea, CoachProfile, VenueSchedule, Transaction, Review, UserProfile, Booking, BookingEquipment, Equipment, CoachSchedule
from django.core.files.base import ContentFile
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from .forms import ReviewForm

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
    # === Data untuk landing ===
    # Stats ringkas
    stats = {
        "total_venues": Venue.objects.count(),
        "total_coaches": CoachProfile.objects.count(),
        # anggap "booking terselesaikan" = transaksi CONFIRMED
        "total_bookings": Booking.objects.filter(transaction__status='CONFIRMED').count(),
    }

    # Venue & Coach pilihan (acak) + select_related agar hemat query
    featured_venues = (
        Venue.objects.select_related('sport_category', 'location')
        .order_by('?')[:6]
    )
    featured_coaches = (
        CoachProfile.objects.select_related('user', 'main_sport_trained')
        .order_by('?')[:6]
    )

    # Testimoni terbaru
    testimonials = (
        Review.objects.select_related('customer')
        .order_by('-created_at')[:5]
    )

    context = {
        "stats": stats,
        "featured_venues": featured_venues,
        "featured_coaches": featured_coaches,
        "testimonials": testimonials,
    }
    return render(request, 'main/landing.html', context)

def is_admin(user):
    return user.is_superuser or user.is_staff

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        if form.is_valid():
            form.save()
            if is_ajax:
                return JsonResponse({'ok': True, 'redirect': reverse('login')})
            messages.success(request, "Registration successful! Please log in.")
            return redirect('login')

        # jika form invalid
        if is_ajax:
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
        messages.error(request, "Please check your input.")
    else:
        form = CustomUserCreationForm()
    return render(request, 'main/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return get_user_dashboard(request.user)  # Tetap panggil ini

    # Simpan next ke session saat GET agar tetap terbawa meski form AJAX tidak menyertakan hidden input
    if request.method == 'GET':
        nxt = request.GET.get('next')
        if nxt:
            request.session['post_login_next'] = nxt

    if request.method == 'POST':
        from django.utils.http import url_has_allowed_host_and_scheme  # import lokal biar snippet ini self-contained
        form = AuthenticationForm(request, data=request.POST)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Ambil next dari POST -> GET -> session (fallback)
            next_from_post = request.POST.get('next')
            next_from_get = request.GET.get('next')
            next_from_session = request.session.pop('post_login_next', None)
            candidate_next = next_from_post or next_from_get or next_from_session

            # Validasi next agar hanya redirect ke host yang sama / skema aman
            if candidate_next and url_has_allowed_host_and_scheme(candidate_next, allowed_hosts={request.get_host()}):
                final_redirect_url = candidate_next
            else:
                # --- PERBAIKAN LOGIKA REDIRECT ---
                # Gunakan helper baru untuk menentukan URL
                redirect_url_name = get_dashboard_redirect_url_name(user)
                final_redirect_url = reverse(redirect_url_name)
                # --- AKHIR PERBAIKAN ---

            if is_ajax:
                return JsonResponse({'ok': True, 'redirect': final_redirect_url})
            messages.info(request, f"Welcome back, {user.username}.")
            return redirect(final_redirect_url)

        # form tidak valid
        if is_ajax:
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    # Kirimkan next ke template juga (kalau mau dipakai hidden input di form)
    next_ctx = request.GET.get('next') or request.session.get('post_login_next', '')
    return render(request, 'main/login.html', {'form': form, 'next': next_ctx})


@login_required(login_url='login')
def logout_view(request):
    logout(request)
    messages.info(request, "Logout Berhasil.")
    return redirect('index')

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
            messages.warning(request, "Anda belum melengkapi profil pelatih. Silakan lengkapi profil untuk mengelola jadwal.")
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
    
    paginator = Paginator(coaches_list, 6)  
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
    
    paginator = Paginator(coaches_list, 6)
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

def admin_dashboard_view(request):
    if not is_admin(request.user):
        return redirect('home')
    return redirect('home')

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def create_booking(request, venue_id):
    """Handles the display and processing of a new booking by a customer."""

    venue = get_object_or_404(Venue, id=venue_id)
    equipment_list = Equipment.objects.filter(venue=venue)

    now = timezone.localtime(timezone.now())
    today = now.date()
    current_time = now.time()

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
                        messages.error(request, "Coach yang Anda pilih tidak valid.")
                        raise IntegrityError("Coach profile does not exist.")
                    except CoachSchedule.DoesNotExist:
                        messages.error(request, f"Coach {coach_obj.user.username} tidak lagi tersedia pada jadwal yang dipilih.")
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
             messages.error(request, f"Terjadi kesalahan tidak terduga: {e}. Silakan coba lagi.")
             return redirect('create_booking', venue_id=venue.id)

        messages.success(request, "Booking berhasil dibuat! Segera lakukan pembayaran untuk mengonfirmasi jadwal Anda.")
        return redirect('my_bookings') 
    
    context = {
        'venue': venue,
        'schedules': schedules, 
        'equipment_list': equipment_list,
        'coaches': [], 
    }
    return render(request, 'main/create_booking.html', context)


@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def customer_payment(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    transaction = booking.transaction

    if transaction.status == 'CONFIRMED':
        messages.success(request, "Booking ini sudah dikonfirmasi.")
        return redirect('my_bookings')

    if transaction.status == 'CANCELLED':
        messages.error(request, "Booking ini sudah dibatalkan atau kedaluwarsa.")
        return redirect('booking_history')

    if transaction.status != 'PENDING':
        messages.error(request, "Status booking tidak valid untuk pembayaran.")
        return redirect('my_bookings')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    if request.method == 'POST' or (transaction.payment_method and transaction.payment_method.upper() == 'CASH'):
        is_cash_auto_confirm = not request.method == 'POST'
        
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
                    error_msg = "Maaf, jadwal ini baru saja dikonfirmasi oleh pengguna lain."
                    
                    if is_ajax and not is_cash_auto_confirm:
                        return JsonResponse({'success': False, 'message': error_msg}, status=400)
                    
                    messages.error(request, error_msg)
                    return redirect('booking_history')

                booked_items = BookingEquipment.objects.filter(booking=booking).select_related('equipment')
                items_to_update = []
                
                for item in booked_items:
                    equipment = Equipment.objects.select_for_update().get(id=item.equipment.id)
                    
                    if equipment.stock_quantity < item.quantity:
                        raise IntegrityError(f"Pembayaran gagal, stok untuk {equipment.name} tidak lagi mencukupi.")
                    
                    equipment.stock_quantity -= item.quantity
                    items_to_update.append(equipment)
                
                if items_to_update:
                    Equipment.objects.bulk_update(items_to_update, ['stock_quantity'])
    
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
            error_msg = str(e) if "stok" in str(e) else "Terjadi kesalahan saat memproses pembayaran. Silakan coba lagi."
            
            if is_ajax and not is_cash_auto_confirm:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('my_bookings')
        
        success_msg = "Pembayaran berhasil. Booking Anda telah dikonfirmasi."
        if is_ajax and not is_cash_auto_confirm:
            return JsonResponse({
                'success': True,
                'message': success_msg,
                'redirect_url': reverse('my_bookings')
            })

        messages.success(request, success_msg)
        return redirect('my_bookings')

    context = {
        'booking': booking,
        'transaction': transaction,
    }
    return render(request, 'main/customer_payment.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def booking_history(request):
    qs = (Booking.objects
          .select_related(
              'transaction',
              'venue_schedule__venue__location',
              'coach_schedule__coach__user'
          )
          .filter(customer=request.user)
          .order_by('-id'))

    # filter q & status kalau kamu sudah punya logika AJAX-nya
    q = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    if q:
        qs = qs.filter(venue_schedule__venue__name__icontains=q) | qs.filter(id__icontains=q)
    if status:
        qs = qs.filter(transaction__status=status)

    bookings = list(qs)

    # Sematkan review user untuk setiap booking (venue & coach)
    for b in bookings:
        b.my_venue_review = None
        b.my_coach_review = None

        venue = b.venue_schedule.venue if b.venue_schedule else None
        coach = b.coach_schedule.coach if b.coach_schedule else None

        if venue:
            b.my_venue_review = (Review.objects
                                 .filter(customer=request.user,
                                         target_venue=venue,
                                         target_coach__isnull=True)
                                 .order_by('-id')
                                 .first())
        if coach:
            b.my_coach_review = (Review.objects
                                 .filter(customer=request.user,
                                         target_coach=coach,
                                         target_venue__isnull=True)
                                 .order_by('-id')
                                 .first())

    # Untuk permintaan AJAX (partial list) kamu bisa render template partial (booking_list.html)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'main/booking_list.html', {'bookings': bookings})

    return render(request, 'main/booking_history.html', {'bookings': bookings})

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
            
            if is_ajax:
                return JsonResponse({'success': True, 'message': 'Booking berhasil dibatalkan dan jadwal telah dikembalikan.'})
            
            messages.success(request, 'Booking berhasil dibatalkan dan jadwal telah dikembalikan.')
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
                schedule_query = Q(id=new_schedule_id, venue=venue, date__gte=today)
                schedule_query &= (Q(is_booked=False) | Q(booking=booking))
                new_schedule = VenueSchedule.objects.select_for_update().get(schedule_query)
                if new_schedule.date == today and new_schedule.start_time < current_time:
                    raise VenueSchedule.DoesNotExist("Jadwal yang dipilih sudah lewat.")
            except VenueSchedule.DoesNotExist:
                return JsonResponse({ 'success': False, 'message': 'Jadwal tidak tersedia atau sudah dibooking.'}, status=400)
            
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
                    new_coach_schedule_obj = CoachSchedule.objects.select_for_update().get(coach_schedule_query)

                    coach_revenue = coach_obj.rate_per_hour or 0 
                    
                    new_coach_schedule_obj.is_booked = True
                    new_coach_schedule_obj.save()
                except (CoachProfile.DoesNotExist, CoachSchedule.DoesNotExist):
                    return JsonResponse({'success': False, 'message': 'Coach tidak tersedia pada jadwal yang dipilih.'}, status=400)
            
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
        'selected_equipment_ids': selected_equipment_ids,
        'equipments': equipments_data,
    })

# ======================================================
# ================== REVIEWS (VENUE/COACH) =============
# ======================================================
@login_required(login_url='login')
@user_passes_test(lambda u: hasattr(u, 'profile') and u.profile.is_customer, login_url='home')
def submit_review(request, booking_id):
    """
    Submit review untuk venue ATAU coach dari sebuah booking (tanpa AJAX).
    GET  : tampilkan form.
    POST : simpan review.
    """
    booking = get_object_or_404(
        Booking.objects.select_related('transaction', 'venue_schedule__venue', 'coach_schedule__coach'),
        id=booking_id,
        customer=request.user
    )

    # Hanya boleh review jika CONFIRMED
    if not booking.transaction or booking.transaction.status != 'CONFIRMED':
        messages.error(request, "Hanya booking dengan status CONFIRMED yang bisa diberi ulasan.")
        return redirect('booking_history')

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            target  = (form.cleaned_data.get('target') or '').strip().lower()   # 'venue' | 'coach'
            rating  = form.cleaned_data.get('rating')
            comment = (form.cleaned_data.get('comment') or '').strip()

            if target not in ('venue', 'coach'):
                messages.error(request, "Target review tidak valid.")
                return redirect('booking_history')

            if target == 'venue':
                target_venue = booking.venue_schedule.venue if booking.venue_schedule else None
                if not target_venue:
                    messages.error(request, "Booking ini tidak memiliki venue untuk direview.")
                    return redirect('booking_history')

                # Cegah duplikasi review untuk venue ini oleh user yang sama
                if Review.objects.filter(
                    customer=request.user, target_venue=target_venue, target_coach__isnull=True
                ).exists():
                    messages.warning(request, "Anda sudah memberi ulasan untuk venue ini.")
                    return redirect('booking_history')

                Review.objects.create(
                    customer=request.user,
                    target_venue=target_venue,
                    rating=rating,
                    comment=comment
                )
                messages.success(request, "Terima kasih! Ulasan venue berhasil disimpan.")
                return redirect('booking_history')

            # target == 'coach'
            target_coach = booking.coach_schedule.coach if booking.coach_schedule else None
            if not target_coach:
                messages.error(request, "Booking ini tidak menggunakan coach, tidak bisa memberi ulasan coach.")
                return redirect('booking_history')

            if Review.objects.filter(
                customer=request.user, target_coach=target_coach, target_venue__isnull=True
            ).exists():
                messages.warning(request, "Anda sudah memberi ulasan untuk coach ini.")
                return redirect('booking_history')

            Review.objects.create(
                customer=request.user,
                target_coach=target_coach,
                rating=rating,
                comment=comment
            )
            messages.success(request, "Terima kasih! Ulasan coach berhasil disimpan.")
            return redirect('booking_history')

        # Form tidak valid
        messages.error(request, "Ada kesalahan dalam pengisian form.")
        # (biarkan terus render ulang form di bawah)

    else:
        # GET: tentukan default target
        q_target = (request.GET.get('target') or '').strip().lower()
        if q_target not in ('venue', 'coach'):
            if booking.venue_schedule and booking.venue_schedule.venue:
                q_target = 'venue'
            elif booking.coach_schedule and booking.coach_schedule.coach:
                q_target = 'coach'
            else:
                q_target = 'venue'

        form = ReviewForm(initial={'target': q_target})

    context = {'form': form, 'booking': booking}
    return render(request, 'main/submit_review.html', context)



# --- edit_review ---
from django.views.decorators.http import require_POST

@login_required(login_url='login')
@user_passes_test(lambda u: hasattr(u, 'profile') and u.profile.is_customer, login_url='home')
@require_POST
def edit_review(request, review_id):
    """Simpan perubahan review (POST-only)."""
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    review = get_object_or_404(
        Review.objects.select_related('customer'),
        id=review_id,
        customer=request.user
    )

    comment = (request.POST.get('comment') or '').strip()
    rating_raw = request.POST.get('rating')

    try:
        rating = int(rating_raw)
    except (TypeError, ValueError):
        rating = 0

    if not (1 <= rating <= 5):
        msg = 'Rating harus 1 sampai 5 bintang.'
        return JsonResponse({'success': False, 'message': msg}, status=400) if is_ajax else (
            messages.error(request, msg) or redirect('booking_history')
        )
    if not comment:
        msg = 'Komentar tidak boleh kosong.'
        return JsonResponse({'success': False, 'message': msg}, status=400) if is_ajax else (
            messages.error(request, msg) or redirect('booking_history')
        )

    review.rating = rating
    review.comment = comment
    review.save()

    msg = 'Ulasan berhasil diperbarui.'
    return JsonResponse({'success': True, 'message': msg}) if is_ajax else (
        messages.success(request, msg) or redirect('booking_history')
    )

@login_required(login_url='login')
@require_http_methods(["GET"])
def edit_review_page(request, review_id):
    review = get_object_or_404(Review, id=review_id, customer=request.user)
    # Kirim ke form edit sederhana (rating & comment)
    return render(request, 'main/review_edit_page.html', {'review': review})

@login_required(login_url='login')
@require_POST
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, customer=request.user)
    review.delete()
    messages.success(request, "Review berhasil dihapus.")
    return redirect('booking_history')
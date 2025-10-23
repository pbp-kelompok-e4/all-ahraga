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


def get_user_dashboard(user):
    if user.is_superuser or user.is_staff:
        return redirect('home') # Arahkan ke admin dashboard

    try:
        profile = user.profile 

        if profile.is_venue_owner:
            return redirect('venue_dashboard') # UBAH BARIS INI

        elif profile.is_coach:
            return redirect('coach_dashboard') # UBAH BARIS INI

        elif profile.is_customer:
            return redirect('customer_dashboard') # UBAH BARIS INI

    except UserProfile.DoesNotExist:
        pass

    return redirect('home')

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
        return get_user_dashboard(request.user)

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # AJAX
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': True, 'redirect': reverse('home')})
            messages.info(request, f"Welcome back, {user.username}.")
            return get_user_dashboard(user)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'main/login.html', {'form': form})

@login_required(login_url='login')
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('home') 

def main_view(request):
    venues = Venue.objects.all().select_related('location', 'sport_category')
    categories = SportCategory.objects.all()
    areas = LocationArea.objects.all()
    
    query = request.GET.get('q')
    if query:
        venues = venues.filter(name__icontains=query)

    context = {
        'venues': venues,
        'categories': categories,
        'areas': areas,
    }
    return render(request, 'main/home.html', context)


def venue_detail_view(request, venue_id):
    venue = get_object_or_404(Venue, pk=venue_id)
    return render(request, 'main/venue_detail.html', {'venue': venue})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def customer_dashboard_view(request):
    venues = Venue.objects.all().select_related('sport_category')
    categories = SportCategory.objects.all()
    areas = LocationArea.objects.all()
    
    query = request.GET.get('q')
    if query:
        venues = venues.filter(name__icontains=query)

    context = {
        'venues': venues,
        'categories': categories,
        'areas': areas,
    }
    return render(request, 'main/home.html', context)

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
        
        venue_revenue_data.append({
            'venue': venue,
            'bookings': confirmed_bookings,
            'total_revenue': venue_total,
            'booking_count': confirmed_bookings.count()
        })

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
                    # Format error lebih detail
                    errors_dict = {}
                    for field, error_list in equipment_form.errors.items():
                        errors_dict[field] = [str(error) for error in error_list]
                    
                    return JsonResponse({
                        'success': False, 
                        'errors': errors_dict,
                        'message': 'Validasi gagal. Periksa input Anda.'
                    }, status=400)

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
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_dashboard_view(request):
    return redirect('home')

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
        
        # Get statistics about what will be deleted
        schedules_count = venue.schedules.count()
        bookings_count = Booking.objects.filter(venue_schedule__venue=venue).count()
        
        # Check if there's a confirmation parameter
        if request.method == 'POST' and not request.POST.get('confirm_delete'):
            # If no confirmation and there are schedules/bookings, ask for confirmation
            if schedules_count > 0 or bookings_count > 0:
                warning_message = f"This venue has {schedules_count} schedules and {bookings_count} bookings. Deleting it will remove all associated data."
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'require_confirmation': True,
                        'message': warning_message,
                        'schedules_count': schedules_count,
                        'bookings_count': bookings_count
                    }, status=400)
                
                messages.warning(request, warning_message)
                # You could render a confirmation page here instead
                return redirect('venue_dashboard')
        
        # Find all related bookings to delete their transactions first
        bookings = Booking.objects.filter(venue_schedule__venue=venue)
        
        # Delete all related transactions first (to avoid integrity errors)
        Transaction.objects.filter(booking__in=bookings).delete()
        
        # Now delete the bookings
        bookings.delete()
        
        # Finally delete the venue (this will cascade delete schedules due to FK relationship)
        venue_name = venue.name
        venue.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f"Lapangan '{venue_name}' and all associated bookings successfully deleted."
            })
        
        messages.success(request, f"Lapangan '{venue_name}' and all associated bookings successfully deleted.")
        return redirect('venue_dashboard')
        
    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting venue {venue_id}: {str(e)}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': f"Error deleting venue: {str(e)}"
            }, status=500)
        
        messages.error(request, f"Error deleting venue: {str(e)}")
        return redirect('venue_dashboard')

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

    # --- Filter Jadwal yang Relevan untuk Ditampilkan (GET Request) ---
    now = timezone.localtime(timezone.now())
    today = now.date()
    current_time = now.time()

    schedules = VenueSchedule.objects.filter(
        venue=venue,
        is_booked=False,  # Hanya yang belum dibooking
        date__gte=today   # Hanya tanggal hari ini atau masa depan
    ).exclude(
        # Kecualikan jadwal hari ini yang waktunya sudah lewat
        date=today,
        start_time__lt=current_time
    ).order_by('date', 'start_time')
    # --- Akhir Filter Jadwal ---

    if request.method == 'POST':
        # --- Proses Pembuatan Booking (POST Request) ---
        schedule_id = request.POST.get('schedule_id')
        equipment_ids = request.POST.getlist('equipment') # Bisa multiple
        coach_id = request.POST.get('coach') # Bisa kosong
        payment_method = request.POST.get('payment_method', 'CASH') # Default ke CASH jika tidak ada

        if not schedule_id:
            messages.error(request, "Anda harus memilih jadwal terlebih dahulu!")
            return redirect('create_booking', venue_id=venue.id)

        try:
            # Gunakan transaksi database atomik untuk memastikan konsistensi
            with db_transaction.atomic():
                # 1. Ambil dan Kunci Jadwal Venue
                try:
                    # select_for_update() mengunci baris ini hingga transaksi selesai
                    schedule = VenueSchedule.objects.select_for_update().get(
                        id=schedule_id,
                        venue=venue,
                        is_booked=False,
                        date__gte=today # Validasi ulang tanggal
                    )
                    # Validasi ulang waktu jika tanggalnya hari ini
                    if schedule.date == today and schedule.start_time < current_time:
                         raise VenueSchedule.DoesNotExist("Jadwal yang dipilih sudah lewat.")

                except VenueSchedule.DoesNotExist as e:
                    messages.error(request, f"Jadwal tidak tersedia atau sudah dibooking. Silakan pilih jadwal lain. ({e})")
                    return redirect('create_booking', venue_id=venue.id)

                # 2. Hitung Harga Awal
                total_price = venue.price_per_hour or 0

                # 3. Proses Equipment yang Dipilih
                selected_equipment = []
                if equipment_ids:
                    # Ambil semua equipment valid dalam satu query
                    equipment_queryset = Equipment.objects.filter(id__in=equipment_ids, venue=venue)
                    for eq in equipment_queryset:
                        selected_equipment.append(eq)
                        total_price += eq.rental_price or 0

                # 4. Proses Coach yang Dipilih (jika ada)
                coach_obj = None
                coach_schedule_obj = None
                if coach_id:
                    try:
                        coach_obj = CoachProfile.objects.get(id=coach_id)
                        # Ambil dan kunci jadwal coach yang sesuai
                        coach_schedule_obj = CoachSchedule.objects.select_for_update().get(
                            coach=coach_obj,
                            date=schedule.date,         # Tanggal harus sama
                            start_time=schedule.start_time, # Jam mulai harus sama
                            is_booked=False              # Pastikan coach masih available
                        )
                        total_price += coach_obj.rate_per_hour or 0
                    except CoachProfile.DoesNotExist:
                        messages.error(request, "Coach yang Anda pilih tidak valid.")
                        raise IntegrityError("Coach profile does not exist.") # Batalkan transaksi
                    except CoachSchedule.DoesNotExist:
                        messages.error(request, f"Coach {coach_obj.user.username} tidak lagi tersedia pada jadwal yang dipilih.")
                        raise IntegrityError("Coach schedule not available.") # Batalkan transaksi

                # 5. Buat Objek Booking Utama
                booking = Booking.objects.create(
                    customer=request.user,
                    venue_schedule=schedule,
                    coach_schedule=coach_schedule_obj, # Bisa None jika tanpa coach
                    total_price=total_price,
                )

                # 6. Update Status Jadwal Venue
                schedule.is_booked = True
                # Sebaiknya jangan ubah is_available di sini jika itu flag statis
                # schedule.is_available = False
                schedule.save()

                # 7. Update Status Jadwal Coach (jika ada)
                if coach_schedule_obj:
                    coach_schedule_obj.is_booked = True
                    # coach_schedule_obj.is_available = False
                    coach_schedule_obj.save()

                # 8. Buat Relasi BookingEquipment
                booking_equipment_list = []
                for equipment in selected_equipment:
                    booking_equipment_list.append(
                        BookingEquipment(
                            booking=booking,
                            equipment=equipment,
                            quantity=1, # Asumsi kuantitas selalu 1
                            sub_total=equipment.rental_price
                        )
                    )
                if booking_equipment_list:
                    BookingEquipment.objects.bulk_create(booking_equipment_list)

                # 9. Buat Transaksi Awal (Status PENDING)
                Transaction.objects.create(
                    booking=booking,
                    status='PENDING',
                    payment_method=payment_method,
                    # Bagi hasil pendapatan (sesuaikan jika ada logika platform fee)
                    revenue_venue=venue.price_per_hour or 0,
                    revenue_coach=coach_obj.rate_per_hour if coach_obj else 0,
                    revenue_platform=0 # Ganti jika perlu
                )

        # Tangani error jika terjadi konflik selama transaksi
        except IntegrityError as e:
            # Pesan error spesifik (misal coach/jadwal tidak tersedia) sudah ditangani di atas
            # Tampilkan pesan generik hanya jika bukan error spesifik tersebut
             if "Coach" not in str(e) and "Jadwal" not in str(e):
                  messages.error(request, "Terjadi konflik saat menyimpan booking (mungkin jadwal sudah diambil). Silakan coba lagi.")
             return redirect('create_booking', venue_id=venue.id)
        except Exception as e: # Tangkap error tak terduga lainnya
             messages.error(request, f"Terjadi kesalahan tidak terduga: {e}. Silakan coba lagi.")
             return redirect('create_booking', venue_id=venue.id)

        # Jika semua proses dalam 'try' berhasil
        messages.success(request, "Booking berhasil dibuat! Segera lakukan pembayaran untuk mengonfirmasi jadwal Anda.")
        return redirect('my_bookings') # Arahkan ke halaman daftar booking pending

    # --- Konteks untuk Menampilkan Halaman (GET Request) ---
    context = {
        'venue': venue,
        'schedules': schedules, # Gunakan jadwal yang sudah difilter
        'equipment_list': equipment_list,
        'coaches': [], # List coach akan diisi oleh AJAX saat jadwal dipilih
    }
    return render(request, 'main/create_booking.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def get_available_coaches(request, schedule_id):
    try:
        schedule = VenueSchedule.objects.select_related('venue__location', 'venue__sport_category').get(id=schedule_id, is_booked=False)
        venue = schedule.venue
    except VenueSchedule.DoesNotExist:
        return JsonResponse({'error': 'Jadwal tidak ditemukan atau sudah dibooking.'}, status=404)
    
    coaches_for_schedule = CoachProfile.objects.filter(
        service_areas=venue.location,
        main_sport_trained=venue.sport_category,
        schedules__date=schedule.date,
        schedules__start_time=schedule.start_time,
        schedules__is_available=True,
        schedules__is_booked=False
    ).select_related('user', 'main_sport_trained').distinct()

    coaches_data = []
    for coach in coaches_for_schedule:
        full_name = coach.user.get_full_name() or coach.user.username
        coaches_data.append({
            'id': coach.id,
            'name': full_name,
            'avatar_initial': full_name[:1].upper(),
            'sport': coach.main_sport_trained.name,
            'rate_per_hour': float(coach.rate_per_hour or 0), 
        })

    return JsonResponse({'coaches': coaches_data})
        
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

        except IntegrityError:
            error_msg = "Terjadi kesalahan saat memproses pembayaran. Silakan coba lagi."
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
    bookings = Booking.objects.filter(customer=request.user).select_related(
        'venue_schedule__venue', 'transaction'
    ).order_by('-venue_schedule__date')

    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if query:
        bookings = bookings.filter(
            Q(venue_schedule__venue__name__icontains=query) |
            Q(id__icontains=query) 
        )

    if status:
        bookings = bookings.filter(transaction__status=status)

    context = {
        'bookings': bookings
    }

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
def manage_coach_profile(request):
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        coach_profile = CoachProfile(user=request.user)

    if request.method == 'POST':
        form = CoachProfileForm(request.POST, request.FILES, instance=coach_profile)
        if form.is_valid():
            profile = form.save()
            messages.success(request, "Perubahan profil berhasil disimpan.")
            return redirect('coach_profile') 
        
        else:
            messages.error(request, "Perubahan gagal disimpan. Mohon periksa input Anda.")
    else:
        form = CoachProfileForm(instance=coach_profile)

    return render(request, 'main/manage_coach_profile.html', {'form': form, 'coach_profile': coach_profile})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def delete_coach_profile(request):
    coach_profile = get_object_or_404(CoachProfile, user=request.user)

    if request.method == 'POST':
        coach_profile.delete()
        messages.success(request, "Profil pelatih berhasil dihapus.")
        return redirect('home') 

    return render(request, 'main/confirm_delete_coach_profile.html', {'coach_profile': coach_profile})

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
    context = {
        'coach_profile': coach_profile, # Bisa None
        'schedules': schedules,         # Bisa queryset kosong
        'form': form,                   # Form kosong
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

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_revenue_report(request):
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        messages.info(request, "Silakan lengkapi profil pelatih terlebih dahulu sebelum melihat laporan pendapatan.")
        return redirect('manage_coach_profile')

    transactions = Transaction.objects.filter(booking__coach_schedule__coach=coach_profile, status='CONFIRMED')
    total_revenue = transactions.aggregate(Sum('revenue_coach'))['revenue_coach__sum'] or 0

    context = {
        'transactions': transactions,
        'total_revenue': total_revenue,
    }
    return render(request, 'main/coach_revenue_report.html', context)

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
    # --- AKHIR LOGIKA AJAX DELETE ---

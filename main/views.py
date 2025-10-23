from django.db import transaction as db_transaction, IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm 
from django.contrib import messages
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
        return redirect('admin_dashboard_view') # Arahkan ke admin dashboard

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
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()

            messages.success(request, "Pendaftaran berhasil! Silakan masuk.")
            return redirect('login') 
        else:
            messages.error(request, "Mohon periksa input Anda.")
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
            messages.info(request, f"Selamat datang kembali, {user.username}.")
            return get_user_dashboard(user)
        else:
            messages.error(request, "Username atau password salah.")
    else:
        form = AuthenticationForm()

    return render(request, 'main/login.html', {'form': form})

@login_required(login_url='login')
def logout_view(request):
    logout(request)
    messages.info(request, "Anda telah berhasil keluar.")
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
    venues = Venue.objects.filter(owner=request.user)
    context = {
        'venues': venues,
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
        form = VenueForm(request.POST, request.FILES)  # Tambahkan request.FILES
        if form.is_valid():
            user = request.user
            venue = form.save(commit=False)
            venue.owner = user
            venue.save()
            messages.success(request, f"Lapangan '{venue.name}' berhasil ditambahkan.")
            return redirect('venue_dashboard')
    else:
        form = VenueForm()

    return render(request, 'main/venue_form.html', {'form': form, 'page_title': 'Tambah Lapangan Baru'})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_manage_view(request, venue_id):
    venue = get_object_or_404(Venue, id=venue_id, owner=request.user)

    venue_edit_form = VenueForm(instance=venue)
    equipment_form = EquipmentForm()

    if request.method == 'POST':
        if 'submit_venue_edit' in request.POST:
            venue_edit_form = VenueForm(request.POST, request.FILES, instance=venue)
            if venue_edit_form.is_valid():
                venue_edit_form.save()
                messages.success(request, "Data lapangan berhasil diperbarui.")
                return redirect('venue_manage', venue_id=venue.id)


        elif 'submit_equipment' in request.POST:
            equipment_form = EquipmentForm(request.POST)
            if equipment_form.is_valid():
                equipment = equipment_form.save(commit=False)
                equipment.venue = venue 
                equipment.save()
                messages.success(request, "Equipment baru berhasil ditambahkan.")
                return redirect('venue_manage', venue_id=venue.id)
            
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
    """View baru untuk membuat dan menampilkan jadwal venue."""
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
    venue = get_object_or_404(Venue, pk=venue_id)
    
    if venue.owner != request.user:
        messages.error(request, "Anda tidak memiliki izin untuk menghapus lapangan ini.")
        return redirect('venue_dashboard')
    
    venue_name = venue.name
    venue.delete()
    messages.success(request, f"Lapangan '{venue_name}' berhasil dihapus.")
    return redirect('venue_dashboard')

def admin_dashboard_view(request):
    if not is_admin(request.user):
        return redirect('home')
    return redirect('home')

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def create_booking(request, venue_id):
    venue = get_object_or_404(Venue, id=venue_id)
    schedules = VenueSchedule.objects.filter(venue=venue, is_available=True, is_booked=False).order_by('date', 'start_time')
    equipment_list = Equipment.objects.filter(venue=venue)

    if request.method == 'POST':
        schedule_id = request.POST.get('schedule_id')
        equipment_ids = request.POST.getlist('equipment')
        coach_id = request.POST.get('coach')
        payment_method = request.POST.get('payment_method')

        if not schedule_id:
            messages.error(request, "Pilih jadwal terlebih dahulu!")
            return redirect('create_booking', venue_id=venue.id)

        try:
            with db_transaction.atomic():
                try:
                    schedule = VenueSchedule.objects.select_for_update().get(
                        id=schedule_id, 
                        venue=venue, 
                        is_booked=False
                    )
                except VenueSchedule.DoesNotExist:
                    messages.error(request, "Jadwal tidak tersedia atau sudah dibooking oleh orang lain.")
                    return redirect('create_booking', venue_id=venue.id)

                total_price = venue.price_per_hour or 0

                selected_equipment = []
                if equipment_ids:
                    for equipment_id in equipment_ids:
                        try:
                            equipment = Equipment.objects.get(id=equipment_id, venue=venue)
                            selected_equipment.append(equipment)
                            total_price += equipment.rental_price or 0
                        except Equipment.DoesNotExist:
                            continue

                coach_obj = None
                coach_schedule_obj = None

                if coach_id:
                    try:
                        coach_obj = CoachProfile.objects.get(id=coach_id)
                        coach_schedule_obj = CoachSchedule.objects.select_for_update().filter(
                            coach=coach_obj,
                            date=schedule.date,
                            start_time=schedule.start_time,
                            is_available=True,
                            is_booked=False
                        ).first()

                        if not coach_schedule_obj:
                            messages.error(request, f"Coach {coach_obj.user.get_full_name()} tidak tersedia pada jadwal yang dipilih.")
                            raise IntegrityError("Coach schedule not available") 
                    
                        total_price += coach_obj.rate_per_hour or 0

                    except CoachProfile.DoesNotExist:
                        messages.error(request, "Coach yang dipilih tidak valid.")
                        raise IntegrityError("Coach profile does not exist")

                booking = Booking.objects.create(
                    customer=request.user,
                    venue_schedule=schedule,
                    coach_schedule=coach_schedule_obj,
                    total_price=total_price,
                )

                schedule.is_booked = True
                schedule.is_available = False
                schedule.save()

                if coach_schedule_obj:
                    coach_schedule_obj.is_booked = True
                    coach_schedule_obj.is_available = False
                    coach_schedule_obj.save()

                for equipment in selected_equipment:
                    BookingEquipment.objects.create(
                        booking=booking, 
                        equipment=equipment, 
                        quantity=1, 
                        sub_total=equipment.rental_price
                    )

                Transaction.objects.create(
                    booking=booking,
                    status='PENDING',
                    payment_method=payment_method,
                    revenue_venue=venue.price_per_hour or 0,
                    revenue_coach=coach_obj.rate_per_hour if coach_obj else 0,
                    revenue_platform=0
                )
        
        except IntegrityError as e:
            if "Coach" not in str(e):
                 messages.error(request, "Terjadi kesalahan tak terduga saat booking. Silakan coba lagi.")
            return redirect('create_booking', venue_id=venue.id)

        messages.success(request, "Booking dibuat. Lakukan pembayaran untuk mengonfirmasi.")
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
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        return JsonResponse({"success": False, "message": "Profil pelatih tidak ditemukan."}, status=400)

    form = CoachScheduleForm(request.POST or None) 
    schedules = coach_profile.schedules.all().order_by('date', 'start_time')

    if request.method == 'POST':
        form = CoachScheduleForm(request.POST) 
        if form.is_valid():
            end_time_global_str = request.POST.get('end_time_global') 

            cd = form.cleaned_data
            schedule_date = cd['date']
            start_time_slot = cd['start_time']
            is_available = cd.get('is_available', True)
            
            try:
                start_dt = datetime.combine(schedule_date, start_time_slot)
                end_dt = datetime.strptime(end_time_global_str, '%H:%M')
                end_dt = datetime.combine(schedule_date, end_dt.time())
            except (ValueError, TypeError):
                return JsonResponse({"success": False, "message": "Format jam atau tanggal tidak valid."}, status=400)

            if end_dt <= start_dt:
                return JsonResponse({"success": False, "message": "Waktu selesai harus setelah waktu mulai."}, status=400)

            created = 0
            
            # --- INI BAGIAN PENTING YANG HARUS DIPERBARUI ---
            new_slots_data = [] # Array untuk menampung slot baru
            current = start_dt
            
            while current < end_dt:
                slot_start = current.time()
                next_dt = current + timedelta(hours=1)
                slot_end = next_dt.time()
                
                if next_dt > end_dt:
                    slot_end = end_dt.time()
                    
                exists = CoachSchedule.objects.filter(
                    coach=coach_profile, date=schedule_date, start_time=slot_start
                ).exists()

                if not exists:
                    # Simpan objek yang baru dibuat
                    new_schedule = CoachSchedule.objects.create(
                        coach=coach_profile, date=schedule_date, start_time=slot_start,
                        end_time=slot_end, is_available=is_available
                    )
                    created += 1
                    # Tambahkan data yang relevan untuk frontend
                    new_slots_data.append({
                        'id': new_schedule.id,
                        'date_str_iso': new_schedule.date.strftime('%Y-%m-%d'),
                        'date_str_display': new_schedule.date.strftime('%A, %d %b %Y'), # Format: "l, d M Y"
                        'start_time': new_schedule.start_time.strftime('%H:%M'),
                        'end_time': new_schedule.end_time.strftime('%H:%M'),
                        'is_booked': False,
                    })

                current = next_dt

            # Ganti respons JSON untuk menyertakan data slot baru
            return JsonResponse({
                "success": True, 
                "message": f"{created} slot jadwal berhasil ditambahkan.",
                "new_slots": new_slots_data # <-- INI KUNCINYA
            }, status=200)
            # --- PERUBAHAN SELESAI ---
        else:
            return JsonResponse({"success": False, "message": "Data form tidak valid.", "errors": form.errors}, status=400)


    # LOGIC GET (Menampilkan halaman)
    context = {
        'coach_profile': coach_profile,
        'schedules': schedules,
        'form': form,
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

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
    schedule_form = VenueScheduleForm()
    equipment_form = EquipmentForm()

    if request.method == 'POST':
        if 'submit_venue_edit' in request.POST:
            venue_edit_form = VenueForm(request.POST, request.FILES, instance=venue)  # Tambahkan request.FILES
            if venue_edit_form.is_valid():
                venue_edit_form.save()
                messages.success(request, "Data lapangan berhasil diperbarui.")
                return redirect('venue_manage', venue_id=venue.id)

        elif 'submit_schedule' in request.POST:
            schedule_form = VenueScheduleForm(request.POST)
            if schedule_form.is_valid():
                cd = schedule_form.cleaned_data
                schedule_date = cd['date']
                start_time = cd['start_time']
                end_time = cd['end_time']
                is_available = cd.get('is_available', True)

                start_dt = datetime.combine(schedule_date, start_time)
                end_dt = datetime.combine(schedule_date, end_time)
                if end_dt <= start_dt:
                    messages.error(request, "Waktu selesai harus setelah waktu mulai.")
                    return redirect('venue_manage', venue_id=venue.id)

                created = 0
                skipped = 0
                current = start_dt
                while current < end_dt:
                    slot_start = current.time()
                    next_dt = current + timedelta(hours=1)
                    slot_end = next_dt.time() if next_dt <= end_dt else end_time

                    exists = VenueSchedule.objects.filter(
                        venue=venue, date=schedule_date, start_time=slot_start
                    ).exists()

                    if not exists:
                        VenueSchedule.objects.create(
                            venue=venue,
                            date=schedule_date,
                            start_time=slot_start,
                            end_time=slot_end,
                            is_available=is_available
                        )
                        created += 1
                    else:
                        skipped += 1

                    current = next_dt

                messages.success(request, f"{created} jadwal dibuat. {skipped} dilewati karena sudah ada.")
                return redirect('venue_manage', venue_id=venue.id)

        elif 'submit_equipment' in request.POST:
            equipment_form = EquipmentForm(request.POST)
            if equipment_form.is_valid():
                equipment = equipment_form.save(commit=False)
                equipment.venue = venue # Set venue
                equipment.save()
                messages.success(request, "Equipment baru berhasil ditambahkan.")
                return redirect('venue_manage', venue_id=venue.id)
            
    venue_location = venue.location 
    available_coaches = CoachProfile.objects.filter(
        service_areas=venue_location, 
        is_verified=True
    )

    schedules = venue.schedules.all().order_by('date', 'start_time')
    equipments = venue.equipment.all()

    context = {
        'venue': venue,
        'venue_edit_form': venue_edit_form,
        'schedule_form': schedule_form,
        'equipment_form': equipment_form,
        'schedules': schedules,
        'equipments': equipments,
        'available_coaches': available_coaches,
    }
    return render(request, 'main/venue_manage.html', context)

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
    

    availabe_coaches_map = {}
    for schedule in schedules:
        coaches_for_schedule = CoachProfile.objects.filter(
            service_areas=venue.location,
            main_sport_trained=venue.sport_category,
            schedules__date=schedule.date,
            schedules__start_time=schedule.start_time,
            schedules__is_available=True,
            schedules__is_booked=False
        ).select_related('user').distinct()
        availabe_coaches_map[schedule.id] = list(coaches_for_schedule)

    coaches_set = set()
    for coach_list in availabe_coaches_map.values():
        coaches_set.update(coach_list)
    coaches = list(coaches_set)

    if request.method == 'POST':
        schedule_id = request.POST.get('schedule_id')
        equipment_ids = request.POST.getlist('equipment')
        coach_id = request.POST.get('coach')
        payment_method = request.POST.get('payment_method')

        if not schedule_id:
            messages.error(request, "Pilih jadwal terlebih dahulu!")
            return redirect('create_booking', venue_id=venue.id)

        try:
            schedule = VenueSchedule.objects.get(id=schedule_id, venue=venue, is_booked=False)
        except VenueSchedule.DoesNotExist:
            messages.error(request, "Jadwal tidak tersedia atau sudah dibooking.")
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

        # Buat CoachSchedule jika coach dipilih
        coach_obj = None
        coach_schedule_obj = None

        if coach_id:
            try:
                coach_obj = CoachProfile.objects.get(id=coach_id)
                coach_schedule_obj = CoachSchedule.objects.filter(
                    coach=coach_obj,
                    date=schedule.date,
                    start_time=schedule.start_time,
                    is_available=True,
                    is_booked=False
                ).first()

                if not coach_schedule_obj:
                    messages.error(request, f"Coach {coach_obj.user.get_full_name()} tidak tersedia pada jadwal yang dipilih ({schedule.date.strftime('%d/%m')} jam {schedule.start_time.strftime('%H:%M')}).")
                    return redirect('create_booking', venue_id=venue.id)
            
                total_price += coach_obj.rate_per_hour or 0

            except CoachProfile.DoesNotExist:
                messages.error(request, "Coach yang dipilih tidak valid.")
                return redirect('create_booking', venue_id=venue.id)
            
        # Buat booking
        booking = Booking.objects.create(
            customer=request.user,
            venue_schedule=schedule,
            coach_schedule=coach_schedule_obj,
            total_price=total_price,
        )

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

        messages.success(request, "Booking dibuat. Lakukan pembayaran untuk mengonfirmasi.")
        return redirect('my_bookings')

    context = {
        'venue': venue,
        'schedules': schedules,
        'equipment_list': equipment_list,
        'coaches': coaches,
    }
    return render(request, 'main/create_booking.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def customer_payment(request, booking_id):
    # Konfirmasi pembayaran
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    transaction = booking.transaction

    if transaction.payment_method and transaction.payment_method.upper() == 'CASH':
        if transaction.status != 'CONFIRMED':
            transaction.status = 'CONFIRMED'
            transaction.save()

            venue_schedule = booking.venue_schedule
            venue_schedule.is_booked = True
            venue_schedule.is_available = False
            venue_schedule.save()

            if booking.coach_schedule:
                coach_schedule = booking.coach_schedule
                coach_schedule.is_booked = True
                coach_schedule.is_available = False
                coach_schedule.save()

        return redirect('my_bookings')
    
    if request.method == 'POST':
        transaction.status = 'CONFIRMED'
        transaction.save()

        venue_schedule = booking.venue_schedule
        venue_schedule.is_booked = True
        venue_schedule.is_available = False
        venue_schedule.save()

        if booking.coach_schedule:
            coach_schedule = booking.coach_schedule
            coach_schedule.is_booked = True
            coach_schedule.is_available = False
            coach_schedule.save()

        return redirect('my_bookings')
    context = {
        'booking': booking,
        'transaction': transaction,
    }

    return render(request, 'main/customer_payment.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def booking_history(request):
    bookings = Booking.objects.filter(customer=request.user).select_related('venue_schedule__venue', 'transaction').order_by(
        '-venue_schedule__date')
    context = {
        'bookings' : bookings
    }

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

    context = {
        'bookings' : bookings
    }

    return render(request, 'main/my_bookings.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def delete_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)

    if booking.transaction and booking.transaction.status == 'PENDING':
        booking.transaction.delete()
        booking.delete()
    return redirect('home')
  
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
            profile = form.save(commit=False)
            
            url = form.cleaned_data.get('profile_picture_url')
            if url:
                try:
                    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urlopen(req, timeout=10) as resp:
                        data = resp.read()
                        if data:
                            filename = url.split('/')[-1].split('?')[0] or f'coach_{request.user.id}.jpg'
                            profile.profile_picture.save(filename, ContentFile(data), save=False)
                except (HTTPError, URLError, ValueError, TimeoutError) as e:
                    messages.error(request, f"Gagal mengambil gambar dari URL: {e}")

            profile.save()
            form.save_m2m()
            
            profile_url = reverse('coach_profile') 
            return redirect(f'{profile_url}?success=true')
        
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
    """
    Tampilkan dan tambahkan jadwal pelatih (per jam). 
    Jika belum ada CoachProfile, arahkan ke manage_coach_profile.
    """
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        messages.info(request, "Silakan buat profil pelatih terlebih dahulu.")
        return redirect('manage_coach_profile')

    form = CoachScheduleForm()
    schedules = coach_profile.schedules.all().order_by('date', 'start_time')

    if request.method == 'POST':
        form = CoachScheduleForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            schedule_date = cd['date']
            start_time = cd['start_time']
            end_time = cd['end_time']
            is_available = cd.get('is_available', True)

            start_dt = datetime.combine(schedule_date, start_time)
            end_dt = datetime.combine(schedule_date, end_time)
            if end_dt <= start_dt:
                messages.error(request, "Waktu selesai harus setelah waktu mulai.")
                return redirect('coach_schedule')

            created = 0
            skipped = 0
            current = start_dt
            while current < end_dt:
                slot_start = current.time()
                next_dt = current + timedelta(hours=1)
                slot_end = next_dt.time() if next_dt <= end_dt else end_time

                exists = CoachSchedule.objects.filter(
                    coach=coach_profile, date=schedule_date, start_time=slot_start
                ).exists()

                if not exists:
                    CoachSchedule.objects.create(
                        coach=coach_profile,
                        date=schedule_date,
                        start_time=slot_start,
                        end_time=slot_end,
                        is_available=is_available
                    )
                    created += 1
                else:
                    skipped += 1

                current = next_dt

            messages.success(request, f"{created} jadwal dibuat. {skipped} dilewati karena sudah ada.")
            return redirect('coach_schedule')
        else:
            messages.error(request, "Mohon periksa input jadwal.")
            return redirect('coach_schedule')

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
        return redirect('coach_schedule')

    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        messages.error(request, "Profil pelatih tidak ditemukan.")
        return redirect('coach_schedule')

    ids = request.POST.getlist('selected_schedules')
    deleted = 0
    for sid in ids:
        try:
            cs = CoachSchedule.objects.get(id=sid, coach=coach_profile)
            if cs.is_booked:
                messages.warning(request, f"Slot {cs.date} {cs.start_time.strftime('%H:%M')} tidak dapat dihapus (sudah dibooking).")
                continue
            cs.delete()
            deleted += 1
        except CoachSchedule.DoesNotExist:
            continue

    messages.success(request, f"{deleted} jadwal berhasil dihapus.")
    return redirect('coach_schedule')

def coach_list_view(request):
    """Menampilkan daftar semua coach"""
    coaches = CoachProfile.objects.all().select_related(
        'user', 'main_sport_trained'
    ).prefetch_related('service_areas')
    
    # Filter berdasarkan pencarian
    query = request.GET.get('q')
    if query:
        coaches = coaches.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )
    
    # Filter berdasarkan olahraga
    sport_filter = request.GET.get('sport')
    if sport_filter:
        coaches = coaches.filter(main_sport_trained__id=sport_filter)
    
    # Filter berdasarkan area
    area_filter = request.GET.get('area')
    if area_filter:
        coaches = coaches.filter(service_areas__id=area_filter)
    
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


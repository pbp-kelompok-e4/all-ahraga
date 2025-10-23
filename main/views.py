from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm 
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import date
from .forms import CustomUserCreationForm, VenueForm, VenueScheduleForm, EquipmentForm
from .models import Venue, SportCategory, LocationArea, CoachProfile, VenueSchedule, Transaction, Review, UserProfile, Booking, BookingEquipment, Equipment

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
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()

            messages.success(request, "Registration successful! Please log in.")
            return redirect('login') 
        else:
            messages.error(request, "Please check your input.")
    else:
        form = CustomUserCreationForm()
    venues = Venue.objects.all().select_related('location')
    show_coach = False
    if request.method == 'POST' and request.POST.get('role_type') == 'COACH':
        show_coach = True
    return render(request, 'main/register.html', {'form': form, 'venues': venues, 'show_coach_fields': show_coach})

def login_view(request):
    if request.user.is_authenticated:
        return get_user_dashboard(request.user)
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST) 
        
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.info(request, f"Welcome back, {user.username}.")
            return get_user_dashboard(user)
        else:
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
    total_revenue = Transaction.objects.filter(
        booking__venue_schedule__venue__id__in=venue_ids,
        status='CONFIRMED'
    ).aggregate(total=Sum('revenue_venue'))['total'] or 0.00

    context = {
        'total_revenue': total_revenue,
    }
    return render(request, 'main/venue_revenue.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_create_view(request):
    if request.method == 'POST':
        form = VenueForm(request.POST)
        if form.is_valid():
            venue = form.save(commit=False)
            venue.owner = request.user  # Set owner
            venue.save()
            messages.success(request, f"Lapangan '{venue.name}' berhasil ditambahkan.")
            return redirect('venue_dashboard')
    else:
        form = VenueForm()

    return render(request, 'main/venue_form.html', {'form': form, 'page_title': 'Tambah Lapangan Baru'})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_manage_view(request, venue_id):
    # Pastikan venue ada dan milik user
    venue = get_object_or_404(Venue, id=venue_id, owner=request.user)

    # Siapkan semua form
    venue_edit_form = VenueForm(instance=venue)
    schedule_form = VenueScheduleForm()
    equipment_form = EquipmentForm()

    if request.method == 'POST':
        # Cek form mana yang di-submit
        if 'submit_venue_edit' in request.POST:
            venue_edit_form = VenueForm(request.POST, instance=venue)
            if venue_edit_form.is_valid():
                venue_edit_form.save()
                messages.success(request, "Data lapangan berhasil diperbarui.")
                return redirect('venue_manage', venue_id=venue.id)

        elif 'submit_schedule' in request.POST:
            schedule_form = VenueScheduleForm(request.POST)
            if schedule_form.is_valid():
                schedule = schedule_form.save(commit=False)
                schedule.venue = venue # Set venue
                schedule.save()
                messages.success(request, "Jadwal baru berhasil ditambahkan.")
                return redirect('venue_manage', venue_id=venue.id)

        elif 'submit_equipment' in request.POST:
            equipment_form = EquipmentForm(request.POST)
            if equipment_form.is_valid():
                equipment = equipment_form.save(commit=False)
                equipment.venue = venue # Set venue
                equipment.save()
                messages.success(request, "Equipment baru berhasil ditambahkan.")
                return redirect('venue_manage', venue_id=venue.id)
            
    # 1. Dapatkan lokasi dari venue tersebut
    venue_location = venue.location 

    # 2. Filter semua CoachProfile yang area layanannya (service_areas)
    #    mencakup lokasi venue tersebut.
    available_coaches = CoachProfile.objects.filter(
        service_areas=venue_location, 
        is_verified=True # Pastikan hanya pelatih terverifikasi
    )

    # Ambil data untuk ditampilkan di list
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
    # Ambil data
    venue = get_object_or_404(Venue, id=venue_id)
    schedules = VenueSchedule.objects.filter(venue=venue, is_available=True, is_booked=False).order_by('date', 'start_time')
    equipment_list = Equipment.objects.filter(venue=venue)
    coaches = CoachProfile.objects.filter(service_areas=venue.location, is_verified=True)

    # Jika user book 
    if request.method == 'POST':
        schedule_id = request.POST.get('schedule_id')
        equipment_ids = request.POST.getlist('equipment')
        coach_id = request.POST.get('coach')

        # Validasi jadwal
        if not schedule_id:
            messages.error(request, "Pilih jadwal terlebih dahulu!")
            return redirect('create_booking', venue_id=venue.id)
        try:
            schedule = VenueSchedule.objects.get(id=schedule_id, venue=venue, is_booked=False)
        except VenueSchedule.DoesNotExist:
            messages.error(request, "Jadwal sudah dibooking")
            return redirect('create_booking', venue_id=venue.id)
        
        total_price = venue.price_per_hour

        # Jika user ingin sewa equipment
        selected_equipment = []
        if equipment_ids:
            for equipment_id in equipment_ids:
                try:
                    equipment = Equipment.objects.get(id=equipment_id, venue=venue)
                    selected_equipment.append(equipment)
                    total_price += equipment.rental_price
                except Equipment.DoesNotExist:
                    continue
        
        # Jika user ingin sewa coach
        coach_schedule = None
        coach = None
        if coach_id:
            try:
                coach = CoachProfile.objects.get(id=coach_id, service_area=venue.location)
                total_price += coach.rate_per_hour
                coach_schedule = CoachProfile.objects.filter(coach=coach, date=schedule.date, is_available=True, is_booked=False).first()
            except coach.DoesNotExist:
                coach = None

        # Buat dan simpan booking baru
        booking = Booking.objects.create(
            customer=request.user, 
            venue_schedule=schedule, 
            coach_schedule=coach_schedule if coach_schedule else None, 
            total_price=total_price,
        )

        schedule.is_booked = True
        schedule.save()

        if coach_schedule:
            coach_schedule.is_booked = True
            coach_schedule.save()

        for equipment in selected_equipment:
            BookingEquipment.objects.create(
                booking=booking, equipment=equipment, quantity=1, sub_total=equipment.rental_price
            )
        
        # Buat dan simpan transaksi baru
        Transaction.objects.create(
            booking=booking, 
            status='PENDING', 
            payment_method='TRANSFER', 
            revenue_venue=venue.price_per_hour,
            revenue_coach=coach.rate_per_hour if coach else 0,
            revenue_platform=0
        )

        return redirect('home')

    context = {
        'venue': venue,
        'schedules': schedules,
        'equipment_list': equipment_list,
        'coaches': coaches,
    }
    return render(request, 'main/home.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def customer_payment(request, booking_id):
    # Konfirmasi pembayaran
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    transaction = booking.transaction
    transaction.status = 'CONFIRMED'
    transaction.save()
    return redirect('home')

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


def landing_view(request):
    feedback_list = Review.objects.select_related('customer', 'target_venue').order_by('-created_at')

    contributors = {}
    for fb in feedback_list:
        uid = fb.customer.id
        if uid not in contributors:
            contributors[uid] = {
                'username': fb.customer.username,
                'count': 0,
                'sum': 0,
                'last_message': fb.comment,
            }
        contributors[uid]['count'] += 1
        contributors[uid]['sum'] += fb.rating
        contributors[uid]['last_message'] = fb.comment

    feedback_contributors = []
    for v in contributors.values():
        avg = round(v['sum'] / v['count'], 2) if v['count'] else 0
        feedback_contributors.append({'username': v['username'], 'count': v['count'], 'avg_rating': avg, 'last_message': v['last_message']})

    featured_venues = Venue.objects.annotate(review_count=Count('reviews')).order_by('-review_count')[:6]

    user_bookings = None
    if request.user.is_authenticated:
        user_bookings = Booking.objects.filter(customer=request.user).select_related('venue_schedule__venue').order_by('-booking_time')

    context = {
        'feedback_list': feedback_list,
        'feedback_contributors': feedback_contributors,
        'featured_venues': featured_venues,
        'user_bookings': user_bookings,
    }
    return render(request, 'main/landing.html', context)


@login_required(login_url='login')
@require_POST
def add_review_ajax(request):
    booking_id = request.POST.get('booking_id')
    rating = request.POST.get('rating')
    message = request.POST.get('message')

    if not booking_id or not rating or not message:
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)

    try:
        booking = Booking.objects.select_related('venue_schedule__venue').get(id=booking_id, customer=request.user)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Booking not found'}, status=404)

    venue = booking.venue_schedule.venue

    if Review.objects.filter(customer=request.user, target_venue=venue).exists():
        return JsonResponse({'success': False, 'error': 'You have already reviewed this venue'}, status=400)

    try:
        rating_int = int(rating)
        if rating_int < 1 or rating_int > 5:
            raise ValueError()
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid rating'}, status=400)

    review = Review.objects.create(customer=request.user, target_venue=venue, rating=rating_int, comment=message)

    resp = {
        'success': True,
        'review': {
            'id': review.id,
            'customer': request.user.username,
            'rating': review.rating,
            'comment': review.comment,
        }
    }
    return JsonResponse(resp)


@login_required(login_url='login')
def add_feedback(request):
    if request.method == 'POST':
        rating = request.POST.get('rating')
        message = request.POST.get('message')
        booking = Booking.objects.filter(customer=request.user).select_related('venue_schedule__venue').first()
        if not booking:
            messages.error(request, 'No booking found to leave feedback.')
            return redirect('home')
        try:
            rating_int = int(rating)
        except (ValueError, TypeError):
            messages.error(request, 'Invalid rating.')
            return redirect('add_feedback')
        Review.objects.create(customer=request.user, target_venue=booking.venue_schedule.venue, rating=rating_int, comment=message)
        messages.success(request, 'Feedback added successfully.')
        return redirect('landing')
    return render(request, 'main/add_feedback.html')


@login_required(login_url='login')
def edit_feedback(request, feedback_id):
    fb = get_object_or_404(Review, id=feedback_id)
    if fb.customer != request.user:
        messages.error(request, 'You do not have permission to edit this feedback.')
        return redirect('landing')
    if request.method == 'POST':
        rating = request.POST.get('rating')
        message = request.POST.get('message')
        try:
            rating_int = int(rating)
        except (ValueError, TypeError):
            messages.error(request, 'Invalid rating.')
            return redirect('edit_feedback', feedback_id=fb.id)
        fb.rating = rating_int
        fb.comment = message
        fb.save()
        messages.success(request, 'Feedback updated successfully.')
        return redirect('landing')
    return render(request, 'main/edit_feedback.html', {'feedback': fb})


@login_required(login_url='login')
def delete_feedback(request, feedback_id):
    fb = get_object_or_404(Review, id=feedback_id)
    if fb.customer != request.user:
        messages.error(request, 'You do not have permission to delete this feedback.')
        return redirect('landing')
    if request.method == 'POST':
        fb.delete()
        messages.success(request, 'Feedback deleted successfully.')
        return redirect('landing')
    return render(request, 'main/edit_feedback.html', {'feedback': fb})
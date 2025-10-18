from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm 
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum
from datetime import date
from .forms import CustomUserCreationForm
from .models import Venue, SportCategory, LocationArea, CoachProfile, VenueSchedule, Transaction, Review, UserProfile, Booking, BookingEquipment, Equipment

def get_user_dashboard(user):
    if user.is_superuser or user.is_staff:
        return redirect('home')
    
    try:
        profile = user.profile 
        
        if profile.is_venue_owner:
            return redirect('home')
        
        elif profile.is_coach:
            return redirect('home')
        
        elif profile.is_customer:
            return redirect('home')
            
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
    return redirect('home')

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_dashboard_view(request):
    return redirect('home')

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_dashboard_view(request):
    return redirect('home')

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
    coaches = CoachProfile.objects.filter(service_area=venue.location, is_verified=True)

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

        return redirect('customer_bookings')

    context = {
        'venue': venue,
        'schedules': schedules,
        'equipment_list': equipment_list,
        'coaches': coaches,
    }
    return render(request, 'main/venue_booking.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def customer_booking(request):
    # Menampilkan semua bookingan user
    bookings = Booking.objects.filter(customer=request.user).select_related('venue_schedule', 'transaction')
    return render(request, 'main/customer_booking.html', {'bookings' : bookings})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def customer_payment(request, booking_id):
    # Konfirmasi pembayaran
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    transaction = booking.transaction
    transaction.status = 'CONFIRMED'
    transaction.save()
    return redirect(customer_booking)
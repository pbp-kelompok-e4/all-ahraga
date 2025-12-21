from django.db import transaction as db_transaction, IntegrityError
from django.db.models import Avg
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
from django.http import HttpResponse
from django.core import serializers
from django.views.decorators.csrf import csrf_exempt
from django.utils.formats import date_format 
import base64
import requests

def get_user_dashboard(user):
    redirect_url_name = get_dashboard_redirect_url_name(user)
    return redirect(reverse(redirect_url_name))

def get_dashboard_redirect_url_name(user):
    """
    Mengembalikan 'nama' URL (name=...) untuk dashboard 
    berdasarkan role pengguna.
    """
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

def index_view(request):
    """
    View "Dispatcher" untuk root URL ('').
    - Pengguna non-auth -> Tampilkan landing.html
    - Pengguna auth -> Redirect ke dashboard masing-masing.
    """
    if request.user.is_authenticated:
        redirect_url_name = get_dashboard_redirect_url_name(request.user)
        return redirect(reverse(redirect_url_name))
    

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
        return get_user_dashboard(request.user)

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        
            redirect_url_name = get_dashboard_redirect_url_name(user)
            final_redirect_url = reverse(redirect_url_name)
            
            role_type = 'CUSTOMER'
            if user.is_superuser:
                role_type = 'ADMIN'
            elif hasattr(user, 'profile'):
                if user.profile.is_venue_owner:
                    role_type = 'VENUE_OWNER'
                elif user.profile.is_coach:
                    role_type = 'COACH'

            if is_ajax:
                return JsonResponse({
                    'ok': True, 
                    'redirect': final_redirect_url,
                    'username': user.username,
                    'is_superuser': user.is_superuser, 
                    'role_type': role_type             
                })
            else:
                messages.info(request, f"Welcome back, {user.username}.")
                return redirect(final_redirect_url)

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
    return redirect(f"{reverse('landing')}?logout=1")

@login_required(login_url='login') 
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='index') 
def main_view(request):
    """Main page untuk customer - list venues dengan filter"""
    if not request.user.is_authenticated or not request.user.profile.is_customer:
        return redirect('home')
    
    venues = Venue.objects.all().select_related('location', 'sport_category', 'owner')
    
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
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    venues = Venue.objects.filter(owner=request.user)
    venue_ids = venues.values_list('id', flat=True)
    

    total_revenue = Transaction.objects.filter(
        booking__venue_schedule__venue__id__in=venue_ids,
        status='CONFIRMED'
    ).aggregate(total=Sum('revenue_venue'))['total'] or 0.00

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

    if is_ajax:
        return JsonResponse({
            'success': True,
            'total_revenue': float(total_revenue),
            'venue_revenue_data': venue_revenue_data
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
        form = VenueForm(request.POST)
        if form.is_valid():
            user = request.user
            venue = form.save(commit=False)
            venue.owner = user
            venue.payment_options = 'TRANSFER'
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
                        'image_url': venue.main_image if venue.main_image else '',
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
            venue_edit_form = VenueForm(request.POST, instance=venue)
            if venue_edit_form.is_valid():
                updated_venue = venue_edit_form.save()
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Data lapangan berhasil diperbarui.',
                        'venue': {
                            'id': updated_venue.id,
                            'name': updated_venue.name,
                            'description': updated_venue.description,
                            'location': updated_venue.location.name,
                            'sport_category': updated_venue.sport_category.name,
                            'price_per_hour': updated_venue.price_per_hour,
                            'payment_options': updated_venue.payment_options,
                            'main_image': updated_venue.main_image if updated_venue.main_image else ''
                        }
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
                    errors_dict = {}
                    for field, error_list in equipment_form.errors.items():
                        errors_dict[field] = [str(error) for error in error_list]
                    
                    return JsonResponse({
                        'success': False, 
                        'errors': errors_dict,
                        'message': 'Validasi gagal. Periksa input Anda.'
                    }, status=400)

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

@csrf_exempt
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_manage_schedule_view(request, venue_id):
    venue = get_object_or_404(Venue, id=venue_id, owner=request.user)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            schedule_form = VenueScheduleForm(data)
            is_flutter = True 
        except json.JSONDecodeError:
            schedule_form = VenueScheduleForm(request.POST)
            is_flutter = False 

        if schedule_form.is_valid():
            cd = schedule_form.cleaned_data
            schedule_date = cd['date']
            start_time = cd['start_time']
            end_time_global_str = cd.get('end_time_global')
            is_available = cd.get('is_available', True)

            try:
                start_dt = datetime.combine(schedule_date, start_time)
                end_dt_time = datetime.strptime(end_time_global_str, '%H:%M').time()
                end_dt = datetime.combine(schedule_date, end_dt_time)
            except (ValueError, TypeError):
                msg = "Format jam/tanggal salah."
                return JsonResponse({"success": False, "message": msg}, status=400) if is_flutter else render(request, 'main/venue_manage_schedule.html', {'error': msg, 'venue': venue, 'schedule_form': schedule_form})

            if end_dt <= start_dt:
                msg = "Waktu selesai harus setelah mulai."
                return JsonResponse({"success": False, "message": msg}, status=400) if is_flutter else render(request, 'main/venue_manage_schedule.html', {'error': msg, 'venue': venue, 'schedule_form': schedule_form})

            created = 0
            new_slots_data = []
            current = start_dt
            while current < end_dt:
                slot_start = current.time()
                next_dt = current + timedelta(hours=1)
                
                if next_dt > end_dt: 
                    next_dt = end_dt
                
                slot_end = next_dt.time()

                exists = VenueSchedule.objects.filter(venue=venue, date=schedule_date, start_time=slot_start).exists()
                if not exists:
                    new_sch = VenueSchedule.objects.create(
                        venue=venue, 
                        date=schedule_date, 
                        start_time=slot_start, 
                        end_time=slot_end, 
                        is_available=is_available
                    )
                    created += 1
                    
                    new_slots_data.append({
                        'id': new_sch.id,
                        'date_str_iso': new_sch.date.strftime('%Y-%m-%d'),
                        'date_str_display': date_format(new_sch.date, "l, d M Y"), 
                        'start_time': new_sch.start_time.strftime('%H:%M'),
                        'end_time': new_sch.end_time.strftime('%H:%M'),
                        'is_booked': False,
                        'is_available': True,
                    })

                
                current = next_dt
            

            if is_flutter:
                return JsonResponse({
                    "success": True, 
                    "message": f"{created} slot berhasil dibuat.",
                    "new_slots": new_slots_data
                })
            else:

                return JsonResponse({
                    "success": True, 
                    "message": f"{created} slot berhasil dibuat.",
                    "new_slots": new_slots_data
                })

        else:

            if is_flutter:
                return JsonResponse({"success": False, "message": "Data tidak valid", "errors": schedule_form.errors}, status=400)
            else:

                return render(request, 'main/venue_manage_schedule.html', {
                    'venue': venue, 'schedule_form': schedule_form, 
                    'schedules': venue.schedules.all().order_by('date', 'start_time')
                })


    

    if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
        schedules = venue.schedules.all().order_by('date', 'start_time')
        data = []
        for s in schedules:
            data.append({
                'id': s.id,
                'date': s.date.strftime('%Y-%m-%d'),

                'date_display': date_format(s.date, "l, d M Y"), 
                'start_time': s.start_time.strftime('%H:%M'),
                'end_time': s.end_time.strftime('%H:%M'),
                'is_booked': s.is_booked,
                'is_available': s.is_available,
            })
        return JsonResponse(data, safe=False)


    schedule_form = VenueScheduleForm()
    schedules = venue.schedules.all().order_by('date', 'start_time')
    context = {
        'venue': venue,
        'schedule_form': schedule_form,
        'schedules': schedules,
    }
    return render(request, 'main/venue_manage_schedule.html', context)

@csrf_exempt
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_venue_owner, login_url='home')
def venue_schedule_delete(request, venue_id):

    if request.method != 'DELETE' and request.method != 'POST':
        return JsonResponse({"success": False, "message": "Metode tidak diizinkan."}, status=405)

    venue = get_object_or_404(Venue, id=venue_id)

    if venue.owner != request.user:
        return JsonResponse({"success": False, "message": "Anda tidak memiliki izin."}, status=403)

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
         return JsonResponse({"success": True, "message": "Tidak ada jadwal yang dapat dihapus."})

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
        profile_picture_url = coach.profile_picture if coach.profile_picture else None
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

    form = CoachProfileForm(request.POST, instance=coach_profile)
    
    if form.is_valid():
        profile = form.save()
        
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
                'profile_picture': profile.profile_picture if profile.profile_picture else None,
            }
        }
        return JsonResponse(response_data)
    else:
        errors = {}
        for field, error_list in form.errors.items():
            errors[field] = [str(error) for error in error_list]
        
        return JsonResponse({
            'success': False,
            'message': 'Terjadi kesalahan validasi',
            'errors': errors
        }, status=400)

@csrf_exempt
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
@require_http_methods(["DELETE", "POST"]) 
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

@csrf_exempt 
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_schedule(request):
    """Handles displaying and AJAX/JSON creation of coach schedules."""


    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:

        if request.method == 'POST':
            return JsonResponse({"success": False, "message": "Profil pelatih tidak ditemukan. Lengkapi profil dulu."}, status=400)
        coach_profile = None


    if request.method == 'POST':
        if not coach_profile:
             return JsonResponse({"success": False, "message": "Profil pelatih tidak ditemukan."}, status=400)


        try:
            data = json.loads(request.body)
            form = CoachScheduleForm(data)
            is_flutter = True
        except json.JSONDecodeError:
            form = CoachScheduleForm(request.POST)
            is_flutter = False


        if form.is_valid():

            end_time_global_str = form.cleaned_data.get('end_time_global')
            schedule_date = form.cleaned_data['date']
            start_time_slot = form.cleaned_data['start_time']
            

            try:
                start_dt = datetime.combine(schedule_date, start_time_slot)
                end_dt_time = datetime.strptime(end_time_global_str, '%H:%M').time()
                end_dt = datetime.combine(schedule_date, end_dt_time)
            except (ValueError, TypeError):
                msg = "Format jam atau tanggal tidak valid."
                return JsonResponse({"success": False, "message": msg}, status=400) if is_flutter else render(request, 'main/coach_schedule.html', {'form': form, 'error': msg})

            if end_dt <= start_dt:
                msg = "Waktu selesai harus setelah waktu mulai."
                return JsonResponse({"success": False, "message": msg}, status=400) if is_flutter else render(request, 'main/coach_schedule.html', {'form': form, 'error': msg})


            created = 0
            new_slots_data = []
            current = start_dt

            while current < end_dt:
                slot_start = current.time()
                next_dt = current + timedelta(hours=1)
                
                if next_dt > end_dt:
                    next_dt = end_dt 
                
                slot_end = next_dt.time()

                exists = CoachSchedule.objects.filter(
                    coach=coach_profile, date=schedule_date, start_time=slot_start
                ).exists()

                if not exists:
                    new_schedule = CoachSchedule.objects.create(
                        coach=coach_profile,
                        date=schedule_date,
                        start_time=slot_start,
                        end_time=slot_end,
                        is_available=True 
                    )
                    created += 1
                    
                    new_slots_data.append({
                        'id': new_schedule.id,
                        'date_str_iso': new_schedule.date.strftime('%Y-%m-%d'),
                        'date_str_display': date_format(new_schedule.date, "l, d M Y"), 
                        'start_time': new_schedule.start_time.strftime('%H:%M'),
                        'end_time': new_schedule.end_time.strftime('%H:%M'),
                        'is_booked': False,
                        'is_available': True,
                    })

                
                current = next_dt


            if is_flutter:
                return JsonResponse({
                    "success": True,
                    "message": f"{created} slot jadwal berhasil ditambahkan.",
                    "new_slots": new_slots_data
                }, status=200)
            else:

                return JsonResponse({
                    "success": True,
                    "message": f"{created} slot jadwal berhasil ditambahkan.",
                    "new_slots": new_slots_data
                }, status=200)

        else:

            if is_flutter:
                return JsonResponse({"success": False, "message": "Data form tidak valid.", "errors": form.errors}, status=400)
            else:

                schedules = coach_profile.schedules.all().order_by('date', 'start_time') if coach_profile else []
                return render(request, 'main/coach_schedule.html', {'form': form, 'schedules': schedules, 'coach_profile': coach_profile})


    schedules_qs = coach_profile.schedules.all().order_by('date', 'start_time') if coach_profile else []


    if request.GET.get('format') == 'json' or request.headers.get('Accept') == 'application/json':
        data = []
        for s in schedules_qs:
            data.append({
                'id': s.id,
                'date': s.date.strftime('%Y-%m-%d'),
                'start_time': s.start_time.strftime('%H:%M'),
                'end_time': s.end_time.strftime('%H:%M'),
                'is_booked': s.is_booked,
                'is_available': s.is_available,
            })
        return JsonResponse(data, safe=False)


    form = CoachScheduleForm()
    user_has_profile = coach_profile is not None
    
    context = {
        'coach_profile': coach_profile,
        'schedules': schedules_qs,
        'form': form,
        'has_profile': user_has_profile
    }
    return render(request, 'main/coach_schedule.html', context)

@csrf_exempt
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def coach_schedule_delete(request):

    if request.method != 'DELETE' and request.method != 'POST':
        return JsonResponse({"message": "Metode tidak diizinkan."}, status=405)

    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
    except CoachProfile.DoesNotExist:
        return JsonResponse({"message": "Profil pelatih tidak ditemukan."}, status=400)


    try:
        data = json.loads(request.body)
        ids = data.get('selected_schedules', [])
    except json.JSONDecodeError:
        return JsonResponse({"message": "Format data JSON tidak valid."}, status=400)

    if not ids:
        return JsonResponse({"success": False, "message": "Tidak ada jadwal yang dipilih."}, status=400)

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
        message += f" ({warning_count} slot gagal dihapus karena sudah dibooking)."

    return JsonResponse({"success": True, "message": message}, status=200)

def coach_list_view(request):
    """Menampilkan daftar semua coach dengan pagination"""
    coaches_list = CoachProfile.objects.all().select_related(
        'user', 'main_sport_trained'
    ).prefetch_related('service_areas').order_by('user__first_name')
    

    query = request.GET.get('q')
    if query:
        coaches_list = coaches_list.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )
    

    sport_filter = request.GET.get('sport')
    if sport_filter:
        coaches_list = coaches_list.filter(main_sport_trained__id=sport_filter)
    

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
    return render(request, 'main/coach_detail.html', context)

def filter_coaches_ajax(request):
    """
    View AJAX untuk memfilter dan paginasi daftar coach.
    Hanya mengembalikan potongan HTML dari daftar coach.
    """
    coaches_list = CoachProfile.objects.all().select_related(
        'user', 'main_sport_trained'
    ).prefetch_related('service_areas').order_by('user__first_name')
    

    query = request.GET.get('q')
    sport_filter = request.GET.get('sport')
    area_filter = request.GET.get('area')
    

    if query:
        coaches_list = coaches_list.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )
    

    if sport_filter:
        coaches_list = coaches_list.filter(main_sport_trained__id=sport_filter)
    
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
    
    context = {
        'coaches': coaches,
        'query': query,
        'sport_filter': sport_filter,
        'area_filter': area_filter,
    }
    

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
    
    total_users = User.objects.count()
    total_venues = Venue.objects.count()
    total_coaches = CoachProfile.objects.count()
    total_bookings = Booking.objects.count()

    context = {
        'total_users': total_users,
        'total_venues': total_venues,
        'total_coaches': total_coaches,
        'total_bookings': total_bookings,
    }
    
    return render(request, 'main/admin_dashboard.html', context)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def create_booking(request, venue_id):
    venue = get_object_or_404(Venue, id=venue_id)
    
    if request.method == 'GET' and request.headers.get('Accept') == 'application/json':
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

        schedules_data = [
            {
                'id': s.id,
                'date': s.date.isoformat(),
                'date_display': s.date.strftime('%A, %d %B %Y'),
                'start_time': s.start_time.strftime('%H:%M'),
                'end_time': s.end_time.strftime('%H:%M'),
            }
            for s in schedules
        ]

        equipments_data = [
            {
                'id': e.id,
                'name': e.name,
                'rental_price': float(e.rental_price or 0),
                'stock_quantity': e.stock_quantity,
            }
            for e in equipment_list
        ]

        return JsonResponse({
            'success': True,
            'venue': {
                'id': venue.id,
                'name': venue.name,
                'description': venue.description or '',
                'price_per_hour': float(venue.price_per_hour or 0),
                'location': venue.location.name if venue.location else None,
                'sport_category': venue.sport_category.name if venue.sport_category else None,
                'image_url': request.build_absolute_uri(venue.image.url) if venue.image else None,
            },
            'schedules': schedules_data,
            'equipments': equipments_data,
        })

    if request.method == 'POST':
        is_json = request.headers.get('Content-Type') == 'application/json'
        
        if is_json:
            try:
                data = json.loads(request.body)
                schedule_id = data.get('schedule_id')
                equipment_ids = data.get('equipment', [])
                coach_id = data.get('coach_id')
                payment_method = data.get('payment_method', 'CASH')
                quantities = data.get('quantities', {})  
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
        else:
            schedule_id = request.POST.get('schedule_id')
            equipment_ids = request.POST.getlist('equipment')
            coach_id = request.POST.get('coach')
            payment_method = request.POST.get('payment_method', 'CASH')
            quantities = {}

            if schedule_id and isinstance(schedule_id, str):
                schedule_id = schedule_id.replace('.', '')
            
            if coach_id and isinstance(coach_id, str):
                coach_id = coach_id.replace('.', '')
                if coach_id == '': coach_id = None 

            if equipment_ids:
                cleaned_ids = []
                for eid in equipment_ids:
                    if isinstance(eid, str):
                        cleaned_ids.append(eid.replace('.', ''))
                    else:
                        cleaned_ids.append(eid)
                equipment_ids = cleaned_ids

        if not schedule_id:
            error_msg = "Anda harus memilih jadwal terlebih dahulu!"
            if is_json:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('create_booking', venue_id=venue.id)

        try:
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            utc_now = timezone.now()
            now_in_jakarta = utc_now.astimezone(jakarta_tz)
            today = now_in_jakarta.date()
            current_time = now_in_jakarta.time()

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
                    error_msg = f"Jadwal tidak tersedia atau sudah dibooking."
                    if is_json:
                        return JsonResponse({'success': False, 'message': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('create_booking', venue_id=venue.id)

                total_price = venue.price_per_hour or 0
                selected_equipment_data = []
                equipment_revenue = 0


                if equipment_ids:
                    equipment_queryset = Equipment.objects.filter(id__in=equipment_ids, venue=venue)
                    for eq in equipment_queryset:
                        if is_json:
                            quantity = quantities.get(str(eq.id), 1)
                        else:
 
                            q_val = request.POST.get(f'quantity_{eq.id}')
                            
 
                            if not q_val:
                                from django.utils.numberformat import format
                                id_with_dot = format(eq.id, '.', grouping=3, thousand_sep='.', force_grouping=True)
                                q_val = request.POST.get(f'quantity_{id_with_dot}')
                            
 
                            quantity_str = q_val if q_val else '1'
                            
                            try:
                                quantity = int(quantity_str)
                                if quantity <= 0: quantity = 1
                            except (ValueError, TypeError):
                                quantity = 1

                        if quantity > eq.stock_quantity:
                            error_msg = f"Stock untuk {eq.name} tidak mencukupi (tersisa {eq.stock_quantity})."
                            if is_json:
                                return JsonResponse({'success': False, 'message': error_msg}, status=400)
                            messages.error(request, error_msg)
                            raise IntegrityError(error_msg)

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
                    except (CoachProfile.DoesNotExist, CoachSchedule.DoesNotExist) as e:
                        error_msg = "Coach tidak tersedia pada jadwal yang dipilih."
                        if is_json:
                            return JsonResponse({'success': False, 'message': error_msg}, status=400)
 
                        messages.error(request, error_msg)
                        return redirect('create_booking', venue_id=venue.id)

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

                if is_json:
                    return JsonResponse({
                        'success': True,
                        'message': 'Booking berhasil dibuat!',
                        'booking': {
                            'id': booking.id,
                            'total_price': float(booking.total_price),
                            'payment_method': payment_method,
                        }
                    })

                if payment_method.upper() == 'CASH':
                    return redirect('my_bookings')
                else:
                    return redirect('my_bookings')

        except IntegrityError as e:
            if is_json:
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, str(e))
            return redirect('create_booking', venue_id=venue.id)
        except Exception as e:
            if is_json:
                return JsonResponse({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'}, status=500)
            messages.error(request, f'Terjadi kesalahan: {str(e)}')
            return redirect('create_booking', venue_id=venue.id)

 
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

    context = {
        'venue': venue,
        'schedules': schedules,
        'equipment_list': equipment_list,
        'coaches': [],
    }
    return render(request, 'main/create_booking.html', context)

@csrf_exempt
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def customer_payment(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, customer=request.user)
    transaction = booking.transaction
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    is_json = 'application/json' in request.headers.get('Content-Type', '') or \
              'application/json' in request.headers.get('Accept', '')

    should_confirm = request.method == 'POST' or (transaction.payment_method == 'CASH')

    if should_confirm:
        is_cash_auto_confirm = transaction.payment_method == 'CASH' and request.method != 'POST'

        try:
            with db_transaction.atomic():
                venue_schedule = VenueSchedule.objects.select_for_update().get(id=booking.venue_schedule.id)
                
                if Booking.objects.filter(venue_schedule=venue_schedule, transaction__status='CONFIRMED').exclude(id=booking.id).exists():
                    transaction.status = 'CANCELLED'
                    transaction.save()
                    raise IntegrityError("Maaf, jadwal ini baru saja dikonfirmasi oleh pengguna lain.")

                booking_equipments = BookingEquipment.objects.filter(booking=booking).select_related('equipment')
                for be in booking_equipments:
                    equipment = Equipment.objects.select_for_update().get(id=be.equipment.id)
                    if equipment.stock_quantity < be.quantity:
                        raise IntegrityError(f"Maaf, stok {equipment.name} tidak mencukupi. Tersedia: {equipment.stock_quantity}, Dibutuhkan: {be.quantity}")
                    
                    equipment.stock_quantity -= be.quantity
                    equipment.save()

                venue_schedule.is_booked = True
                venue_schedule.save()
                
                if booking.coach_schedule:
                    booking.coach_schedule.is_booked = True
                    booking.coach_schedule.save()

                transaction.status = 'CONFIRMED'
                transaction.save()

            if is_json or (is_ajax and not is_cash_auto_confirm):
                return JsonResponse({'success': True, 'message': 'Pembayaran berhasil dikonfirmasi!'})

            if is_cash_auto_confirm:
                messages.success(request, 'Booking Berhasil Dikonfirmasi!')
                return redirect('my_bookings')

        except IntegrityError as e:
            if is_json or is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, str(e))

    return render(request, 'main/customer_payment.html', {'booking': booking, 'transaction': transaction})

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def booking_history(request):
    bookings = Booking.objects.filter(
        customer=request.user
    ).select_related(
        'venue_schedule__venue__location',
        'coach_schedule__coach__user__profile',
        'transaction'
    ).prefetch_related(
        'equipment_details__equipment'
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

    is_ajax_json = request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.headers.get('Accept') == 'application/json'
    
    if is_ajax_json:
        bookings_data = []
        
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
        
        for booking in bookings:
            equipment_list = []
            for eq_detail in booking.equipment_details.all():
                equipment_list.append({
                    'id': eq_detail.equipment.id,
                    'name': eq_detail.equipment.name,
                    'quantity': eq_detail.quantity,
                    'price': str(eq_detail.equipment.rental_price)
                })

            booking_data = {
                'id': booking.id,
                'venue': {
                    'id': booking.venue_schedule.venue.id,
                    'name': booking.venue_schedule.venue.name,
                    'location': booking.venue_schedule.venue.location.name if booking.venue_schedule.venue.location else None
                },
                'schedule': {
                    'date': booking.venue_schedule.date.strftime('%Y-%m-%d'),
                    'date_display': booking.venue_schedule.date.strftime('%A, %d %B %Y'),
                    'start_time': booking.venue_schedule.start_time.strftime('%H:%M'),
                    'end_time': booking.venue_schedule.end_time.strftime('%H:%M')
                },
                'coach': None,
                'equipment': equipment_list,
                'total_price': str(booking.total_price),
                'transaction': {
                    'payment_method': booking.transaction.payment_method,
                    'status': booking.transaction.status,
                    'status_display': booking.transaction.get_status_display()
                },
                'venue_review': None,
                'coach_review': None,
                'booking_time': booking.booking_time.isoformat() if hasattr(booking, 'booking_time') else None
            }

            if booking.coach_schedule:
                booking_data['coach'] = {
                    'id': booking.coach_schedule.coach.id,
                    'name': booking.coach_schedule.coach.user.get_full_name() or booking.coach_schedule.coach.user.username,
                    'phone_number': booking.coach_schedule.coach.user.profile.phone_number if hasattr(booking.coach_schedule.coach.user, 'profile') else None
                }

            v_id = booking.venue_schedule.venue_id
            c_id = booking.coach_schedule.coach_id if booking.coach_schedule else None
            
            if v_id and v_id in venue_review_map:
                review = venue_review_map[v_id]
                booking_data['venue_review'] = {
                    'id': review.id,
                    'rating': review.rating,
                    'comment': review.comment,
                    'created_at': review.created_at.isoformat()
                }
            
            if c_id and c_id in coach_review_map:
                review = coach_review_map[c_id]
                booking_data['coach_review'] = {
                    'id': review.id,
                    'rating': review.rating,
                    'comment': review.comment,
                    'created_at': review.created_at.isoformat()
                }

            bookings_data.append(booking_data)

        return JsonResponse({
            'success': True,
            'bookings': bookings_data,
            'total': len(bookings_data)
        })
    
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
    user = request.user
    search_query = request.GET.get('q', '').strip()
    
    bookings = Booking.objects.filter(
        customer=user,
        transaction__status='PENDING'  
    ).select_related(
        'venue_schedule__venue__sport_category',
        'venue_schedule__venue__location',
        'coach_schedule__coach__user',
        'transaction'
    ).prefetch_related(
        'equipment_details__equipment'
    ).order_by('-booking_time')
    
    if search_query:
        bookings = bookings.filter(
            Q(venue_schedule__venue__name__icontains=search_query) |
            Q(id__icontains=search_query)
        )
    
    is_ajax_json = request.headers.get('X-Requested-With') == 'XMLHttpRequest' and request.headers.get('Accept') == 'application/json'
    
    if is_ajax_json:
        bookings_data = []
        for booking in bookings:
            venue = booking.venue_schedule.venue
            coach = booking.coach_schedule.coach if booking.coach_schedule else None
            transaction = booking.transaction
            
            equipments = []
            for be in booking.equipment_details.all():
                equipments.append({
                    'id': be.equipment.id,
                    'name': be.equipment.name,
                    'quantity': be.quantity,
                    'rental_price': float(be.equipment.rental_price or 0),
                    'sub_total': float(be.sub_total or 0)
                })
            
            booking_data = {
                'id': booking.id,
                'venue': {
                    'id': venue.id,
                    'name': venue.name,
                    'description': venue.description or '',
                    'sport_category': venue.sport_category.name if venue.sport_category else None,
                    'location': venue.location.name if venue.location else None,
                    'price_per_hour': float(venue.price_per_hour or 0),
                    'image_url': venue.main_image if venue.main_image else None,
                },
                'schedule': {
                    'id': booking.venue_schedule.id,
                    'date': booking.venue_schedule.date.isoformat(),
                    'date_display': booking.venue_schedule.date.strftime('%A, %d %B %Y'),
                    'start_time': booking.venue_schedule.start_time.strftime('%H:%M'),
                    'end_time': booking.venue_schedule.end_time.strftime('%H:%M'),
                },
                'coach': {
                    'id': coach.id,
                    'name': coach.user.get_full_name() or coach.user.username,
                    'rate_per_hour': float(coach.rate_per_hour or 0),
                    'specialization': coach.main_sport_trained.name if coach.main_sport_trained else ''
                } if coach else None,
                'equipments': equipments,
                'transaction': {
                    'id': transaction.id,
                    'status': transaction.status,
                    'status_display': transaction.get_status_display(),
                    'payment_method': transaction.payment_method,
                    'revenue_venue': float(transaction.revenue_venue or 0),
                    'revenue_coach': float(transaction.revenue_coach or 0),
                    'transaction_time': transaction.transaction_time.isoformat(),  
                } if transaction else None,
                'total_price': float(booking.total_price or 0),
                'booking_time': booking.booking_time.isoformat(),
                'can_edit': True,  
                'can_cancel': True,  
            }
            bookings_data.append(booking_data)
        
        return JsonResponse({
            'success': True,
            'count': len(bookings_data),
            'bookings': bookings_data
        })
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        html = render_to_string('main/_my_booking_list.html', {
            'bookings': bookings
        }, request=request)
        return JsonResponse({
            'success': True,
            'html': html
        })
    
    context = {
        'bookings': bookings,
    }
    return render(request, 'main/my_bookings.html', context)

@csrf_exempt
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def delete_booking(request, booking_id):
    if request.method not in ['DELETE', 'POST']:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Metode tidak diizinkan.'}, status=405)
        messages.error(request, "Metode tidak valid.")
        return redirect('my_bookings')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or \
              'application/json' in request.headers.get('Accept', '')
    
    try:
        with db_transaction.atomic():
            booking = get_object_or_404(
                Booking.objects.select_related('transaction', 'venue_schedule', 'coach_schedule'), 
                id=booking_id, 
                customer=request.user
            )

            if hasattr(booking, 'transaction') and booking.transaction.status == 'PENDING':
                
                if booking.venue_schedule:
                    booking.venue_schedule.is_booked = False
                    booking.venue_schedule.is_available = True
                    booking.venue_schedule.save()
                
                if booking.coach_schedule:
                    booking.coach_schedule.is_booked = False
                    booking.coach_schedule.is_available = True
                    booking.coach_schedule.save()
                
                booking_equipments = BookingEquipment.objects.filter(booking=booking)
                for item in booking_equipments:
                    item.equipment.stock_quantity += item.quantity
                    item.equipment.save()
                booking.transaction.delete()
                booking.delete()
                
                success_msg = 'Booking berhasil dibatalkan'
                if is_ajax:
                    return JsonResponse({'success': True, 'message': success_msg})
                
                messages.success(request, success_msg)
                return redirect('my_bookings')
            
            else:
                error_msg = 'Booking tidak dapat dibatalkan (sudah dibayar atau dalam proses).'
                if is_ajax:
                    return JsonResponse({'success': False, 'message': error_msg}, status=400)
                
                messages.error(request, error_msg)
                return redirect('my_bookings')

    except Exception as e:
        error_msg = f'Gagal membatalkan booking: {str(e)}'
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_msg}, status=500)
        
        messages.error(request, error_msg)
        return redirect('my_bookings')

@csrf_exempt
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_customer, login_url='home')
def update_booking(request, booking_id):
    if request.method not in ['PUT', 'POST']:   
        return JsonResponse({
            'success': False, 
            'message': 'Metode tidak diizinkan.'
        }, status=405)
    
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    try:
        import json
        data = json.loads(request.body)
        
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
        
        new_schedule_id = data.get('schedule_id')
        new_coach_id = data.get('coach_id')  
        equipment_ids = data.get('equipment', [])  
        new_payment_method = data.get('payment_method', 'CASH')
        
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
                
                target_schedule = VenueSchedule.objects.get(schedule_query)
                
                if target_schedule.date == today and target_schedule.start_time < current_time:
                    raise VenueSchedule.DoesNotExist("Jadwal yang dipilih sudah lewat.")

                new_schedule = VenueSchedule.objects.select_for_update().get(id=target_schedule.id)

                if new_schedule.is_booked:
                    try:
                        existing_booking = new_schedule.booking
                        if existing_booking != booking:
                            raise IntegrityError("Jadwal ini baru saja dibooking oleh orang lain.")
                    except Booking.DoesNotExist:
                        pass

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
                    
                    if new_coach_schedule_obj.is_booked:
                        try:
                            existing_booking = new_coach_schedule_obj.booking
                            if existing_booking != booking:
                                raise IntegrityError("Jadwal coach ini baru saja dibooking oleh orang lain.")
                        except Booking.DoesNotExist:
                            pass

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
                    quantity = data.get(f'quantity_{eq.id}', 1)
                    try:
                        quantity = int(quantity)
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
            'coach_schedule__coach__user',
            'transaction'
        ).prefetch_related(
            'equipment_details__equipment' 
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
        'date': current_schedule.date.isoformat(),
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
            'date': s.date.isoformat(),
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
            'rate': float(coach.rate_per_hour or 0),
            'specialization': coach.main_sport_trained.name if coach.main_sport_trained else ''
        }

    selected_equipment_map = {
        item['equipment_id']: item['quantity']
        for item in booking.equipment_details.values('equipment_id', 'quantity')   
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
        'current_payment_method': current_payment_method,
    })

def filter_venues_ajax(request):
    """AJAX endpoint untuk filter venues dengan pagination"""
    search = request.GET.get('search', '').strip()
    location_id = request.GET.get('location', '')
    sport_id = request.GET.get('sport', '')
    page = request.GET.get('page', 1)
    
    venues = Venue.objects.all().select_related('location', 'sport_category', 'owner')
    
  
    if search:
        venues = venues.filter(
            Q(name__icontains=search) | 
            Q(description__icontains=search)
        )
    
    if location_id:
        venues = venues.filter(location_id=location_id)
    
    if sport_id:
        venues = venues.filter(sport_category_id=sport_id)
    
 
    paginator = Paginator(venues, 6)
    try:
        venues_page = paginator.page(page)
    except PageNotAnInteger:
        venues_page = paginator.page(1)
    except EmptyPage:
        venues_page = paginator.page(paginator.num_pages)
    
  
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
            'image': venue.main_image if venue.main_image else None,
            'rating': round(avg_rating, 1),
        })
    
  
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
        return JsonResponse({"success": False, "message": "Feedback hanya untuk booking berstatus CONFIRMED."}, status=400)
    return True


@csrf_exempt
def upsert_review(request, booking_id):
    """Create/edit review berdasarkan target. ?target=venue|coach"""
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Anda harus login terlebih dahulu."}, status=401)
    
    target = request.GET.get("target")
    booking = get_object_or_404(
        Booking.objects.select_related(
            "venue_schedule__venue", "coach_schedule__coach__user", "transaction"
        ),
        pk=booking_id,
        customer=request.user
    )

    guard = _guard_confirmed_owner(request, booking)
    if isinstance(guard, JsonResponse):
        return guard

    instance = None
    if target == "venue":
        venue = getattr(getattr(booking, "venue_schedule", None), "venue", None)
        if not venue:
            msg = "Booking ini tidak memiliki venue yang valid."
            return JsonResponse({"success": False, "message": msg}, status=400)

        instance = Review.objects.filter(customer=request.user, target_venue=venue).order_by("-created_at").first()
        title = "Edit Review Venue" if instance else "Beri Review Venue"
        target_ctx = {"target": "venue", "target_name": venue.name}

    elif target == "coach":
        coach = getattr(getattr(booking, "coach_schedule", None), "coach", None)
        if not coach:
            msg = "Booking ini tidak memiliki pelatih."
            return JsonResponse({"success": False, "message": msg}, status=400)

        instance = Review.objects.filter(customer=request.user, target_coach=coach).order_by("-created_at").first()
        title = "Edit Review Coach" if instance else "Beri Review Coach"
        target_ctx = {"target": "coach", "target_name": getattr(coach, "user", coach).__str__()}

    else:
        return JsonResponse({"success": False, "message": "Target tidak valid."}, status=400)

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
            return JsonResponse({"success": True, "message": msg})

        err = next(iter(form.errors.values()))[0] if form.errors else "Form tidak valid."
        return JsonResponse({"success": False, "message": err}, status=400)

    form = ReviewForm(instance=instance)

    return render(request, "main/review_form.html", {
        "title": title,
        "form": form,
        "booking": booking,
        **target_ctx,
        "existing": instance is not None,
        "existing_id": getattr(instance, "id", None),
    })

@csrf_exempt
@require_http_methods(['POST'])
def delete_review(request, review_id):
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Anda harus login terlebih dahulu."}, status=401)
    
    try:
        review = Review.objects.get(pk=review_id, customer=request.user)
    except Review.DoesNotExist:
        return JsonResponse({"success": False, "message": "Review tidak ditemukan."}, status=404)
    
    review.delete()
    return JsonResponse({"success": True, "message": "Feedback berhasil dihapus."})

@csrf_exempt
def get_booking_reviews(request, booking_id):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Anda harus login terlebih dahulu."},
            status=401
        )
    
    try:
        booking = Booking.objects.select_related(
            'venue_schedule__venue',
            'coach_schedule__coach__user',
            'customer'
        ).get(pk=booking_id)
    except Booking.DoesNotExist:
        return JsonResponse(
            {"error": "Booking tidak ditemukan."},
            status=404
        )
    
    if booking.customer != request.user:
        return JsonResponse(
            {"error": "Anda tidak memiliki izin untuk melihat reviews booking ini."},
            status=403
        )
    
    reviews_data = []
    
    if booking.venue_schedule and booking.venue_schedule.venue:
        venue = booking.venue_schedule.venue
        venue_review = Review.objects.filter(
            customer=request.user,
            target_venue=venue
        ).first()
        
        if venue_review:
            reviews_data.append({
                "pk": venue_review.id,
                "fields": {
                    "rating": venue_review.rating,
                    "comment": venue_review.comment,
                    "target_type": "venue",
                    "target_name": venue.name,
                    "created_at": venue_review.created_at.isoformat() if venue_review.created_at else None,
                }
            })
    
    if booking.coach_schedule and booking.coach_schedule.coach:
        coach = booking.coach_schedule.coach
        coach_review = Review.objects.filter(
            customer=request.user,
            target_coach=coach
        ).first()
        
        if coach_review:
            reviews_data.append({
                "pk": coach_review.id,
                "fields": {
                    "rating": coach_review.rating,
                    "comment": coach_review.comment,
                    "target_type": "coach",
                    "target_name": coach.user.get_full_name() or coach.user.username,
                    "created_at": coach_review.created_at.isoformat() if coach_review.created_at else None,
                }
            })
    
    return JsonResponse(reviews_data, safe=False)

 

@login_required(login_url='login')
@user_passes_test(is_admin, login_url='home')
def admin_user_management_view(request):
    """Menampilkan halaman manajemen semua pengguna dengan pagination."""
    user_list = User.objects.select_related('profile').order_by('-date_joined')
    
    paginator = Paginator(user_list, 20)  
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
    
    paginator = Paginator(venue_list, 20)  
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
    
    paginator = Paginator(booking_list, 20)  
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
@require_http_methods(["POST"])  
def admin_toggle_coach_verification_view(request, coach_id):
    """
    Meng-toggle status is_verified seorang Coach via AJAX.
    """
    try:
 
        coach = get_object_or_404(CoachProfile, id=coach_id)

 
        coach.is_verified = not coach.is_verified
        coach.save()

 
        return JsonResponse({
            'success': True,
            'is_verified': coach.is_verified,  
            'message': 'Status coach berhasil diperbarui.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

def show_json(request):
    if request.user.is_authenticated:
        booking_list = Booking.objects.filter(customer=request.user).select_related(
            'venue_schedule__venue', 
            'coach_schedule__coach__user'
        )
    else:
        booking_list = Booking.objects.none()
    
    data = []
    for booking in booking_list:
        item = {
            "model": "main.booking",
            "pk": booking.pk,
            "fields": {
                "venue_schedule": booking.venue_schedule.id, 
                "coach_schedule": booking.coach_schedule.id if booking.coach_schedule else None,
                "customer": booking.customer.id, 

                "customer_name": booking.customer.get_full_name() or booking.customer.username,
                "venue_name": booking.venue_schedule.venue.name,
                "date": booking.venue_schedule.date.strftime("%Y-%m-%d"),
                "start_time": booking.venue_schedule.start_time.strftime("%H:%M"),
                "end_time": booking.venue_schedule.end_time.strftime("%H:%M"),
                "coach_name": booking.coach_schedule.coach.user.get_full_name() if booking.coach_schedule else "-",
                
                "total_price": str(booking.total_price),
                "booking_time": booking.booking_time.isoformat() if hasattr(booking, 'booking_time') else None
            }
        }
        data.append(item)
    
    return JsonResponse(data, safe=False)

def show_my_bookings_json(request):
    if not request.user.is_authenticated:
        return JsonResponse([], safe=False)

    bookings = Booking.objects.filter(
        customer=request.user,
        transaction__status='PENDING'
    ).select_related(
        'venue_schedule__venue',
        'coach_schedule__coach__user',
        'transaction'
    ).prefetch_related('equipment_details__equipment')

    data = []
    for booking in bookings:
        equipments = []
        for be in booking.equipment_details.all():
            equipments.append({
                "name": be.equipment.name,
                "quantity": be.quantity
            })

        item = {
            "model": "main.booking",
            "pk": booking.pk,
            "fields": {
                "venue_schedule": booking.venue_schedule.id,
                "coach_schedule": booking.coach_schedule.id if booking.coach_schedule else None,
                "customer": booking.customer.id,
                "customer_name": booking.customer.get_full_name() or booking.customer.username,
                "venue_name": booking.venue_schedule.venue.name,
                "date": booking.venue_schedule.date.strftime("%Y-%m-%d"),
                "start_time": booking.venue_schedule.start_time.strftime("%H:%M"),
                "end_time": booking.venue_schedule.end_time.strftime("%H:%M"),
                "coach_name": (booking.coach_schedule.coach.user.get_full_name() or booking.coach_schedule.coach.user.username) if booking.coach_schedule else "-",
                "total_price": str(booking.total_price),
                "booking_time": booking.booking_time.isoformat() if booking.booking_time else None,
                "payment_method": booking.transaction.payment_method if booking.transaction else "CASH",
                "equipments": equipments,
            }
        }
        data.append(item)

    return JsonResponse(data, safe=False)

def show_booking_history_json(request):
    if not request.user.is_authenticated:
        return JsonResponse([], safe=False)
    
    bookings = Booking.objects.filter(
        customer=request.user,
        transaction__status='CONFIRMED'  
    ).select_related(
        'venue_schedule__venue',
        'coach_schedule__coach__user',
        'transaction'
    ).prefetch_related('equipment_details__equipment')

    data = []
    for booking in bookings:
        equipments = []
        for be in booking.equipment_details.all():
            equipments.append({
                "name": be.equipment.name,
                "quantity": be.quantity
            })

        item = {
            "model": "main.booking",
            "pk": booking.pk,
            "fields": {
                "venue_schedule": booking.venue_schedule.id,
                "coach_schedule": booking.coach_schedule.id if booking.coach_schedule else None,
                "customer": booking.customer.id,
                "customer_name": booking.customer.get_full_name() or booking.customer.username,
                "venue_name": booking.venue_schedule.venue.name,
                "date": booking.venue_schedule.date.strftime("%Y-%m-%d"),
                "start_time": booking.venue_schedule.start_time.strftime("%H:%M"),
                "end_time": booking.venue_schedule.end_time.strftime("%H:%M"),
                
                "coach_name": (booking.coach_schedule.coach.user.get_full_name() or booking.coach_schedule.coach.user.username) if booking.coach_schedule else "-",
                "total_price": str(booking.total_price),
                "booking_time": booking.booking_time.isoformat() if booking.booking_time else None,
                "payment_method": booking.transaction.payment_method if booking.transaction else "CASH",
                "equipments": equipments,
            }
        }
        data.append(item)

    return JsonResponse(data, safe=False)

@csrf_exempt
def api_create_booking(request, venue_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'})
    
    try:
        import json
        data = json.loads(request.body)
        
        venue = get_object_or_404(Venue, pk=venue_id)
        schedule_id = data.get('schedule_id')
        coach_schedule_id = data.get('coach_schedule_id')
        equipment_ids = data.get('equipment', [])
        quantities = data.get('quantities', {})
        payment_method = data.get('payment_method', 'CASH')
        
        schedule = get_object_or_404(VenueSchedule, pk=schedule_id, venue=venue)
        
        if schedule.is_booked:
            return JsonResponse({'success': False, 'message': 'Jadwal sudah dibooking'})
        
        total_price = venue.price_per_hour
        revenue_coach = 0
        
        coach_schedule = None
        if coach_schedule_id:
            coach_schedule = get_object_or_404(CoachSchedule, pk=coach_schedule_id)
            if coach_schedule.is_booked:
                return JsonResponse({'success': False, 'message': 'Coach sudah dibooking'})
            revenue_coach = coach_schedule.coach.rate_per_hour
            total_price += revenue_coach
        
        equipment_total = 0
        for eq_id in equipment_ids:
            eq = get_object_or_404(Equipment, pk=eq_id, venue=venue)
            qty = int(quantities.get(str(eq_id), 1))
            
            if eq.stock_quantity < qty:
                return JsonResponse({'success': False, 'message': f'Stok {eq.name} tidak mencukupi. Tersedia: {eq.stock_quantity}'})
            
            equipment_total += eq.rental_price * qty
        
        total_price += equipment_total
        
        booking = Booking.objects.create(
            customer=request.user,
            venue_schedule=schedule,
            coach_schedule=coach_schedule,
            total_price=total_price,
        )
        
        for eq_id in equipment_ids:
            eq = get_object_or_404(Equipment, pk=eq_id, venue=venue)
            qty = int(quantities.get(str(eq_id), 1))
            
            BookingEquipment.objects.create(
                booking=booking,
                equipment=eq,
                quantity=qty,
                sub_total=eq.rental_price * qty,
            )
        
        Transaction.objects.create(
            booking=booking,
            status='PENDING',
            payment_method=payment_method,
            revenue_venue=float(venue.price_per_hour) + float(equipment_total),
            revenue_coach=float(revenue_coach),
            revenue_platform=0,
        )
        
        schedule.is_booked = True
        schedule.is_available = False
        schedule.save()
        
        if coach_schedule:
            coach_schedule.is_booked = True
            coach_schedule.is_available = False
            coach_schedule.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Booking berhasil dibuat',
            'booking_id': booking.pk,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
    
@csrf_exempt
def api_filter_venues(request):
    search = request.GET.get('search', '').strip()
    location_name = request.GET.get('location', '') 
    sport_name = request.GET.get('sport_category', '') 
    page = request.GET.get('page', 1) 
    
    venues_query = Venue.objects.all().select_related('location', 'sport_category', 'owner').order_by('id')
    
    if search:
        venues_query = venues_query.filter(
            Q(name__icontains=search) |
            Q(location__name__icontains=search) |
            Q(sport_category__name__icontains=search)
        )
    
    if location_name:
        venues_query = venues_query.filter(location__name__icontains=location_name)
        
    if sport_name:
        venues_query = venues_query.filter(sport_category__name__icontains=sport_name)
    
    paginator = Paginator(venues_query, 6) 
    try:
        venues_page = paginator.page(page)
    except:
        return JsonResponse({'success': True, 'venues': [], 'total_pages': 1})

    venues_data = []
    for v in venues_page:
        avg_rating = Review.objects.filter(target_venue=v).aggregate(avg=Avg('rating'))['avg']
        
        venues_data.append({
            'id': v.pk,
            'name': v.name,
            'location': v.location.name if v.location else '',
            'sport_category': v.sport_category.name if v.sport_category else '',
            'price_per_hour': float(v.price_per_hour or 0),
            'image': v.main_image if v.main_image else '',
            'rating': float(avg_rating) if avg_rating else 5.0,  
        })
    
    return JsonResponse({
        'success': True,
        'venues': venues_data,
        'total_pages': paginator.num_pages, 
        'current_page': venues_page.number,
        'has_next': venues_page.has_next() 
    })

@csrf_exempt
def api_booking_form_data(request, venue_id):
    try:
        venue = Venue.objects.get(pk=venue_id)
    except Venue.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Venue tidak ditemukan'}, status=404)
    
    schedules = VenueSchedule.objects.filter(
        venue=venue,
        date__gte=timezone.now().date()
    ).order_by('date', 'start_time')
    
    schedules_data = []
    for s in schedules:
        schedules_data.append({
            'id': s.id,
            'date': s.date.strftime('%Y-%m-%d'),
            'date_display': s.date.strftime('%a, %d %b %Y'),
            'start_time': s.start_time.strftime('%H:%M'),
            'end_time': s.end_time.strftime('%H:%M'),
            'is_booked': s.is_booked, 
        })
    
    equipments = Equipment.objects.filter(venue=venue, stock_quantity__gt=0)
    equipments_data = []
    for eq in equipments:
        equipments_data.append({
            'id': eq.id,
            'name': eq.name,
            'rental_price': float(eq.rental_price or 0),
            'stock_quantity': eq.stock_quantity,
        })
    
    return JsonResponse({
        'success': True,
        'venue': {
            'id': venue.id,
            'name': venue.name,
            'sport_category': venue.sport_category.name if venue.sport_category else None,
            'location': venue.location.name if venue.location else None,
            'price_per_hour': float(venue.price_per_hour or 0),
            'description': venue.description,
            'image': venue.main_image if venue.main_image else None,
        },
        'schedules': schedules_data,
        'equipments': equipments_data,
    })

@csrf_exempt
def api_get_coaches_for_schedule(request, schedule_id):
    editing_booking_id = request.GET.get('editing_booking_id')

    try:
        venue_schedule = VenueSchedule.objects.select_related('venue', 'venue__sport_category', 'venue__location').get(pk=schedule_id)
        venue = venue_schedule.venue
    except VenueSchedule.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Schedule tidak ditemukan'}, status=404)
    
    coach_booked_filter = Q(is_booked=False)
    if editing_booking_id and editing_booking_id != 'null' and editing_booking_id != '':
        coach_booked_filter |= Q(booking__id=editing_booking_id)

    coach_schedules = CoachSchedule.objects.filter(
        coach_booked_filter, 
        date=venue_schedule.date,
        start_time__lte=venue_schedule.start_time,
        end_time__gte=venue_schedule.end_time,
        coach__main_sport_trained=venue.sport_category, 
        coach__service_areas=venue.location          
    ).select_related('coach', 'coach__user', 'coach__main_sport_trained').prefetch_related('coach__service_areas')
    
    coaches_data = []
    for cs in coach_schedules:
        coach = cs.coach
        service_areas = [area.name for area in coach.service_areas.all()] if coach.service_areas.exists() else []
        coaches_data.append({
            'id': coach.id,
            'coach_schedule_id': cs.id,
            'name': coach.user.get_full_name() or coach.user.username,
            'age': coach.age,
            'rate_per_hour': float(coach.rate_per_hour or 0),
            'sport': coach.main_sport_trained.name if coach.main_sport_trained else None,
            'experience_desc': coach.experience_desc,
            'profile_picture_url': coach.profile_picture if coach.profile_picture else None,
            'areas': service_areas,
        })
    
    return JsonResponse({
        'success': True,
        'coaches': coaches_data
    })

@csrf_exempt
def api_cancel_booking(request, booking_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    try:
        with db_transaction.atomic():
            booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
            
            if hasattr(booking, 'transaction') and booking.transaction.status == 'PENDING':
                
                if booking.venue_schedule:
                    booking.venue_schedule.is_booked = False
                    booking.venue_schedule.is_available = True
                    booking.venue_schedule.save()
                
                if booking.coach_schedule:
                    booking.coach_schedule.is_booked = False
                    booking.coach_schedule.is_available = True
                    booking.coach_schedule.save()
                
                booking_equipments = BookingEquipment.objects.filter(booking=booking)
                for item in booking_equipments:
                    item.equipment.stock_quantity += item.quantity
                    item.equipment.save()

                booking.transaction.delete()
                booking.delete()
                
                return JsonResponse({'success': True, 'message': 'Booking berhasil dibatalkan'})
            else:
                return JsonResponse({
                    'success': False, 
                    'message': 'Booking tidak dapat dibatalkan (sudah dibayar atau sudah tidak aktif)'
                })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@csrf_exempt
def api_update_booking(request, booking_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
        venue = booking.venue_schedule.venue 
        
        if hasattr(booking, 'transaction') and booking.transaction.status != 'PENDING':
            return JsonResponse({
                'success': False, 
                'message': 'Booking yang sudah dibayar tidak bisa diedit'
            })
        
        if 'schedule_id' in data and data['schedule_id']: 
            new_schedule_id = data['schedule_id']
            
            if int(new_schedule_id) == booking.venue_schedule.id:
                pass 
            else:
                new_schedule = get_object_or_404(VenueSchedule, pk=new_schedule_id)
                
                if new_schedule.is_booked:
                     return JsonResponse({'success': False, 'message': 'Maaf, jadwal tersebut baru saja dibooking orang lain.'})

                old_schedule = booking.venue_schedule
                old_schedule.is_booked = False
                old_schedule.is_available = True
                old_schedule.save()
                
                booking.venue_schedule = new_schedule
                new_schedule.is_booked = True
                new_schedule.is_available = False
                new_schedule.save()
        
        if 'coach_schedule_id' in data:
            new_coach_sched_id = data['coach_schedule_id']
            old_coach_sched = booking.coach_schedule
            
            if old_coach_sched and (not new_coach_sched_id or old_coach_sched.id != new_coach_sched_id):
                old_coach_sched.is_booked = False
                old_coach_sched.save()
            
            if new_coach_sched_id:
                new_coach_sched = get_object_or_404(CoachSchedule, pk=new_coach_sched_id)
                
                if new_coach_sched.is_booked and (not old_coach_sched or new_coach_sched.id != old_coach_sched.id):
                    return JsonResponse({'success': False, 'message': 'Coach tersebut sudah dibooking.'})
                
                booking.coach_schedule = new_coach_sched
                new_coach_sched.is_booked = True
                new_coach_sched.save()
            else:
                booking.coach_schedule = None

        if 'equipment' in data:
            old_equipments = BookingEquipment.objects.filter(booking=booking)
            old_equipments.delete()
            
            equipment_ids = data.get('equipment', [])
            quantities = data.get('quantities', {})
            
            for eq_id in equipment_ids:
                equipment = get_object_or_404(Equipment, pk=eq_id)
                qty = int(quantities.get(str(eq_id), 1))
                
                if equipment.stock_quantity < qty:
                    return JsonResponse({'success': False, 'message': f"Stok {equipment.name} tidak mencukupi."}, status=400)
                
                BookingEquipment.objects.create(
                    booking=booking,
                    equipment=equipment,
                    quantity=qty,
                    sub_total=equipment.rental_price * qty
                )

        if 'payment_method' in data:
            booking.transaction.payment_method = data['payment_method']
            
        new_total_price = float(venue.price_per_hour)
        
        revenue_coach = 0
        if booking.coach_schedule:
            revenue_coach = float(booking.coach_schedule.coach.rate_per_hour)
            new_total_price += revenue_coach
            
        if 'equipment' not in data:
            current_equipments = BookingEquipment.objects.filter(booking=booking)
            equipment_cost = sum([e.sub_total for e in current_equipments])
            new_total_price += float(equipment_cost)
        else:
            recalc_equipments = BookingEquipment.objects.filter(booking=booking)
            equipment_cost = sum([e.sub_total for e in recalc_equipments])
            new_total_price += float(equipment_cost)

        booking.total_price = new_total_price
        booking.save()
        
        transaction = booking.transaction
        transaction.revenue_venue = float(venue.price_per_hour) + float(equipment_cost)
        transaction.revenue_coach = revenue_coach
        transaction.save()
        
        return JsonResponse({'success': True, 'message': 'Booking berhasil diperbarui'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@csrf_exempt
def api_booking_detail(request, booking_id):
    try:
        booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
        
        equipments = []
        for be in booking.equipment_details.all():
            equipments.append({
                'id': be.equipment.pk,
                'name': be.equipment.name,
                'quantity': be.quantity,
            })
        
        data = {
            'success': True,
            'booking': {
                'id': booking.pk,
                'venue_id': booking.venue_schedule.venue.pk,      
                'schedule_id': booking.venue_schedule.pk,        
                'coach_schedule_id': booking.coach_schedule.pk if booking.coach_schedule else None,
                'payment_method': booking.transaction.payment_method if hasattr(booking, 'transaction') else 'CASH',
                'equipments': equipments,
            }
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})
@login_required(login_url='login')
def api_venue_dashboard(request):
    """Flutter API: Get venue dashboard data"""
 
    if not hasattr(request.user, 'profile') or not request.user.profile.is_venue_owner:
        return JsonResponse({
            'success': False,
            'message': 'Hanya venue owner yang dapat mengakses dashboard venue'
        }, status=403)
    
    if request.method == 'GET':
        venues = Venue.objects.filter(owner=request.user)
        venues_data = []
        for venue in venues:
            venues_data.append({
                'id': venue.id,
                'name': venue.name,
                'category': venue.sport_category.name,
                'location': venue.location.name,
                'description': venue.description or '',
                'price_per_hour': float(venue.price_per_hour or 0),
                'image_url': venue.main_image if venue.main_image else None,
            })
        return JsonResponse({'success': True, 'venues': venues_data})
    
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

@csrf_exempt
@login_required(login_url='login')
def api_venue_add(request):
    """Flutter API: Add new venue & Get master data"""
 
    if not hasattr(request.user, 'profile') or not request.user.profile.is_venue_owner:
        return JsonResponse({
            'success': False,
            'message': 'Hanya venue owner yang dapat menambah lapangan'
        }, status=403)
    
 
    if request.method == 'GET':
        locations = LocationArea.objects.all()
        sports = SportCategory.objects.all()
        
        locations_data = [
            {'id': loc.id, 'name': loc.name}
            for loc in locations
        ]
        
        sports_data = [
            {'id': sport.id, 'name': sport.name}
            for sport in sports
        ]
        
        return JsonResponse({
            'success': True,
            'locations': locations_data,
            'sports': sports_data
        })
    
 
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
             
            required_fields = ['name', 'sport_category', 'location', 'price_per_hour']
            for field in required_fields:
                if field not in data:
                    return JsonResponse({
                        'success': False,
                        'message': f'Field {field} wajib diisi'
                    }, status=400)
            
 
            try:
                sport_category = SportCategory.objects.get(id=data['sport_category'])
            except SportCategory.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Kategori olahraga tidak valid'
                }, status=400)
            
            try:
                location = LocationArea.objects.get(id=data['location'])
            except LocationArea.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Lokasi tidak valid'
                }, status=400)
            
 
            venue = Venue.objects.create(
                owner=request.user,
                name=data['name'],
                sport_category=sport_category,
                location=location,
                price_per_hour=data['price_per_hour'],
                description=data.get('description', '')
            )
            
 
            if 'image' in data and data['image']:
                try:
                    venue.main_image = data['image']   
                    venue.save()
                except Exception as e:
                    pass   
            
            return JsonResponse({
                'success': True,
                'message': f"Lapangan '{venue.name}' berhasil ditambahkan.",
                'venue': {
                    'id': venue.id,
                    'name': venue.name,
                    'category': venue.sport_category.name,
                    'location': venue.location.name,
                    'price_per_hour': float(venue.price_per_hour),
                }
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

@csrf_exempt
@login_required(login_url='login')
def api_venue_revenue(request):
    """Flutter API: Get venue revenue report"""
  
    if not hasattr(request.user, 'profile') or not request.user.profile.is_venue_owner:
        return JsonResponse({
            'success': False,
            'message': 'Hanya venue owner yang dapat melihat laporan pendapatan'
        }, status=403)
    
    if request.method == 'GET':
        venues = Venue.objects.filter(owner=request.user)
        
        total_revenue = 0
        venue_revenue_data = []
        
        for venue in venues:
            bookings = Booking.objects.filter(
                venue_schedule__venue=venue,
                transaction__status='CONFIRMED'
            ).select_related('transaction', 'venue_schedule', 'customer', 'coach_schedule__coach__user').order_by('-venue_schedule__date')
            
            venue_revenue = 0
            bookings_data = []
            
            for booking in bookings:
                amount = float(booking.transaction.revenue_venue or 0)
                venue_revenue += amount
                
 
                coach_name = None
                if booking.coach_schedule:
                    coach_name = booking.coach_schedule.coach.user.username

                bookings_data.append({
                    'id': booking.id,
                    'date': booking.venue_schedule.date.strftime('%a, %d %b %Y'),
                    'start_time': booking.venue_schedule.start_time.strftime('%H:%M'),
                    'end_time': booking.venue_schedule.end_time.strftime('%H:%M'),
                    'customer_username': booking.customer.username,
                    'revenue': amount,
                    'coach': coach_name, 
                })
            
            total_revenue += venue_revenue
            
            venue_revenue_data.append({
                'venue_id': venue.id,
                'venue_name': venue.name,
                'total_revenue': venue_revenue,
                'booking_count': bookings.count(),
                'bookings': bookings_data
            })
        
        return JsonResponse({
            'success': True,
            'total_revenue': total_revenue,
            'venue_revenue_data': venue_revenue_data
        })
    
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

@csrf_exempt
@login_required(login_url='login')
def api_venue_manage(request, venue_id):
    """Flutter API: Manage venue (GET data, POST edit/add/delete equipment)"""
 
    if not hasattr(request.user, 'profile') or not request.user.profile.is_venue_owner:
        return JsonResponse({
            'success': False,
            'message': 'Hanya venue owner yang dapat mengelola venue'
        }, status=403)
    
    try:
        venue = Venue.objects.get(id=venue_id, owner=request.user)
    except Venue.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Venue tidak ditemukan atau bukan milik Anda'
        }, status=404)
    
 
    if request.method == 'GET':
        locations = LocationArea.objects.all()
        categories = SportCategory.objects.all()
        equipments = Equipment.objects.filter(venue=venue)
        
        venue_data = {
            'id': venue.id,
            'name': venue.name,
            'description': venue.description or '',
            'price_per_hour': float(venue.price_per_hour or 0),
            'location_id': venue.location.id,
            'sport_category_id': venue.sport_category.id,
            'payment_options': venue.payment_options,
            'image': venue.main_image if venue.main_image else None,  
        }
        
        locations_data = [{'id': loc.id, 'name': loc.name} for loc in locations]
        categories_data = [{'id': cat.id, 'name': cat.name} for cat in categories]
        equipments_data = [{
            'id': eq.id,
            'name': eq.name,
            'stock': eq.stock_quantity,
            'price': float(eq.rental_price)
        } for eq in equipments]
        
        return JsonResponse({
            'success': True,
            'venue': venue_data,
            'locations': locations_data,
            'categories': categories_data,
            'equipments': equipments_data
        })
    
 
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
 
            if action == 'add_equipment':
                equipment = Equipment.objects.create(
                    venue=venue,
                    name=data.get('name'),
                    stock_quantity=data.get('stock_quantity', 0),
                    rental_price=data.get('rental_price', 0)
                )
                
                equipments = Equipment.objects.filter(venue=venue)
                equipments_data = [{
                    'id': eq.id,
                    'name': eq.name,
                    'stock': eq.stock_quantity,
                    'price': float(eq.rental_price)
                } for eq in equipments]
                
                return JsonResponse({
                    'success': True,
                    'message': 'Equipment berhasil ditambahkan',
                    'equipments': equipments_data
                })
            
 
            elif action == 'edit_equipment':
                equipment_id = data.get('equipment_id')
                try:
                    equipment = Equipment.objects.get(id=equipment_id, venue=venue)
                    equipment.name = data.get('name', equipment.name)
                    equipment.stock_quantity = data.get('stock_quantity', equipment.stock_quantity)
                    equipment.rental_price = data.get('rental_price', equipment.rental_price)
                    equipment.save()
                    
                    equipments = Equipment.objects.filter(venue=venue)
                    equipments_data = [{
                        'id': eq.id,
                        'name': eq.name,
                        'stock': eq.stock_quantity,
                        'price': float(eq.rental_price)
                    } for eq in equipments]
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Equipment berhasil diperbarui',
                        'equipments': equipments_data
                    })
                except Equipment.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'message': 'Equipment tidak ditemukan'
                    }, status=404)
            
 
            elif action == 'delete_equipment':
                equipment_id = data.get('equipment_id')
                try:
                    equipment = Equipment.objects.get(id=equipment_id, venue=venue)
                    equipment.delete()
                    
                    equipments = Equipment.objects.filter(venue=venue)
                    equipments_data = [{
                        'id': eq.id,
                        'name': eq.name,
                        'stock': eq.stock_quantity,
                        'price': float(eq.rental_price)
                    } for eq in equipments]
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Equipment berhasil dihapus',
                        'equipments': equipments_data
                    })
                except Equipment.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'message': 'Equipment tidak ditemukan'
                    }, status=404)
            
 
            else:
 
                if 'image' in data and data['image']:
                    try:
 
                        venue.main_image = data['image']
                    except Exception as e:
                        print(f"Error saving image: {e}")
                        pass  

 
                if 'location' in data:
                    try:
                        location = LocationArea.objects.get(id=data['location'])
                        venue.location = location
                    except LocationArea.DoesNotExist:
                        return JsonResponse({
                            'success': False,
                            'message': 'Lokasi tidak valid'
                        }, status=400)
                
 
                if 'sport_category' in data:
                    try:
                        category = SportCategory.objects.get(id=data['sport_category'])
                        venue.sport_category = category
                    except SportCategory.DoesNotExist:
                        return JsonResponse({
                            'success': False,
                            'message': 'Kategori olahraga tidak valid'
                        }, status=400)
                
 
                if 'name' in data:
                    venue.name = data['name']
                if 'description' in data:
                    venue.description = data['description']
                if 'price_per_hour' in data:
                    venue.price_per_hour = data['price_per_hour']
                
                venue.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Venue berhasil diperbarui'
                })
                
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

@csrf_exempt
@login_required(login_url='login')
def api_venue_delete(request, venue_id):
    """Flutter API: Delete venue""" 
    if not hasattr(request.user, 'profile') or not request.user.profile.is_venue_owner:
        return JsonResponse({
            'success': False,
            'message': 'Hanya venue owner yang dapat menghapus venue'
        }, status=403)
    
    if request.method == 'POST' or request.method == 'DELETE':
        try:
            venue = Venue.objects.get(id=venue_id, owner=request.user)
            venue_name = venue.name
            venue.delete()
            
            return JsonResponse({
                'success': True,
                'message': f"Venue '{venue_name}' berhasil dihapus"
            })
        except Venue.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Venue tidak ditemukan atau bukan milik Anda'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def get_coach_profile_json(request):
    """Endpoint JSON untuk mendapatkan coach profile user yang sedang login"""
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
        
        data = {
            'id': coach_profile.id,
            'user_id': str(coach_profile.user.id),
            'username': coach_profile.user.username,
            'first_name': coach_profile.user.first_name,
            'last_name': coach_profile.user.last_name,
            'email': coach_profile.user.email,
            'age': coach_profile.age,
            'experience_desc': coach_profile.experience_desc,
            'rate_per_hour': float(coach_profile.rate_per_hour) if coach_profile.rate_per_hour else None,
            'main_sport_trained': coach_profile.main_sport_trained.name if coach_profile.main_sport_trained else None,
            'main_sport_trained_id': coach_profile.main_sport_trained.id if coach_profile.main_sport_trained else None,
            'service_areas': [area.name for area in coach_profile.service_areas.all()],
            'service_area_ids': [area.id for area in coach_profile.service_areas.all()],
            'is_verified': coach_profile.is_verified,
            'profile_picture': coach_profile.profile_picture if coach_profile.profile_picture else None,
            'created_at': coach_profile.created_at.isoformat() if hasattr(coach_profile, 'created_at') else None,
            'updated_at': coach_profile.updated_at.isoformat() if hasattr(coach_profile, 'updated_at') else None,
        }
        
        return JsonResponse({
            'success': True,
            'has_profile': True,
            'profile': data
        })
        
    except CoachProfile.DoesNotExist:
        return JsonResponse({
            'success': True,
            'has_profile': False,
            'profile': None,
            'user': {
                'username': request.user.username,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)
    
@login_required(login_url='login')
def get_sport_categories_json(request):
    """Endpoint untuk mendapatkan daftar kategori olahraga"""
    try:
        categories = SportCategory.objects.all().values('id', 'name')
        return JsonResponse({
            'success': True,
            'categories': list(categories)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@login_required(login_url='login')
def get_location_areas_json(request):
    """Endpoint untuk mendapatkan daftar area lokasi"""
    try:
        areas = LocationArea.objects.all().values('id', 'name')
        return JsonResponse({
            'success': True,
            'areas': list(areas)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@csrf_exempt
@login_required(login_url='login')
@user_passes_test(lambda user: hasattr(user, 'profile') and user.profile.is_coach, login_url='home')
def save_coach_profile_flutter(request):
    """
    Endpoint untuk save/update coach profile dari Flutter
    Menerima data JSON dengan profile_picture sebagai URL
    """
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Method not allowed'
        }, status=405)
    
    try:
 
        data = json.loads(request.body)
        
 
        try:
            coach_profile = CoachProfile.objects.get(user=request.user)
            is_update = True
        except CoachProfile.DoesNotExist:
            coach_profile = CoachProfile(user=request.user)
            is_update = False
        
 
        age = data.get('age')
        rate_per_hour = data.get('rate_per_hour')
        main_sport_trained_id = data.get('main_sport_trained_id')
        experience_desc = data.get('experience_desc')
        service_area_ids = data.get('service_area_ids')   
        profile_picture_url = data.get('profile_picture')   
        
 
        if not all([age, rate_per_hour, main_sport_trained_id, experience_desc, service_area_ids]):
            return JsonResponse({
                'success': False,
                'message': 'Semua field wajib diisi'
            }, status=400)
        
 
        coach_profile.age = int(age)
        coach_profile.rate_per_hour = float(rate_per_hour)
        
 
        try:
            coach_profile.main_sport_trained = SportCategory.objects.get(id=int(main_sport_trained_id))
        except SportCategory.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Kategori olahraga tidak valid'
            }, status=400)
        
        coach_profile.experience_desc = experience_desc
        
 
        if 'profile_picture' in data:
            if profile_picture_url:  
                coach_profile.profile_picture = profile_picture_url
            else:   
                coach_profile.profile_picture = None   
 
        
 
        coach_profile.save()
        
 
        try:
            service_areas = LocationArea.objects.filter(id__in=service_area_ids)
            coach_profile.service_areas.set(service_areas)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Format area layanan tidak valid: {str(e)}'
            }, status=400)
        
 
        response_data = {
            'success': True,
            'message': f'Profil berhasil {"diperbarui" if is_update else "dibuat"}!',
            'profile': {
                'id': coach_profile.id,
                'age': coach_profile.age,
                'experience_desc': coach_profile.experience_desc,
                'rate_per_hour': float(coach_profile.rate_per_hour),
                'main_sport_trained': coach_profile.main_sport_trained.name,
                'main_sport_trained_id': coach_profile.main_sport_trained.id,
                'service_areas': [area.name for area in coach_profile.service_areas.all()],
                'service_area_ids': [area.id for area in coach_profile.service_areas.all()],
                'is_verified': coach_profile.is_verified,
                'profile_picture': coach_profile.profile_picture if coach_profile.profile_picture else None,
            }
        }
        
        return JsonResponse(response_data, status=200)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Format JSON tidak valid'
        }, status=400)
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'message': f'Format data tidak valid: {str(e)}'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Terjadi kesalahan: {str(e)}'
        }, status=500)
    
@login_required(login_url='login')
@csrf_exempt
def coach_revenue_api(request):
    """API endpoint untuk mendapatkan data revenue coach dalam format JSON"""
    try:
        coach_profile = CoachProfile.objects.get(user=request.user)
        has_profile = True
        
        transactions = Transaction.objects.filter(
            booking__coach_schedule__coach=coach_profile, 
            status='CONFIRMED'
        ).order_by('-transaction_time')
        
        total_revenue = transactions.aggregate(Sum('revenue_coach'))['revenue_coach__sum'] or 0
        
        transactions_data = []
        for transaction in transactions:
            transactions_data.append({
                'id': transaction.id,
                'payment_method': transaction.payment_method,
                'status': transaction.status,
                'revenue_coach': float(transaction.revenue_coach),
                'transaction_time': transaction.transaction_time.strftime('%Y-%m-%d %H:%M:%S'),
            })
        
        return JsonResponse({
            'success': True,
            'has_profile': has_profile,
            'total_revenue': float(total_revenue),
            'transactions': transactions_data,
            'transactions_count': len(transactions_data),
        })
        
    except CoachProfile.DoesNotExist:
        return JsonResponse({
            'success': True,
            'has_profile': False,
            'total_revenue': 0,
            'transactions': [],
            'transactions_count': 0,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)
    
@login_required(login_url='login')
def coach_list_json(request):
    """API endpoint untuk mendapatkan daftar coach dalam format JSON"""
    try:
        coaches_list = CoachProfile.objects.all().select_related(
            'user', 'main_sport_trained'
        ).prefetch_related('service_areas').order_by('user__first_name')
        
 
        query = request.GET.get('q', '')
        if query:
            coaches_list = coaches_list.filter(
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(user__username__icontains=query)
            )
        
 
        sport_filter = request.GET.get('sport', '')
        if sport_filter:
            coaches_list = coaches_list.filter(main_sport_trained__id=sport_filter)
 
        area_filter = request.GET.get('area', '')
        if area_filter:
            coaches_list = coaches_list.filter(service_areas__id=area_filter)
        
 
        paginator = Paginator(coaches_list, 8)
        page_number = request.GET.get('page', 1)
        
        try:
            coaches = paginator.page(page_number)
        except PageNotAnInteger:
            coaches = paginator.page(1)
        except EmptyPage:
            coaches = paginator.page(paginator.num_pages)
        
 
        coaches_data = []
        for coach in coaches:
 
            profile_pic = coach.profile_picture if coach.profile_picture else None
            
 
            service_areas = [{'id': area.id, 'name': area.name} for area in coach.service_areas.all()]
            
            coaches_data.append({
                'id': coach.id,
                'user': {
                    'id': coach.user.id,
                    'username': coach.user.username,
                    'first_name': coach.user.first_name,
                    'last_name': coach.user.last_name,
                    'full_name': coach.user.get_full_name() or coach.user.username,
                },
                'profile_picture': profile_pic,
                'age': coach.age,
                'main_sport_trained': {
                    'id': coach.main_sport_trained.id,
                    'name': coach.main_sport_trained.name,
                } if coach.main_sport_trained else None,
                'rate_per_hour': float(coach.rate_per_hour),
                'service_areas': service_areas,
                'experience_desc': coach.experience_desc or '',
            })
        
        return JsonResponse({
            'success': True,
            'coaches': coaches_data,
            'pagination': {
                'current_page': coaches.number,
                'total_pages': paginator.num_pages,
                'has_previous': coaches.has_previous(),
                'has_next': coaches.has_next(),
                'previous_page': coaches.previous_page_number() if coaches.has_previous() else None,
                'next_page': coaches.next_page_number() if coaches.has_next() else None,
                'total_count': paginator.count,
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)
    
@login_required(login_url='login')
def coach_detail_json(request, coach_id):
    """API endpoint untuk mendapatkan detail coach dalam format JSON"""
    try:
        coach = get_object_or_404(
            CoachProfile.objects.select_related('user', 'main_sport_trained')
            .prefetch_related('service_areas'),
            id=coach_id
        )
        
 
        profile_pic = coach.profile_picture if coach.profile_picture else None
 
        service_areas = [
            {'id': area.id, 'name': area.name} 
            for area in coach.service_areas.all()
        ]
        
 
        reviews = Review.objects.filter(
            target_coach=coach
        ).select_related('customer').order_by('-created_at')[:10]
        
        reviews_data = []
        total_rating = 0
        for review in reviews:
            reviews_data.append({
                'id': review.id,
                'customer_name': review.customer.get_full_name() or review.customer.username,
                'rating': review.rating,
                'comment': review.comment or '',
                'created_at': review.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
            total_rating += review.rating
        
 
        avg_rating = 0
        if reviews.count() > 0:
            avg_rating = total_rating / reviews.count()
        
        coach_data = {
            'id': coach.id,
            'user': {
                'id': coach.user.id,
                'username': coach.user.username,
                'first_name': coach.user.first_name,
                'last_name': coach.user.last_name,
                'full_name': coach.user.get_full_name() or coach.user.username,
                'email': coach.user.email,
            },
            'profile_picture': profile_pic,
            'age': coach.age,
            'gender': coach.gender if hasattr(coach, 'gender') else None,
            'phone': coach.phone if hasattr(coach, 'phone') else None,
            'main_sport_trained': {
                'id': coach.main_sport_trained.id,
                'name': coach.main_sport_trained.name,
            } if coach.main_sport_trained else None,
            'rate_per_hour': float(coach.rate_per_hour),
            'service_areas': service_areas,
            'experience_desc': coach.experience_desc or '',
            'years_of_experience': coach.years_of_experience if hasattr(coach, 'years_of_experience') else None,
            'certifications': coach.certifications if hasattr(coach, 'certifications') else None,
            'achievements': coach.achievements if hasattr(coach, 'achievements') else None,
            'reviews': reviews_data,
            'total_reviews': reviews.count(),
            'avg_rating': round(avg_rating, 1),
        }
        
        return JsonResponse({
            'success': True,
            'coach': coach_data,
        })
        
    except CoachProfile.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Coach tidak ditemukan'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)

def proxy_image(request):
    image_url = request.GET.get('url')
    if not image_url:
        return HttpResponse('No URL provided', status=400)
    
    try:
 
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        
  
        return HttpResponse(
            response.content,
            content_type=response.headers.get('Content-Type', 'image/jpeg')
        )
    except requests.RequestException as e:
        return HttpResponse(f'Error fetching image: {str(e)}', status=500)
    
# --- ADMIN API FOR FLUTTER ---

@login_required
@user_passes_test(is_admin)
def api_admin_dashboard(request):
    data = {
        'total_users': User.objects.count(),
        'total_venues': Venue.objects.count(),
        'total_coaches': CoachProfile.objects.count(),
        'total_bookings': Booking.objects.count(),
    }
    return JsonResponse(data)

@login_required
@user_passes_test(is_admin)
def api_admin_users(request):
    # Ambil parameter pencarian 'q' dari URL, default kosong
    search_query = request.GET.get('q', '').strip()
    
    users = User.objects.select_related('profile').all().order_by('-date_joined')
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query)
        )

    data = []
    for u in users:
        role = "Lainnya"
        if u.is_superuser: role = "Admin"
        elif hasattr(u, 'profile'):
            if u.profile.is_venue_owner: role = "Venue Owner"
            elif u.profile.is_coach: role = "Coach"
            elif u.profile.is_customer: role = "Customer"
        
        phone = "-"
        if hasattr(u, 'profile') and u.profile.phone_number:
            phone = u.profile.phone_number

        data.append({
            'username': u.username,
            'email': u.email or "-",
            'role': role,
            'phone_number': phone,
            'date_joined': u.date_joined.strftime("%d %b %Y")
        })
    return JsonResponse({'users': data})

@login_required
@user_passes_test(is_admin)
def api_admin_venues(request):
    search_query = request.GET.get('q', '').strip()
    
    venues = Venue.objects.select_related('owner', 'sport_category', 'location').all()
    
    if search_query:
        venues = venues.filter(name__icontains=search_query)

    data = []
    for v in venues:
        data.append({
            'name': v.name,
            'owner': v.owner.username,
            'category': v.sport_category.name,
            'location': v.location.name if v.location else "-",
            'price': v.price_per_hour
        })
    return JsonResponse({'venues': data})

@login_required
@user_passes_test(is_admin)
def api_admin_coaches(request):
    search_query = request.GET.get('q', '').strip()
    
    coaches = CoachProfile.objects.select_related('user', 'main_sport_trained').all()
    
    if search_query:
        coaches = coaches.filter(user__username__icontains=search_query)

    data = []
    for c in coaches:
        areas = [a.name for a in c.service_areas.all()] 
        
        data.append({
            'id': c.id,
            'username': c.user.username,
            'sport': c.main_sport_trained.name if c.main_sport_trained else "-",
            'rate': c.rate_per_hour,
            'is_verified': c.is_verified,
            'service_areas': areas,
            'profile_picture': c.profile_picture 
        })
        
    return JsonResponse({'coaches': data})

@login_required
@user_passes_test(is_admin)
def api_admin_bookings(request):
    search_query = request.GET.get('q', '').strip()
    
    bookings = Booking.objects.select_related(
        'customer', 
        'venue_schedule__venue', 
        'transaction'
    ).all().order_by('-booking_time')
    
    if search_query:
        bookings = bookings.filter(
            Q(id__icontains=search_query) |
            Q(customer__username__icontains=search_query) |
            Q(venue_schedule__venue__name__icontains=search_query)
        )

    data = []
    for b in bookings:
        status = "Unknown"
        if hasattr(b, 'transaction'):
            status = b.transaction.status
            
        data.append({
            'id': b.id,
            'customer': b.customer.username,
            'venue': b.venue_schedule.venue.name,
            'total': b.total_price,
            'status': status,
            'coach': b.coach_schedule.coach.user.username if b.coach_schedule else "-"
        })
    return JsonResponse({'bookings': data})
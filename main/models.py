from django.db import models
from django.contrib.auth.models import User 
from django.core.validators import MinValueValidator, MaxValueValidator

class SportCategory(models.Model):
    name = models.CharField(max_length=50, unique=True) 
    def __str__(self):
        return self.name
    class Meta:
        verbose_name_plural = "Kategori Olahraga"

class LocationArea(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name
    class Meta:
        verbose_name_plural = "Area Lokasi"

# --- USER PROFILE ---

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=15, blank=True, null=True, verbose_name="Nomor Telepon")

    is_customer = models.BooleanField(default=True)
    is_venue_owner = models.BooleanField(default=False)
    is_coach = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile {self.user.username}"


# --- VENUE OWNER ---

class Venue(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, 
                              related_name='owned_venues')
    
    name = models.CharField(max_length=150)
    description = models.TextField()
    location = models.ForeignKey(LocationArea, on_delete=models.SET_NULL, null=True)
    price_per_hour = models.DecimalField(max_digits=10, decimal_places=0, 
                                         validators=[MinValueValidator(0)])
    
    sport_category = models.ForeignKey(SportCategory, on_delete=models.PROTECT, 
                                       related_name='venues_by_sport')
    
    main_image = models.ImageField(
        upload_to='venue_photos/', # Disimpan di media/venue_photos/
        null=True, 
        blank=True,
        verbose_name="Foto Utama Lapangan"
    )

    PAYMENT_CHOICES = [
        ('CASH', 'Bayar di Tempat'),
        ('TRANSFER', 'Transfer Manual'),
    ]
    payment_options = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='TRANSFER')

    def __str__(self):
        return self.name

class VenueSchedule(models.Model):
    """Jadwal ketersediaan per lapangan."""
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='schedules')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    is_available = models.BooleanField(default=True)
    is_booked = models.BooleanField(default=False) 

    def __str__(self):
        return f"{self.venue.name} - {self.date} ({self.start_time}-{self.end_time})"

    class Meta:
        unique_together = (('venue', 'date', 'start_time'),)
        ordering = ['date', 'start_time']

class Equipment(models.Model):
    """Data alat yang disewakan oleh Venue."""
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='equipment')
    name = models.CharField(max_length=100)
    rental_price = models.DecimalField(max_digits=10, decimal_places=0, 
                                       validators=[MinValueValidator(0)])
    stock_quantity = models.IntegerField(default=1, validators=[MinValueValidator(0)])

    def __str__(self):
        return f"{self.name} ({self.venue.name})"

# --- COACH ---

class CoachProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coach_profile_data')
    
    age = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(18)])
    experience_desc = models.TextField(blank=True)
    rate_per_hour = models.DecimalField(max_digits=10, decimal_places=0, validators=[MinValueValidator(0)])
    
    profile_picture = models.ImageField(
        upload_to='coach_photos/',
        null=True, blank=True,
        verbose_name="Foto Profil"
    )
    
    # kalau kategori olahraga dihapus → tolak (biar tidak merusak referensi)
    main_sport_trained = models.ForeignKey(
        'SportCategory', on_delete=models.PROTECT, related_name='coaches_by_sport'
    )
    
    service_areas = models.ManyToManyField('LocationArea', related_name='coaches_serving')
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def __str__(self):
        return self.user.get_full_name() or self.user.username
    
class CoachSchedule(models.Model):
    coach = models.ForeignKey(
        CoachProfile, on_delete=models.CASCADE, related_name='schedules'
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    is_available = models.BooleanField(default=True)
    is_booked = models.BooleanField(default=False)

    class Meta:
        unique_together = (('coach', 'date', 'start_time'),)
        ordering = ['date', 'start_time']

# --- CUSTOMER ---

class Booking(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_bookings')

    # venue_schedule tetap CASCADE karena venue bisa dikelola internal
    venue_schedule = models.OneToOneField(
        'VenueSchedule', on_delete=models.CASCADE
    )

    # ubah dari CASCADE → SET_NULL agar riwayat booking tidak hilang jika coach dihapus
    coach_schedule = models.OneToOneField(
        'CoachSchedule', on_delete=models.SET_NULL, null=True, blank=True
    )
    
    booking_time = models.DateTimeField(auto_now_add=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=0)

    def __str__(self):
        return f"Booking #{self.id} oleh {self.customer.username}"

class BookingEquipment(models.Model):
    """Detail peralatan yang disewa dalam satu booking."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='equipment_details')
    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    sub_total = models.DecimalField(max_digits=10, decimal_places=0)

    def __str__(self):
        return f"{self.equipment.name} ({self.quantity} unit)"

class Transaction(models.Model):
    """Simulasi Transaksi, Status, dan Pembagian Pendapatan."""
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT)
    
    STATUS_CHOICES = [
        ('PENDING', 'Menunggu Konfirmasi Pembayaran'),
        ('CONFIRMED', 'Booking Terkonfirmasi'),
        ('CANCELLED', 'Dibatalkan'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    payment_method = models.CharField(max_length=20)
    transaction_time = models.DateTimeField(auto_now_add=True)

    revenue_venue = models.DecimalField(max_digits=10, decimal_places=0, default=0)
    revenue_coach = models.DecimalField(max_digits=10, decimal_places=0, default=0) 
    revenue_platform = models.DecimalField(max_digits=10, decimal_places=0, default=0)

    def __str__(self):
        return f"Transaksi #{self.id} - {self.status}"
    
# --- RATING & REVIEW ---

class Review(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_given')
    
    target_venue = models.ForeignKey('Venue', on_delete=models.CASCADE, null=True, blank=True, related_name='reviews')
    
    # review ikut hilang kalau coach dihapus
    target_coach = models.ForeignKey(
        'CoachProfile', on_delete=models.CASCADE, null=True, blank=True, related_name='reviews_received'
    )
    
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
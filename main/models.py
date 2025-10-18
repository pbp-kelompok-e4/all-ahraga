from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator

# --- MASTER DATA MODELS ---

class SportCategory(models.Model):
    """Data Master Kategori Olahraga (Tempat Futsal, Basket, dll. disimpan)"""
    name = models.CharField(max_length=50, unique=True) 

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Kategori Olahraga"

class LocationArea(models.Model):
    """Data Master Area/Lokasi Pelayanan"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Area Lokasi"

# --- AUTENTIKASI & AKUN ---

class User(AbstractUser):
    # Field untuk menentukan Role
    is_customer = models.BooleanField(default=True)
    is_venue_owner = models.BooleanField(default=False)
    is_coach = models.BooleanField(default=False)
    phone_number = models.CharField(max_length=15, blank=True, null=True)

    # --- TAMBAHAN UNTUK MENGATASI CLASH (PENTING!) ---
    
    # Menambahkan related_name unik untuk menghindari konflik dengan auth.User
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name=('groups'),
        blank=True,
        help_text=(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        # PENTING: Tambahkan related_name yang unik
        related_name="main_user_groups", 
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name=('user permissions'),
        blank=True,
        help_text=('Specific permissions for this user.'),
        # PENTING: Tambahkan related_name yang unik
        related_name="main_user_permissions",
        related_query_name="user",
    )
    
    # -----------------------------------------------------------------

    def __str__(self):
        return self.username

# --- MANAJEMEN VENUE (VENUE OWNER) ---

class Venue(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, 
                              limit_choices_to={'is_venue_owner': True}, 
                              related_name='venues')
    
    name = models.CharField(max_length=150)
    description = models.TextField()
    location = models.ForeignKey(LocationArea, on_delete=models.SET_NULL, null=True)
    price_per_hour = models.DecimalField(max_digits=10, decimal_places=0, 
                                         validators=[MinValueValidator(0)])
    
    # Kategori Lapangan: ForeignKey karena hanya 1 kategori per Lapangan
    sport_category = models.ForeignKey(SportCategory, on_delete=models.PROTECT, 
                                       related_name='venues_by_sport')
    
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
    
    is_available = models.BooleanField(default=True) # Digunakan saat VenueOwner set jadwal
    is_booked = models.BooleanField(default=False)   # Diubah jadi True setelah booking dikonfirmasi

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

# --- MANAJEMEN PELATIH (COACH) ---

class CoachProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, 
                                limit_choices_to={'is_coach': True}, 
                                related_name='coach_profile')
    
    age = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(18)])
    experience_desc = models.TextField(blank=True)
    rate_per_hour = models.DecimalField(max_digits=10, decimal_places=0, 
                                        validators=[MinValueValidator(0)])
    
    # ForeignKey: Pelatih hanya melatih SATU Kategori Utama
    main_sport_trained = models.ForeignKey(SportCategory, on_delete=models.PROTECT, 
                                           related_name='coaches_by_sport') 
    
    service_areas = models.ManyToManyField(LocationArea, related_name='coaches_serving')
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.user.get_full_name() or self.user.username
    
class CoachSchedule(models.Model):
    """Jadwal kosong dan ketersediaan pelatih."""
    coach = models.ForeignKey(CoachProfile, on_delete=models.CASCADE, related_name='schedules')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    is_available = models.BooleanField(default=True)
    is_booked = models.BooleanField(default=False) # Diubah jadi True setelah booking dikonfirmasi

    def __str__(self):
        return f"{self.coach.user.username} - {self.date} ({self.start_time}-{self.end_time})"

    class Meta:
        unique_together = (('coach', 'date', 'start_time'),)
        ordering = ['date', 'start_time']

# --- PEMESANAN & PEMBAYARAN (CUSTOMER) ---

class Booking(models.Model):
    customer = models.ForeignKey(User, on_delete=models.PROTECT, 
                                 limit_choices_to={'is_customer': True}, 
                                 related_name='bookings')
    
    # Note: Menggunakan OneToOneField akan membuat jadwal langsung ter-reserved 
    venue_schedule = models.OneToOneField(VenueSchedule, on_delete=models.PROTECT) 
    coach_schedule = models.OneToOneField(CoachSchedule, on_delete=models.PROTECT, null=True, blank=True)
    
    booking_time = models.DateTimeField(auto_now_add=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=0)

    def __str__(self):
        return f"Booking #{self.id} oleh {self.customer.username}"

class BookingEquipment(models.Model):
    """Detail peralatan yang disewa dalam satu booking."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='equipment_details')
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT)
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

    # --- FIELD UNTUK SIMULASI PEMBAGIAN PENDAPATAN ---
    
    # Biaya Lapangan & Alat yang masuk ke Venue
    revenue_venue = models.DecimalField(max_digits=10, decimal_places=0, default=0)
    
    # Biaya Sesi yang masuk ke Coach (hanya jika coach_schedule tidak null)
    revenue_coach = models.DecimalField(max_digits=10, decimal_places=0, default=0) 
    
    # Komisi yang masuk ke Platform (All-Ahraga)
    revenue_platform = models.DecimalField(max_digits=10, decimal_places=0, default=0)

    def __str__(self):
        return f"Transaksi #{self.id} - {self.status}"
    
# --- RATING & REVIEW ---

class Review(models.Model):
    """Ulasan dan Rating yang diberikan Customer kepada Venue/Coach."""
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_reviews')
    
    target_venue = models.ForeignKey(Venue, on_delete=models.CASCADE, null=True, blank=True, related_name='reviews')
    target_coach = models.ForeignKey(CoachProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='reviews')
    
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        target = self.target_venue or self.target_coach
        return f"Rating {self.rating} untuk {target}"
    
    class Meta:
        pass
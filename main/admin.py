from django.contrib import admin
from .models import (
    UserProfile,
    Venue,
    VenueSchedule,
    Equipment,
    LocationArea,
    SportCategory,
    CoachProfile,
    CoachSchedule,
    Booking,
    BookingEquipment,
    Transaction,
    Review
    # Tambahkan model lain jika ada
)

# Cara sederhana (menampilkan model dengan pengaturan default)
admin.site.register(UserProfile)
admin.site.register(Venue)
admin.site.register(VenueSchedule)
admin.site.register(Equipment)
admin.site.register(LocationArea)
admin.site.register(SportCategory)
admin.site.register(CoachProfile)
admin.site.register(CoachSchedule)
admin.site.register(Booking)
admin.site.register(BookingEquipment)
admin.site.register(Transaction)
admin.site.register(Review)

# Anda bisa menambahkan kustomisasi tampilan admin di sini nanti
# Contoh:
# class VenueAdmin(admin.ModelAdmin):
#     list_display = ('name', 'location', 'sport_category', 'owner')
#     list_filter = ('location', 'sport_category')
#     search_fields = ('name', 'description')
#
# admin.site.register(Venue, VenueAdmin)
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
)


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


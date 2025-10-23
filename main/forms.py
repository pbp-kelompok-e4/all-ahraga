from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User 
from .models import UserProfile, Venue, VenueSchedule, Equipment, LocationArea, SportCategory

ROLE_CHOICES = [
    ('CUSTOMER', 'Customer'),
    ('VENUE_OWNER', 'Venue Owner'),
    ('COACH', 'Coach'),
]

class CustomUserCreationForm(UserCreationForm):
    role_type = forms.ChoiceField(choices=ROLE_CHOICES, label="Sign Up As")
    phone_number = forms.CharField(max_length=15, required=True, label="Phone Number")
    email = forms.EmailField(required=True, label="Email Address") 
    profile_picture = forms.ImageField(required=False, label="Profile Picture")
    service_area = forms.ModelChoiceField(queryset=LocationArea.objects.all(), required=False, label="Service Area")
    selected_venues_json = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = User 
        fields = ('username', 'email', 'phone_number', 'role_type',) 

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get('email')
        if commit:
            user.save()

        role = self.cleaned_data.get('role_type')
        profile = UserProfile.objects.create(
            user=user,
            phone_number=self.cleaned_data.get('phone_number'),
            is_customer=(role == 'CUSTOMER'),
            is_venue_owner=(role == 'VENUE_OWNER'),
            is_coach=(role == 'COACH'),
        )

        if role == 'COACH':
            from .models import CoachProfile, CoachVenue, Venue

            coach = CoachProfile.objects.create(
                user=user,
            )

            pic = self.cleaned_data.get('profile_picture')
            if pic:
                coach.profile_picture = pic
                coach.save()

            area = self.cleaned_data.get('service_area')
            if area:
                coach.service_areas.add(area)

            import json
            sv = self.cleaned_data.get('selected_venues_json')
            if sv:
                try:
                    data = json.loads(sv)
                    for item in data:
                        vid = item.get('venue_id')
                        rate = item.get('rate')
                        if vid:
                            try:
                                venue = Venue.objects.get(id=vid)
                                CoachVenue.objects.create(coach=coach, venue=venue, rate=rate or 0)
                            except Venue.DoesNotExist:
                                continue
                except Exception:
                    pass

        return user
    
class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = [
            'name', 'description', 'location', 'sport_category', 
            'price_per_hour', 'payment_options'
        ]
        # 'owner' tidak dimasukkan karena akan diisi otomatis oleh view

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mengisi pilihan (queryset) untuk location dan sport_category
        self.fields['location'].queryset = LocationArea.objects.all()
        self.fields['sport_category'].queryset = SportCategory.objects.all()
        # Anda bisa menambahkan styling/widget di sini jika perlu
        self.fields['description'].widget = forms.Textarea(attrs={'rows': 4})


class VenueScheduleForm(forms.ModelForm):
    class Meta:
        model = VenueSchedule
        fields = ['date', 'start_time', 'end_time', 'is_available']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }
        # 'venue' akan diisi otomatis oleh view

class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['name', 'rental_price', 'stock_quantity']
        # 'venue' akan diisi otomatis oleh view
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User 
from .models import UserProfile, Venue, VenueSchedule, Equipment, LocationArea, SportCategory, CoachProfile, CoachSchedule

ROLE_CHOICES = [
    ('CUSTOMER', 'Customer'),
    ('VENUE_OWNER', 'Venue Owner'),
    ('COACH', 'Pelatih'),
]

class CustomUserCreationForm(UserCreationForm):
    role_type = forms.ChoiceField(choices=ROLE_CHOICES, label="Daftar Sebagai")
    phone_number = forms.CharField(max_length=15, required=True, label="Nomor Telepon")
    email = forms.EmailField(required=True, label="Email Address") 

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
        return user
    
class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = [
            'name', 'description', 'location', 'sport_category', 
            'price_per_hour', 'payment_options', 'main_image'
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

class CoachProfileForm(forms.ModelForm):
    profile_picture_url = forms.URLField(
        required=False,
        label="URL Foto Profil",
        help_text="Masukkan URL gambar untuk foto profil Anda (opsional)"
    )

    class Meta:
        model = CoachProfile
        fields = ['age', 'experience_desc', 'rate_per_hour', 'main_sport_trained', 'service_areas']  # sesuaikan jika ada field lain
        widgets = {
            'service_areas': forms.CheckboxSelectMultiple(),
            'experience_desc': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_profile_picture_url(self):
        url = self.cleaned_data.get('profile_picture_url')
        if url:
            valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
            if not url.lower().endswith(valid_extensions):
                raise forms.ValidationError("URL harus mengarah ke file gambar (jpg, jpeg, png, gif, webp).")
        return url

class CoachScheduleForm(forms.ModelForm):
    class Meta:
        model = CoachSchedule
        fields = ['date', 'start_time', 'end_time', 'is_available']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }
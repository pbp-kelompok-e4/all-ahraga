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
            'date': forms.DateInput(
                attrs={
                    'type': 'text',
                    'class': 'datepicker mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm',
                    'placeholder': 'Pilih tanggal'
                }
            ),
            'start_time': forms.TextInput(
                attrs={
                    'class': 'timepicker mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm',
                    'placeholder': 'HH:MM'
                }
            ),
            'end_time': forms.TextInput(
                attrs={
                    'class': 'timepicker mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm',
                    'placeholder': 'HH:MM'
                }
            ),
            'is_available': forms.CheckboxInput(
                attrs={
                    'class': 'h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].label = "Tanggal"
        self.fields['start_time'].label = "Waktu Mulai"
        self.fields['end_time'].label = "Waktu Selesai"
        self.fields['is_available'].label = "Tersedia"
        self.fields['date'].help_text = "Pilih tanggal untuk jadwal venue"
        self.fields['start_time'].help_text = "Format 24 jam (mis. 09:00)"
        self.fields['end_time'].help_text = "Format 24 jam (mis. 10:00)"

class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['name', 'rental_price', 'stock_quantity']
        # 'venue' akan diisi otomatis oleh view

class CoachProfileForm(forms.ModelForm):
    class Meta:
        model = CoachProfile
        fields = ['age', 'experience_desc', 'rate_per_hour', 'main_sport_trained', 'service_areas']
        widgets = {
            'service_areas': forms.CheckboxSelectMultiple(),
        }

class CoachScheduleForm(forms.ModelForm):
    class Meta:
        model = CoachSchedule
        fields = ['date', 'start_time', 'end_time', 'is_available']
        widgets = {
            'date': forms.DateInput(
                attrs={
                    'type': 'text',               
                    'class': 'datepicker mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm',
                    'placeholder': 'Pilih tanggal'
                }
            ),
            'start_time': forms.TextInput(
                attrs={
                    'class': 'timepicker mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm',
                    'placeholder': 'HH:MM'
                }
            ),
            'end_time': forms.TextInput(
                attrs={
                    'class': 'timepicker mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm',
                    'placeholder': 'HH:MM'
                }
            ),
            'is_available': forms.CheckboxInput(
                attrs={
                    'class': 'h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500'
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].label = "Tanggal Sesi"
        self.fields['start_time'].label = "Waktu Mulai"
        self.fields['end_time'].label = "Waktu Selesai"
        self.fields['is_available'].label = "Tersedia"
        self.fields['date'].help_text = "Pilih tanggal sesi"
        self.fields['start_time'].help_text = "Format 24 jam (mis. 14:30)"
        self.fields['end_time'].help_text = "Format 24 jam (mis. 15:30)"
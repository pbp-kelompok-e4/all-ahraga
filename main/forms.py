from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User 
from .models import UserProfile, Venue, VenueSchedule, Equipment, LocationArea, SportCategory, CoachProfile, CoachSchedule
from django.forms.widgets import DateInput, TextInput
from .models import Review

ROLE_CHOICES = [
    ('CUSTOMER', 'Customer'),
    ('VENUE_OWNER', 'Venue Owner'),
    ('COACH', 'Coach'),
]

class CustomUserCreationForm(UserCreationForm):
    role_type = forms.ChoiceField(choices=ROLE_CHOICES, label="Sign Up As")
    phone_number = forms.CharField(max_length=15, required=True, label="Phone Number")
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
    # Tambahkan field ini, sama seperti di CoachScheduleForm
    end_time_global = forms.CharField(
        label="Waktu Selesai Harian",
        help_text="Waktu terakhir sesi (mis. 22:00). Slot dibuat per jam hingga waktu ini.",
        widget=TextInput(
            attrs={
                'class': 'timepicker mt-1 block w-full rounded-md border-gray-300 shadow-sm sm:text-sm',
                'placeholder': 'HH:MM (Akhir Rentang)'
            }
        ),
        required=True
    )

    class Meta:
        model = VenueSchedule
        # Hapus 'end_time' dari fields, kita ganti dengan 'end_time_global'
        fields = ['date', 'start_time', 'is_available']
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
                    'placeholder': 'HH:MM (Mulai Slot Pertama)'
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
        self.fields['start_time'].label = "Waktu Mulai Slot Pertama"
        self.fields['is_available'].label = "Tersedia"
        self.fields['date'].help_text = "Pilih tanggal untuk jadwal venue"
        self.fields['start_time'].help_text = "Format 24 jam (mis. 09:00)"
        # Hapus label/help_text untuk 'end_time' yang sudah tidak ada

class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = ['name', 'rental_price', 'stock_quantity']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-teal-700 focus:border-transparent transition-all',
                'placeholder': 'e.g., Basketball, Racket, etc.'
            }),
            'rental_price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-teal-700 focus:border-transparent transition-all',
                'placeholder': '0',
                'min': '0'
            }),
            'stock_quantity': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-teal-700 focus:border-transparent transition-all',
                'placeholder': '0',
                'min': '0'
            }),
        }
        labels = {
            'name': 'Equipment Name',
            'rental_price': 'Rental Price (Rp)',
            'stock_quantity': 'Stock Quantity',
        }

class CoachProfileForm(forms.ModelForm):
    # pakai upload image sesuai CoachProfile.profile_picture
    profile_picture = forms.ImageField(
        required=False,
        label="Foto Profil",
        widget=forms.ClearableFileInput(attrs={'accept': 'image/*'})
    )

    class Meta:
        model = CoachProfile
        # pastikan fields sesuai dengan CoachProfile model
        fields = [
            'age',
            'experience_desc',
            'rate_per_hour',
            'main_sport_trained',
            'service_areas',
            'profile_picture',
        ]
        widgets = {
            'service_areas': forms.CheckboxSelectMultiple(),
            'experience_desc': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_age(self):
        age = self.cleaned_data.get('age')
        if age in (None, ''):
            return age
        try:
            age = int(age)
        except (TypeError, ValueError):
            raise forms.ValidationError("Umur harus berupa angka")
        if age < 18:
            raise forms.ValidationError("Umur harus >= 18")
        return age

    def clean_rate_per_hour(self):
        rp = self.cleaned_data.get('rate_per_hour')
        if rp in (None, ''):
            return rp
        try:
            # allow integer-like decimal
            return int(rp)
        except (TypeError, ValueError):
            raise forms.ValidationError("Tarif harus berupa angka")

class CoachScheduleForm(forms.ModelForm):
    end_time_global = forms.CharField(
        label="Waktu Selesai Harian",
        help_text="Waktu terakhir sesi (mis. 22:00). Slot dibuat per jam hingga waktu ini.",
        widget=TextInput(
            attrs={
                'class': 'timepicker form-input-style', 
                'placeholder': 'HH:MM (Akhir Rentang)'
            }
        ),
        required=True
    )

    class Meta:
        model = CoachSchedule
        fields = ['date', 'start_time', 'is_available'] 
        widgets = {
            'date': DateInput(
                attrs={
                    'type': 'text',
                    'class': 'datepicker form-input-style',
                    'placeholder': 'Pilih tanggal'
                }
            ),
            'start_time': TextInput(
                attrs={
                    'class': 'timepicker form-input-style',
                    'placeholder': 'HH:MM (Mulai Slot Pertama)'
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
        self.fields['start_time'].label = "Waktu Mulai Slot Pertama"
        self.fields['is_available'].label = "Tersedia"
        self.fields['date'].help_text = "Pilih tanggal sesi"
        self.fields['start_time'].help_text = "Format 24 jam (mis. 08:00)"

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "comment": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Tulis komentar kamu..."
            })
        }
    

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User 
from .models import UserProfile 

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
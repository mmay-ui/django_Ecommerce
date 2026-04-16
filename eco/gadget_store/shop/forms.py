from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email Address")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',)


class CustomAuthenticationForm(AuthenticationForm):
    # Gawing "Username or Email" ang label
    username = forms.CharField(
        label="Username or Email",
        widget=forms.TextInput(attrs={'autofocus': True}),
    )

    def clean(self):
        cleaned_data = super().clean()
        username_or_email = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if username_or_email and password:
            # Hanapin kung may User na may ganitong email
            user = User.objects.filter(email=username_or_email).first()
            
            if user:
                # Kung meron, palitan ang username value para mag-match
                cleaned_data['username'] = user.username
            # Kung wala, mananatili yung input bilang username
        
        return cleaned_data
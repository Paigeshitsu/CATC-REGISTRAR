from django import forms
from .models import DocumentRequest, StudentMasterList, DocumentType


class StudentIDLoginForm(forms.Form):
    OTP_METHOD_CHOICES = [
        ('email', 'Email'),
        ('iprog', 'SMS (iProg)'),
    ]
    
    student_id = forms.CharField(
        max_length=7,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'S######',
            'autofocus': True
        })  
    )
    otp_method = forms.ChoiceField(
        choices=OTP_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-lg'}),
        initial='email',
    )

class OTPVerifyForm(forms.Form):
    otp_code = forms.CharField(
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control lg text-center',
            'placeholder': '000000',
            'style': 'letter-spacing: 10px; font-size: 24px;'
        })
    )

class StudentRequestForm(forms.ModelForm):
    document_types = forms.ModelMultipleChoiceField(
        queryset=DocumentType.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Select Documents"
    )

    class Meta:
        model = DocumentRequest
        fields = ['reason'] # We handle document_types manually in the view
        widgets = {
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

#class RegistrarProcessForm(forms.Form):
    #content = forms.CharField(
     #   widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 10, 'placeholder': 'Type the certification text here...'}),
   #     label="Document Content"
   # )
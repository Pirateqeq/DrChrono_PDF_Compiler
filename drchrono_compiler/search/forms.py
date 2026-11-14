from django import forms

class PatientSearchForm(forms.Form):
    """Patient search: first name, last name and/or date of birth; at least one is required."""

    first_name = forms.CharField(
        max_length=100,
        required=False,
        label='First Name',
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., John',
            'class': 'form-control',
        })
    )

    last_name = forms.CharField(
            max_length=100,
            required=False,
            label="Last Name",
            widget=forms.TextInput(attrs={
                'placeholder': 'e.g., Smith',
                'class': 'form-control',
            })
        )
    date_of_birth = forms.DateField(
            required=False,
            label="Date of Birth",
            widget=forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'placeholder': 'YYYY-MM-DD',
            }),
            input_formats=['%Y-%m-%d', '%m/%d/%Y'],
        )
    
    def clean(self):
        cleaned_data = super().clean()
        if not any(cleaned_data.get(field) for field in ('first_name', 'last_name', 'date_of_birth')):
            raise forms.ValidationError('Please provide at least one of: First Name, Last Name, or Date Of Birth')
        return cleaned_data
from django import forms

class PatientSearchForm(forms.Form):
    """
    Form for searching patients via API call
    - Last name is required
    - First name is optional
    - DOB is optional
    """

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
        first = cleaned_data.get('first_name', '').strip()
        last = cleaned_data.get('last_name', '').strip()
        dob = cleaned_data.get('date_of_birth')

        if not (first or last or dob):
            raise forms.ValidationError(
                'Please provide at least one of: First Name, Last Name, or Date Of Birth'
            )
        
        return cleaned_data
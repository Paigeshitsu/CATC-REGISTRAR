from django import forms
from .models import DocumentRequest

class StudentRequestForm(forms.ModelForm):
    """
    This form allows the Student to "Select & Fill Form" 
    as seen in the flowchart.
    """
    class Meta:
        model = DocumentRequest
        # We only show these two fields to the student. 
        # 'status' and 'student' are handled automatically in the background.
        fields = ['document_type', 'reason']
        
        # Widgets are used to add HTML attributes like CSS classes or placeholders
        widgets = {
            'document_type': forms.Select(attrs={
                'class': 'form-select', 
                'placeholder': 'Select the document you need'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4, 
                'placeholder': 'Explain why you are requesting this document (e.g., For Employment, Scholarship, etc.)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(StudentRequestForm, self).__init__(*args, **kwargs)
        # Adds a friendly label name for the fields
        self.fields['document_type'].label = "Select Document"
        self.fields['reason'].label = "Purpose of Request"
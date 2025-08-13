from django import forms
from orgs.models import Org
from compliance_app.models import ComplianceRecord


class OrgCreateForm(forms.ModelForm):
    class Meta:
        model = Org
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "New organisation name",
                "required": True,
            }),
        }

    def save(self, owner, commit=True):
        org = super().save(commit=False)
        org.user = owner  # your FK is 'user'
        if commit:
            org.save()
        return org


class ComplianceRecordCreateForm(forms.ModelForm):
    class Meta:
        model = ComplianceRecord
        fields = ["org", "requirement", "status"]
        widgets = {
            "requirement": forms.TextInput(attrs={
                "class": "input",
                "placeholder": "Requirement name",
                "required": True,
            }),
            "status": forms.Select(attrs={
                "class": "input",
                "required": True,
            }),
            "org": forms.Select(attrs={
                "class": "input",
                "required": True,
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)   # store current user
        super().__init__(*args, **kwargs)
        if self.user:
            # Limit org choices to those owned by this user
            self.fields["org"].queryset = Org.objects.filter(user=self.user)

    def clean_org(self):
        """Extra safety: prevent adding a record to an org you don't own."""
        org = self.cleaned_data["org"]
        if self.user and org.user_id != self.user.id:
            raise forms.ValidationError("You can only add records to your own organisations.")
        return org

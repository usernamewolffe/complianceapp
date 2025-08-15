from django import forms
from .models import Site


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = [
            "name", "essential_service", "network_role", "eic_code", "timezone",
            "address_line1", "address_line2", "city", "postcode", "country_code",
            "contact_name", "contact_role", "contact_email", "contact_phone",
            "ooh_phone", "dpo_email",
        ]
        labels = {
            "name": "Site name",
            "essential_service": "Essential service",
            "network_role": "Network role",
            "eic_code": "EIC code",
            "timezone": "Time zone",
            "address_line1": "Address line 1",
            "address_line2": "Address line 2",
            "city": "Town/City",
            "postcode": "Postcode",
            "country_code": "Country (ISO-2)",
            "contact_name": "Primary incident contact – name",
            "contact_role": "Primary incident contact – role",
            "contact_email": "Primary incident contact – email",
            "contact_phone": "Primary incident contact – phone",
            "ooh_phone": "Out-of-hours phone",
            "dpo_email": "DPO / privacy email",
        }
        widgets = {
            "name": forms.TextInput(attrs={"required": True}),
            "essential_service": forms.Select(),
            "network_role": forms.Select(),
            "eic_code": forms.TextInput(),
            "timezone": forms.TextInput(attrs={"placeholder": "Europe/London"}),
            "address_line1": forms.TextInput(),
            "address_line2": forms.TextInput(),
            "city": forms.TextInput(),
            "postcode": forms.TextInput(),
            "country_code": forms.TextInput(attrs={"maxlength": 2}),
            "contact_name": forms.TextInput(),
            "contact_role": forms.TextInput(),
            "contact_email": forms.EmailInput(),
            "contact_phone": forms.TextInput(),
            "ooh_phone": forms.TextInput(),
            "dpo_email": forms.EmailInput(),
        }

    def clean_country_code(self):
        cc = (self.cleaned_data.get("country_code") or "").upper()
        if cc and len(cc) != 2:
            raise forms.ValidationError("Use a 2-letter ISO country code (e.g. GB).")
        return cc

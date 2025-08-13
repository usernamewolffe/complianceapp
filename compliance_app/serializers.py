from rest_framework import serializers
from .models import ComplianceRecord

class ComplianceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceRecord
        fields = "__all__"

    def validate_org(self, org):
        request = self.context.get("request")
        if request and org.user != request.user:
            raise serializers.ValidationError("You can only use your own org.")
        return org

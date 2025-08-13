from rest_framework import serializers
from .models import Org

class OrgSerializer(serializers.ModelSerializer):
    class Meta:
        model = Org
        fields = ['id', 'name', 'description', 'created_at']  # no 'user' here

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

# orgs/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Org, Membership, OrgInvite

User = get_user_model()

class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email")

class MembershipSerializer(serializers.ModelSerializer):
    user = UserPublicSerializer(read_only=True)
    class Meta:
        model = Membership
        fields = ("id", "user", "role", "is_active", "invited_at", "accepted_at")

class OrgInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgInvite
        fields = ("id", "email", "role", "token", "expires_at", "used_at")
        read_only_fields = ("token", "expires_at", "used_at")


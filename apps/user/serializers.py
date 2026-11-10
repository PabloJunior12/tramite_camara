from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Module, UserPermission, Position

User = get_user_model()

class PositionSerializer(serializers.ModelSerializer):

    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True
    )

    class Meta:
        model = Position
        fields = [
            "id",
            "name",
            "code",
            "category",
            "category_display",
            "order"
        ]

class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        exclude = ['password']

class ModuleSerializer(serializers.ModelSerializer):

    children = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = ["id", "name", "code", "icon", "children", "path"]

    def get_children(self, obj):
        children = obj.children.all().order_by("order")
        return ModuleSerializer(children, many=True).data
    
class UserPermissionSerializer(serializers.ModelSerializer):

    module = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all())

    class Meta:
        model = UserPermission
        fields = ['module']

class UserAdminCreateSerializer(serializers.ModelSerializer):

    email = serializers.EmailField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[]
    )

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        trim_whitespace=False,
    )

    class Meta:
        model = User
        fields = (

            "first_name",
            "last_name",
            "position",
            "email",
            "phone",
            "username",
            "password",
            "role",    

            "business_name",
            "document_type",
            "document_number",
            "representation",
            "bar_association",
            "bar_registration_number",
            "website",
            "linkedin",
            "profession",
            "university",
            "sunedu_registered",
            "masters_degree",
            "masters_university",
            "masters_sunedu_registered",
            "emission_date",
            "address",
          
        )

    def validate_email(self, value):

        if not value or not value.strip():
            return None

        value = value.strip().lower()

        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este correo."
            )

        return value
    
    def validate_username(self, value):
        value = value.strip()

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este nombre de usuario."
            )

        return value

    def create(self, validated_data):
        password = validated_data.pop("password")

        return User.objects.create_user(
            username=validated_data.pop("username"),
            password=password,
            **validated_data,
        )

class UserAdminUpdateSerializer(serializers.ModelSerializer):

    email = serializers.EmailField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[]
    )

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=False,
        min_length=8,
        trim_whitespace=False,
    )

    class Meta:
        model = User
        fields = (

            "first_name",
            "last_name",
            "position",
            "email",
            "phone",
            "username",
            "password",
            "role",

            "address",
            "is_active",
            "business_name",
            "document_type",
            "document_number",
            "representation",
            "bar_association",
            "bar_registration_number",
            "website",
            "linkedin",
            "profession",
            "university",
            "sunedu_registered",
            "masters_degree",
            "masters_university",
            "masters_sunedu_registered",
            "emission_date",
        )

    def validate_username(self, value):
        value = value.strip()

        queryset = User.objects.filter(username__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este nombre de usuario."
            )

        return value

    def validate_email(self, value):

        if not value or not value.strip():
            return None

        value = value.strip().lower()

        queryset = User.objects.filter(email__iexact=value)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este correo."
            )

        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance
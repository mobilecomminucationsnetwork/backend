from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid



class User(AbstractUser):
    """Sistem kullanıcıları için model"""
    phone_number = models.CharField(max_length=15, blank=True)
    is_face_registered = models.BooleanField(default=False)
    face_embedding = models.BinaryField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Çakışmaları önlemek için related_name ekleyin
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='api_user_groups',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='api_user_permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def __str__(self):
        return self.username

class FaceVector(models.Model):
    """Yüz vektörlerini saklayan model"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='face_vectors', null=True, blank=True)
    name = models.CharField(max_length=100, blank=True)
    vector_data = models.BinaryField()
    vector_size = models.IntegerField()
    # Yeni alan: Base64 kodlanmış görsel verisi
    face_image_base64 = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(null=True, blank=True)
    
    def __str__(self):
        return f"Face Vector {self.id} - {self.name or 'Unnamed'}"
    
    class Meta:
        ordering = ['-created_at']

class AnonymousFaceVector(models.Model):
    """Anonim yüz vektörlerini saklayan model"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, blank=True)
    vector_data = models.BinaryField()
    vector_size = models.IntegerField()
    face_image_base64 = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(null=True, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)  # İsteğin geldiği IP adresi
    
    def __str__(self):
        return f"Anonymous Face Vector {self.id} - {self.name or 'Unnamed'}"
    
    class Meta:
        ordering = ['-created_at']


class Device(models.Model):
    """Raspberry Pi cihazları için model"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_online = models.DateTimeField(null=True, blank=True)
    api_key = models.CharField(max_length=64, unique=True)
    
    def __str__(self):
        return self.name


class Door(models.Model):
    """Basitleştirilmiş Kapı modeli"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)  # Kapı adı: "Ana Giriş", "Arka Kapı" vb.
    current_status = models.CharField(
        max_length=20,
        choices=[
            ('CLOSED', 'Kapalı'),
            ('OPEN', 'Açık'),
        ],
        default='CLOSED'
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.get_current_status_display()})"
    
    class Meta:
        ordering = ['name']


class AccessLog(models.Model):
    """Kapıya erişim denemelerini kaydeden model"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    door = models.ForeignKey(Door, on_delete=models.SET_NULL, null=True, blank=True)
    access_time = models.DateTimeField(default=timezone.now)
    was_successful = models.BooleanField(default=False)
    similarity_score = models.FloatField(null=True, blank=True)
    device_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # Eğer tanınmayan birisi kapıya erişmeye çalışırsa
    face_image = models.ImageField(upload_to='unknown_faces/', null=True, blank=True)
    
    def __str__(self):
        status = "Başarılı" if self.was_successful else "Başarısız"
        user_info = self.user.username if self.user else "Bilinmeyen Kişi"
        door_info = self.door.name if self.door else "Belirsiz Kapı"
        return f"{user_info} - {door_info} - {self.access_time} - {status}"
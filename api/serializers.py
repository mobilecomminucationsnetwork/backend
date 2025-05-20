from rest_framework import serializers
from .models import User, AccessLog, Device, Door
import numpy as np
import base64
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .models import FaceVector, AnonymousFaceVector
from PIL import Image
import io
import os
from django.conf import settings
import uuid

class FaceVectorSerializer(serializers.ModelSerializer):
    vector_data = serializers.ListField(child=serializers.FloatField(), write_only=True)
    face_image_base64 = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    class Meta:
        model = FaceVector
        fields = ['id', 'user', 'name', 'vector_data', 'vector_size', 'face_image_base64', 'created_at', 'is_active', 'metadata']
        read_only_fields = ['id', 'created_at', 'vector_size']
        extra_kwargs = {
            'user': {'required': False},
            'name': {'required': False},
            'metadata': {'required': False}
        }
    
    def validate_face_image_base64(self, value):
        """Base64 görsel verisini doğrula"""
        if value:
            # Base64 formatını kontrol et
            try:
                # "data:image/jpeg;base64," gibi bir önek varsa kaldır
                if ';base64,' in value:
                    value = value.split(';base64,')[1]
                
                # Base64 olarak decode etmeyi dene
                base64.b64decode(value)
            except Exception as e:
                raise serializers.ValidationError(f"Invalid base64 format: {str(e)}")
        return value
    
    def create(self, validated_data):
        # Vektör verisini al
        vector_list = validated_data.pop('vector_data', None)
        if not vector_list:
            raise serializers.ValidationError({"vector_data": "This field is required."})
        
        # Base64 görüntüsünü media klasörüne kaydet
        face_image_path = None
        if 'face_image_base64' in validated_data and validated_data['face_image_base64']:
            try:
                # Base64 görüntüsünü al
                face_image_base64 = validated_data['face_image_base64']
                
                # Base64'ü görüntüye dönüştür
                image_data = base64.b64decode(face_image_base64)
                image = Image.open(io.BytesIO(image_data))
                
                # Media klasörü ve yüz görüntüleri için alt klasör oluştur
                media_root = settings.MEDIA_ROOT
                face_images_dir = os.path.join(media_root, 'face_images')
                os.makedirs(face_images_dir, exist_ok=True)
                
                # Kullanıcı bazlı klasör oluştur (isteğe bağlı)
                user_id = validated_data.get('user', None)
                user_dir = os.path.join(face_images_dir, f"user_{user_id.id if user_id else 'anonymous'}")
                os.makedirs(user_dir, exist_ok=True)
                
                # Görüntü dosyası adı oluştur
                image_filename = f"face_{uuid.uuid4()}.jpg"
                image_path = os.path.join(user_dir, image_filename)
                
                # Görüntüyü kaydet
                image.save(image_path, format='JPEG', quality=95)
                
                # Relatif URL oluştur (MEDIA_URL + path)
                relative_path = os.path.join('face_images', f"user_{user_id.id if user_id else 'anonymous'}", image_filename)
                face_image_path = relative_path
                
                # Metadata'ya görüntü yolunu ekle
                if 'metadata' not in validated_data or validated_data['metadata'] is None:
                    validated_data['metadata'] = {}
                
                validated_data['metadata']['face_image_path'] = face_image_path
                validated_data['metadata']['face_image_url'] = os.path.join(settings.MEDIA_URL, relative_path.replace('\\', '/'))
                
                print(f"Face image saved to: {image_path}")
                
            except Exception as e:
                print(f"Error saving face image: {str(e)}")
                # Hata durumunda işlemi durdurmuyoruz, sadece logluyor ve devam ediyoruz
        
        try:
            # Listeden numpy dizisine dönüştürme
            vector_np = np.array(vector_list, dtype=np.float32)
            vector_size = len(vector_np)
            
            # Binary veriye dönüştür
            vector_bytes = vector_np.tobytes()
            
            # FaceVector modelini oluştur
            face_vector = FaceVector.objects.create(
                vector_data=vector_bytes,
                vector_size=vector_size,
                **validated_data
            )
            return face_vector
        except Exception as e:
            raise serializers.ValidationError({"vector_data": f"Invalid vector data format: {str(e)}"})

class FaceVectorResponseSerializer(serializers.ModelSerializer):
    """FaceVector yanıtı için serializer"""
    username = serializers.SerializerMethodField()
    vector_data = serializers.SerializerMethodField()
    
    class Meta:
        model = FaceVector
        fields = ['id', 'username', 'name', 'vector_data', 'vector_size', 'face_image_base64', 'created_at', 'is_active']
        
    def get_username(self, obj):
        if obj.user:
            return obj.user.username
        return None
    
    def get_vector_data(self, obj):
        """Binary vektör verisini NumPy dizisine ve sonra listeye dönüştür"""
        if obj.vector_data:
            # Binary veriden NumPy dizisine dönüştür
            vector_np = np.frombuffer(obj.vector_data, dtype=np.float32)
            # NumPy dizisini listeye dönüştür
            return vector_np.tolist()
        return None


class AnonymousFaceVectorSerializer(serializers.ModelSerializer):
    vector_data = serializers.ListField(child=serializers.FloatField(), write_only=True)
    face_image_base64 = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
    class Meta:
        model = AnonymousFaceVector
        fields = ['id', 'name', 'vector_data', 'vector_size', 'face_image_base64', 'created_at', 'is_active', 'metadata']
        read_only_fields = ['id', 'created_at', 'vector_size', 'source_ip']
        extra_kwargs = {
            'name': {'required': False},
            'metadata': {'required': False}
        }
    
    def validate_face_image_base64(self, value):
        """Base64 görsel verisini doğrula"""
        if value:
            # Base64 formatını kontrol et
            try:
                # "data:image/jpeg;base64," gibi bir önek varsa kaldır
                if ';base64,' in value:
                    value = value.split(';base64,')[1]
                
                # Base64 olarak decode etmeyi dene
                base64.b64decode(value)
            except Exception as e:
                raise serializers.ValidationError(f"Invalid base64 format: {str(e)}")
        return value
    
    def create(self, validated_data):
        # Vektör verisini al
        vector_list = validated_data.pop('vector_data', None)
        if not vector_list:
            raise serializers.ValidationError({"vector_data": "This field is required."})
        
        try:
            # Listeden numpy dizisine dönüştürme
            vector_np = np.array(vector_list, dtype=np.float32)
            vector_size = len(vector_np)
            
            # Binary veriye dönüştür
            vector_bytes = vector_np.tobytes()
            
            # IP adresini kaydet (eğer request mevcut ise)
            source_ip = None
            request = self.context.get('request')
            if request:
                source_ip = request.META.get('REMOTE_ADDR')
            
            # AnonymousFaceVector modelini oluştur
            face_vector = AnonymousFaceVector.objects.create(
                vector_data=vector_bytes,
                vector_size=vector_size,
                source_ip=source_ip,
                **validated_data
            )
            return face_vector
        except Exception as e:
            raise serializers.ValidationError({"vector_data": f"Invalid vector data format: {str(e)}"})

class AnonymousFaceVectorResponseSerializer(serializers.ModelSerializer):
    """AnonymousFaceVector yanıtı için serializer"""
    vector_data = serializers.SerializerMethodField()
    formatted_created_at = serializers.SerializerMethodField()
    formatted_updated_at = serializers.SerializerMethodField()
    
    class Meta:
        model = AnonymousFaceVector
        fields = ['id', 'name', 'vector_data', 'vector_size', 'face_image_base64', 
                 'created_at', 'updated_at', 'formatted_created_at', 'formatted_updated_at', 
                 'is_active', 'source_ip']
    
    def get_vector_data(self, obj):
        """Binary vektör verisini NumPy dizisine ve sonra listeye dönüştür"""
        if obj.vector_data:
            # Binary veriden NumPy dizisine dönüştür
            vector_np = np.frombuffer(obj.vector_data, dtype=np.float32)
            # NumPy dizisini listeye dönüştür
            return vector_np.tolist()
        return None
    
    def get_formatted_created_at(self, obj):
        """created_at zamanını okunabilir formatta döndür"""
        if obj.created_at:
            # İsteğe bağlı olarak format değiştirilebilir
            return obj.created_at.strftime("%Y-%m-%d %H:%M:%S")
        return None
    
    def get_formatted_updated_at(self, obj):
        """updated_at zamanını okunabilir formatta döndür"""
        if obj.updated_at:
            # İsteğe bağlı olarak format değiştirilebilir
            return obj.updated_at.strftime("%Y-%m-%d %H:%M:%S")
        return None

class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'password2', 
                  'first_name', 'last_name', 'phone_number')
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True}
        }
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Şifreler eşleşmiyor"})
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user

class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            
            if not user:
                raise serializers.ValidationError("Geçersiz kullanıcı adı veya şifre")
            
            if not user.is_active:
                raise serializers.ValidationError("Hesap devre dışı bırakılmış")
            
            # Token oluştur
            refresh = RefreshToken.for_user(user)
            
            return {
                'user': user,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        else:
            raise serializers.ValidationError("Kullanıcı adı ve şifre gereklidir")
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'email', 'first_name', 
                  'last_name', 'phone_number', 'is_face_registered')
        
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class FaceEmbeddingSerializer(serializers.Serializer):
    embedding = serializers.CharField()  # Base64 encoded numpy array
    
    def update(self, instance, validated_data):
        # Convert base64 string to numpy array, then to binary for storage
        embedding_base64 = validated_data.get('embedding')
        embedding_bytes = base64.b64decode(embedding_base64)
        
        # Save the binary data directly
        instance.face_embedding = embedding_bytes
        instance.is_face_registered = True
        instance.save()
        return instance


class DoorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Door
        fields = ['id', 'name', 'current_status', 'updated_at']
        read_only_fields = ['id', 'updated_at']


# AccessLogSerializer'ı güncelleyelim
class AccessLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    door_name = serializers.CharField(source='door.name', read_only=True)
    
    class Meta:
        model = AccessLog
        fields = (
            'id', 'username', 'user', 'door', 'door_name', 'access_time', 
            'was_successful', 'similarity_score', 'device_ip'
        )
        extra_kwargs = {
            'user': {'write_only': True},
            'door': {'write_only': True}
        }

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ('id', 'name', 'location', 'ip_address', 'is_active', 
                  'last_online', 'api_key')
        extra_kwargs = {
            'api_key': {'write_only': True}  # Don't expose API key in responses
        }
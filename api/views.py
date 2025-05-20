# Import'ları düzenlenmiş ve birleştirilmiş hali
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
import numpy as np
import base64
import uuid
from PIL import Image
import numpy as np
import base64
import io
import face_recognition
import cv2
import os
from django.conf import settings
import insightface
from insightface.app import FaceAnalysis

# Tüm serializer importları tek satırda
from .serializers import (
    UserSerializer, 
    FaceEmbeddingSerializer,
    AccessLogSerializer, 
    DeviceSerializer, 
    UserRegisterSerializer, 
    UserLoginSerializer,
    FaceVectorSerializer, 
    FaceVectorResponseSerializer, 
    AnonymousFaceVectorSerializer, 
    AnonymousFaceVectorResponseSerializer,
    DoorSerializer
)
# Hata veren Door modelini ekliyoruz
from .models import User, AccessLog, Device, FaceVector, AnonymousFaceVector, Door
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
import json
logger = logging.getLogger('django.request')
websocket_logger = logging.getLogger('websocket')

class AnonymousFaceVectorViewSet(viewsets.ModelViewSet):
    """
    Anonim yüz vektörlerini yönetmek için API endpoint
    """
    queryset = AnonymousFaceVector.objects.all()
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AnonymousFaceVectorSerializer
        return AnonymousFaceVectorResponseSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        face_vector = serializer.save()
        
        # Yanıt için response serializerı kullan
        response_serializer = AnonymousFaceVectorResponseSerializer(face_vector)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def find_similar(self, request):
        """
        Benzer anonim yüz vektörlerini bul
        """
        if 'vector_data' not in request.data:
            return Response({'error': 'vector_data field is required'}, 
                        status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Vektör listesini al
            vector_list = request.data['vector_data']
            if not isinstance(vector_list, list):
                return Response({'error': 'vector_data must be a list of floats'}, 
                            status=status.HTTP_400_BAD_REQUEST)
            
            # NumPy dizisine dönüştür
            query_vector = np.array(vector_list, dtype=np.float32)
            
            # Benzerlik eşiği (opsiyonel parametre)
            threshold = float(request.data.get('threshold', 0.6))
            
            # En fazla dönecek sonuç sayısı (opsiyonel parametre)
            max_results = int(request.data.get('max_results', 5))
            
            # Benzer vektörleri bul
            similar_vectors = []
            
            for face_vector in AnonymousFaceVector.objects.filter(is_active=True):
                db_vector = np.frombuffer(face_vector.vector_data, dtype=np.float32)
                
                # Vektör boyutları uyuşmazsa atla
                if len(db_vector) != len(query_vector):
                    continue
                
                # Kosinüs benzerliği hesapla
                similarity = np.dot(query_vector, db_vector) / (
                    np.linalg.norm(query_vector) * np.linalg.norm(db_vector)
                )
                
                if similarity >= threshold:
                    similar_vectors.append({
                        'face_vector': face_vector,
                        'similarity': float(similarity)
                    })
            
            # Benzerliğe göre sırala ve max_results kadar döndür
            similar_vectors.sort(key=lambda x: x['similarity'], reverse=True)
            similar_vectors = similar_vectors[:max_results]
            
            # Yanıt hazırla
            results = []
            for item in similar_vectors:
                vector_data = AnonymousFaceVectorResponseSerializer(item['face_vector']).data
                vector_data['similarity'] = item['similarity']
                results.append(vector_data)
                
            return Response(results)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class FaceVectorViewSet(viewsets.ModelViewSet):
    """
    Yüz vektörlerini yönetmek için API endpoint
    """
    queryset = FaceVector.objects.all()
    
    permission_classes = [permissions.AllowAny]
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FaceVectorSerializer
        return FaceVectorResponseSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        face_vector = serializer.save()
        
        # Yanıt için response serializerı kullan
        response_serializer = FaceVectorResponseSerializer(face_vector)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def store_anonymous(self, request):
        """
        Kimlik doğrulama olmadan yüz vektörü ve görsel kaydetme (anonim)
        """
        serializer = FaceVectorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        face_vector = serializer.save()
        
        response_serializer = FaceVectorResponseSerializer(face_vector)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def find_similar(self, request):
        """
        Benzer yüz vektörlerini bul
        """
        if 'vector_data' not in request.data:
            return Response({'error': 'vector_data field is required'}, 
                        status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Vektör listesini al
            vector_list = request.data['vector_data']
            if not isinstance(vector_list, list):
                return Response({'error': 'vector_data must be a list of floats'}, 
                            status=status.HTTP_400_BAD_REQUEST)
            
            # NumPy dizisine dönüştür
            query_vector = np.array(vector_list, dtype=np.float32)
            
            # Benzerlik eşiği (opsiyonel parametre)
            threshold = float(request.data.get('threshold', 0.6))
            
            # En fazla dönecek sonuç sayısı (opsiyonel parametre)
            max_results = int(request.data.get('max_results', 5))
            
            # Benzer vektörleri bul
            similar_vectors = []
            
            for face_vector in FaceVector.objects.filter(is_active=True):
                db_vector = np.frombuffer(face_vector.vector_data, dtype=np.float32)
                
                # Vektör boyutları uyuşmazsa atla
                if len(db_vector) != len(query_vector):
                    continue
                
                # Kosinüs benzerliği hesapla
                similarity = np.dot(query_vector, db_vector) / (
                    np.linalg.norm(query_vector) * np.linalg.norm(db_vector)
                )
                
                if similarity >= threshold:
                    similar_vectors.append({
                        'face_vector': face_vector,
                        'similarity': float(similarity)
                    })
            
            # Benzerliğe göre sırala ve max_results kadar döndür
            similar_vectors.sort(key=lambda x: x['similarity'], reverse=True)
            similar_vectors = similar_vectors[:max_results]
            
            # Yanıt hazırla
            results = []
            for item in similar_vectors:
                vector_data = FaceVectorResponseSerializer(item['face_vector']).data
                vector_data['similarity'] = item['similarity']
                results.append(vector_data)
                
            return Response(results)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class UserRegisterView(generics.GenericAPIView):
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                'user': UserSerializer(user, context=self.get_serializer_context()).data,
                'message': 'Kullanıcı başarıyla kaydedildi',
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            tokens = {
                'refresh': serializer.validated_data['refresh'],
                'access': serializer.validated_data['access']
            }
            return Response({
                'user': UserSerializer(user).data,
                'tokens': tokens,
                'message': 'Giriş başarılı'
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            # Token siyah listeye alınabilir, şu anda basit bir çıkış dönüyoruz
            return Response({'message': 'Başarıyla çıkış yapıldı'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class UserListCreateView(generics.ListCreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

class AccessLogListView(generics.ListAPIView):
    serializer_class = AccessLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = AccessLog.objects.all().order_by('-access_time')
        
        # Tarih filtreleme
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        user_id = self.request.query_params.get('user_id', None)
        success = self.request.query_params.get('success', None)
        
        if start_date:
            queryset = queryset.filter(access_time__gte=start_date)
        if end_date:
            queryset = queryset.filter(access_time__lte=end_date)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if success is not None:
            success_bool = success.lower() == 'true'
            queryset = queryset.filter(was_successful=success_bool)
            
        return queryset

class AccessLogDetailView(generics.RetrieveAPIView):
    queryset = AccessLog.objects.all()
    serializer_class = AccessLogSerializer
    permission_classes = [permissions.IsAuthenticated]

class DeviceListCreateView(generics.ListCreateAPIView):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

class DeviceDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

class DeviceHeartbeatView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, pk):
        device = get_object_or_404(Device, pk=pk)
        device.last_online = timezone.now()
        device.ip_address = request.META.get('REMOTE_ADDR')
        device.save()
        return Response({'status': 'heartbeat received'})

class FaceVerificationView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        if 'embedding' not in request.data:
            return Response({'error': 'No embedding provided'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        # Kapı ID'sini al (opsiyonel)
        door_id = request.data.get('door_id')
        door = None
        
        if door_id:
            try:
                door = Door.objects.get(id=door_id)
            except Door.DoesNotExist:
                return Response({'error': 'Kapı bulunamadı'}, status=status.HTTP_404_NOT_FOUND)
        
        # Base64 kodlu embedding'i numpy dizisine dönüştür
        embedding_base64 = request.data['embedding']
        embedding_bytes = base64.b64decode(embedding_base64)
        test_embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
        
        # En yüksek benzerlik skoruna sahip kullanıcıyı bul
        max_similarity = 0
        matched_user = None
        
        for user in User.objects.filter(is_face_registered=True):
            if user.face_embedding:
                # Veritabanından embedding'i al ve numpy dizisine dönüştür
                db_embedding = np.frombuffer(user.face_embedding, dtype=np.float32)
                
                # Kosinüs benzerliği hesapla
                similarity = np.dot(test_embedding, db_embedding) / (
                    np.linalg.norm(test_embedding) * np.linalg.norm(db_embedding)
                )
                
                if similarity > max_similarity:
                    max_similarity = similarity
                    matched_user = user
        
        # Erişim logu oluştur
        threshold = 0.5  # Benzerlik eşiği, ayarlanabilir
        success = max_similarity > threshold
        
        log = AccessLog.objects.create(
            user=matched_user if success else None,
            door=door,
            was_successful=success,
            similarity_score=float(max_similarity),
            device_ip=request.META.get('REMOTE_ADDR')
        )
        
        # Eğer başarılıysa ve kapı belirtilmişse, kapıyı aç
        if success and door:
            door.current_status = 'OPEN'
            door.save()
        
        if success:
            response_data = {
                'success': True,
                'user_id': matched_user.id,
                'username': matched_user.username,
                'similarity': float(max_similarity),
                'access_log_id': log.id
            }
            if door:
                response_data.update({
                    'door_id': door.id,
                    'door_name': door.name,
                    'door_status': door.current_status
                })
            return Response(response_data)
        else:
            response_data = {
                'success': False,
                'similarity': float(max_similarity),
                'access_log_id': log.id
            }
            if door:
                response_data.update({
                    'door_id': door.id,
                    'door_name': door.name
                })
            return Response(response_data, status=status.HTTP_401_UNAUTHORIZED)

class DoorViewSet(viewsets.ModelViewSet):
    """
    Kapı durumunu yönetmek için API endpoint
    """
    queryset = Door.objects.all()
    serializer_class = DoorSerializer
    permission_classes = [permissions.AllowAny]
    
    @action(detail=True, methods=['post'])
    def set_status(self, request, pk=None):
        """Kapı durumunu ayarla (açık/kapalı)"""
        door = self.get_object()
        
        # İstekten status değerini al
        status_value = request.data.get('status')
        
        # Loglama
        logger.info(f"Door status change requested: {door.id} -> {status_value}")
        
        if not status_value:
            logger.warning(f"Door status change failed: No status value provided for door {door.id}")
            return Response(
                {'error': 'status değeri belirtilmelidir'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Status değerini büyük harfe çevir ve kontrol et
        status_value = status_value.upper()
        
        if status_value not in ['OPEN', 'CLOSED']:
            logger.warning(f"Door status change failed: Invalid status {status_value} for door {door.id}")
            return Response(
                {'error': 'Geçersiz status değeri. OPEN veya CLOSED olmalıdır.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Komut ID ve zaman damgası oluştur
        command_id = str(uuid.uuid4())
        timestamp = timezone.now()
        
        # Kapı durumunu güncelle
        door.current_status = status_value
        door.updated_at = timestamp
        door.save()
        
        logger.info(f"Door {door.id} status updated in database: {status_value}")
        
        # WebSocket üzerinden cihaza komut gönder
        try:
            channel_layer = get_channel_layer()
            
            # WebSocket komutu bilgisini logla
            websocket_logger.info(f"Sending WebSocket command to door_{door.id}: {status_value}")
            
            command_payload = {
                "type": "door_command",
                "command": "set_status",
                "status": status_value,
                "door_id": str(door.id),
                "command_id": command_id,
                "timestamp": str(timestamp)
            }
            
            websocket_logger.debug(f"WebSocket command payload: {command_payload}")
            
            async_to_sync(channel_layer.group_send)(
                f"door_{door.id}",
                command_payload
            )
            
            websocket_logger.info(f"WebSocket command to door_{door.id} sent successfully")
            
        except ImportError:
            # Channels yüklü değilse, sadece log kaydı oluştur
            logger.warning(f"WebSocket notification skipped: Channels not installed")
        except Exception as e:
            # Diğer hatalar için de log kaydı oluştur
            error_msg = str(e)
            logger.error(f"WebSocket notification error: {error_msg}")
            websocket_logger.error(f"Failed to send command to door_{door.id}: {error_msg}")
        
        # Yanıt oluştur
        response_data = {
            'id': str(door.id),
            'name': door.name,
            'current_status': door.current_status,
            'updated_at': door.updated_at,
            'command_id': command_id
        }
        
        logger.info(f"Door status change completed for door {door.id}: {status_value}")
        
        return Response(response_data)

class OpenDoorsView(APIView):
    """
    Bir veya birden fazla kapıyı açmak için API endpoint
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        # İstekten kapı ID'lerini al
        door_ids = request.data.get('door_ids', [])
        
        if not door_ids:
            return Response({
                'error': "En az bir kapı ID'si belirtmelisiniz",
                'example': {
                    'door_ids': ['uuid1', 'uuid2']
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Komut ID ve zaman damgası oluştur
        command_id = str(uuid.uuid4())
        timestamp = timezone.now()
        
        # Sonuçları saklamak için liste
        results = []
        
        # Kapıları açma işlemini gerçekleştir
        for door_id in door_ids:
            try:
                door = Door.objects.get(id=door_id)
                
                # Kapı durumunu güncelle
                door.current_status = 'OPEN'
                door.updated_at = timestamp
                door.save()
                
                # WebSocket üzerinden kapı cihazına bildirim gönder
                try:
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"door_{door_id}",
                        {
                            "type": "door_command",
                            "command": "set_status",
                            "status": "OPEN",
                            "door_id": str(door.id),
                            "command_id": command_id,
                            "timestamp": str(timestamp)
                        }
                    )
                    
                    # WebSocket bildirimini logla
                    print(f"WebSocket bildirimi gönderildi: door_{door_id}")
                    
                except Exception as e:
                    print(f"WebSocket hata: {str(e)}")
                
                # Sonuçlara ekle
                results.append({
                    'door_id': str(door.id),
                    'name': door.name,
                    'status': door.current_status,
                    'success': True
                })
                
            except Door.DoesNotExist:
                results.append({
                    'door_id': door_id,
                    'success': False,
                    'error': 'Kapı bulunamadı'
                })
        
        # Sonuçları döndür
        return Response({
            'command_id': command_id,
            'timestamp': str(timestamp),
            'results': results
        })

class CloseDoorsView(APIView):
    """
    Bir veya birden fazla kapıyı kapatmak için API endpoint
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        # İstekten kapı ID'lerini al
        door_ids = request.data.get('door_ids', [])
        
        if not door_ids:
            return Response({
                'error': "En az bir kapı ID'si belirtmelisiniz",
                'example': {
                    'door_ids': ['uuid1', 'uuid2']
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Komut ID ve zaman damgası oluştur
        command_id = str(uuid.uuid4())
        timestamp = timezone.now()
        
        # Sonuçları saklamak için liste
        results = []
        
        # Kapıları kapama işlemini gerçekleştir
        for door_id in door_ids:
            try:
                door = Door.objects.get(id=door_id)
                
                # Kapı durumunu güncelle
                door.current_status = 'CLOSED'
                door.updated_at = timestamp
                door.save()
                
                # WebSocket üzerinden kapı cihazına bildirim gönder
                try:
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"door_{door_id}",
                        {
                            "type": "door_command",
                            "command": "set_status",
                            "status": "CLOSED",
                            "door_id": str(door.id),
                            "command_id": command_id,
                            "timestamp": str(timestamp)
                        }
                    )
                    
                    # WebSocket bildirimini logla
                    print(f"WebSocket bildirimi gönderildi: door_{door_id}")
                    
                except Exception as e:
                    print(f"WebSocket hata: {str(e)}")
                
                # Sonuçlara ekle
                results.append({
                    'door_id': str(door.id),
                    'name': door.name,
                    'status': door.current_status,
                    'success': True
                })
                
            except Door.DoesNotExist:
                results.append({
                    'door_id': door_id,
                    'success': False,
                    'error': 'Kapı bulunamadı'
                })
        
        # Sonuçları döndür
        return Response({
            'command_id': command_id,
            'timestamp': str(timestamp),
            'results': results
        })

class DoorControlView(APIView):

    """
    Kapıları WebSocket üzerinden kontrol etmek için API
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, action):
        if action not in ['open-doors', 'close-doors']:
            return Response({
                'error': 'Geçersiz eylem. "open-doors" veya "close-doors" kullanın.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # İstekten kapı ID'lerini al
        door_ids = request.data.get('door_ids', [])
        
        if not door_ids:
            return Response({
                'error': "En az bir kapı ID'si belirtmelisiniz",
                'example': {
                    'door_ids': ['uuid1', 'uuid2']
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Eylem türüne göre durumu belirle
        status_value = 'OPEN' if action == 'open-doors' else 'CLOSED'
        
        # Komut ID ve zaman damgası oluştur
        command_id = str(uuid.uuid4())
        timestamp = timezone.now()
        
        # Sonuçları saklamak için liste
        results = []
        
        # Channel layer al
        channel_layer = get_channel_layer()
        
        # Her kapı için WebSocket mesajı gönder
        for door_id in door_ids:
            try:
                # Kapının var olup olmadığını kontrol et
                door = Door.objects.get(id=door_id)
                
                # WebSocket üzerinden kapı cihazına komut gönder
                try:
                    async_to_sync(channel_layer.group_send)(
                        f"door_{door_id}",
                        {
                            "type": "door_command",
                            "command": "set_status",
                            "status": status_value,
                            "door_id": str(door.id),
                            "command_id": str(command_id),
                            "timestamp": str(timestamp)
                        }
                    )
                    
                    # Sonuçlara ekle
                    results.append({
                        'door_id': str(door.id),
                        'name': door.name,
                        'command_sent': True,
                        'message': f'WebSocket komutu gönderildi: {status_value}'
                    })
                    
                except Exception as e:
                    results.append({
                        'door_id': str(door.id),
                        'name': door.name,
                        'command_sent': False,
                        'error': f'WebSocket hatası: {str(e)}'
                    })
                
            except Door.DoesNotExist:
                results.append({
                    'door_id': door_id,
                    'command_sent': False,
                    'error': 'Kapı bulunamadı'
                })
        
        # Sonuçları döndür
        return Response({
            'command_id': str(command_id),
            'timestamp': str(timestamp),
            'action': action,
            'status': status_value,
            'results': results
        })


class UserRegisterFaceView(APIView):

    permission_classes = [permissions.IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Face Analysis modelini yükle
        try:
            # FaceAnalysis sınıfını oluştur ve yapılandır
            # SCRFD yüz dedektörü ve ArcFace MobileFaceNet kullanacak şekilde ayarla
            self.face_analyzer = FaceAnalysis(
                name='buffalo_l',  # SCRFD + ArcFace modeli
                providers=['CPUExecutionProvider'],  # CPU kullan
                allowed_modules=['detection', 'recognition']  # Tespit ve tanıma modülleri
            )
            # Modeli başlat ve yükle (640x640 boyutunda)
            self.face_analyzer.prepare(ctx_id=-1, det_size=(640, 640))
            print("SCRFD ve ArcFace modelleri başarıyla yüklendi")
        except Exception as e:
            print(f"Model yükleme hatası: {e}")
            self.face_analyzer = None
    
    def align_and_crop(self, img: np.ndarray, landmarks: list[list[float]], size: int = 112) -> np.ndarray:
        """
        Align and crop a face from img using 5-point landmarks.
        :param img: source image (H x W x C)
        :param landmarks: list of 5 [x,y] points
        :param size: output square size (pixels)
        :return: aligned, cropped image of shape (size, size, C)
        """
        # Reference points for a 112x112 face
        ref = np.array([
            [38.2946, 51.6963],
            [73.5318, 51.5014],
            [56.0252, 71.7366],
            [41.5493, 92.3655],
            [70.7299, 92.2041],
        ], dtype=np.float32) * (size / 112.0)
        pts = np.array(landmarks, dtype=np.float32)
        M, _ = cv2.estimateAffinePartial2D(pts, ref)
        aligned = cv2.warpAffine(img, M, (size, size), flags=cv2.INTER_LINEAR)
        return aligned
    
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        
        if not hasattr(self, 'face_analyzer') or self.face_analyzer is None:
            return Response({
                'error': 'Face analysis models could not be loaded'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        if 'face_image_base64' not in request.data:
            return Response({
                'error': 'face_image_base64 field is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Base64 verisini al
            face_image_base64 = request.data['face_image_base64']
            name = request.data.get('name', f"Face of {user.username}")
            
            # Expo ImageManipulator'dan gelen metadata'yı kaydet
            client_metadata = request.data.get('metadata', {})
            device_info = client_metadata.get('device_id', 'unknown')
            source_info = client_metadata.get('source', 'unknown')
            original_width = client_metadata.get('original_width', 0)
            original_height = client_metadata.get('original_height', 0)
            user_agent = client_metadata.get('user_agent', 'unknown')
            
            print(f"[DEBUG] Alınan görüntü: Kaynak={source_info}, Cihaz={device_info}, "
                  f"Orijinal Boyut={original_width}x{original_height}, User-Agent={user_agent}")
            
            # Base64 önekini kaldır
            if ';base64,' in face_image_base64:
                base64_data = face_image_base64.split(';base64,')[1]
            else:
                base64_data = face_image_base64
            
            # Base64'ü direkt olarak görüntü verisine dönüştür
            try:
                image_data = base64.b64decode(base64_data)
                image = Image.open(io.BytesIO(image_data)).convert('RGB')
                print(f"[DEBUG] Görüntü başarıyla yüklendi: {image.size}")
                
                # Görüntüyü media klasörüne kaydet
                file_ext = 'jpg'
                file_uuid = uuid.uuid4()
                media_dir = os.path.join(settings.MEDIA_ROOT, 'face_images')
                
                # Dizin yoksa oluştur
                os.makedirs(media_dir, exist_ok=True)
                
                # Dosya yolu oluştur
                file_name = f"user_{user.id}_face_{file_uuid}.{file_ext}"
                file_path = os.path.join(media_dir, file_name)
                
                # Görüntüyü kaydet
                image.save(file_path, format='JPEG', quality=95)
                print(f"[DEBUG] Görüntü kaydedildi: {file_path}")
                
                # Görüntü URL'si oluştur
                image_url = os.path.join(settings.MEDIA_URL, 'face_images', file_name)
                
            except Exception as img_error:
                print(f"[ERROR] Görüntü yükleme/kaydetme hatası: {img_error}")
                return Response({
                    'error': f'Image processing error: {str(img_error)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Eğer resim boyutu 640x640 değilse, yeniden boyutlandır
            img_np = np.array(image)
            if img_np.shape[0] != 640 or img_np.shape[1] != 640:
                img_np = cv2.resize(img_np, (640, 640))
                print(f"[DEBUG] Görüntü 640x640 boyutuna yeniden boyutlandırıldı")
            
            # SCRFD ile yüz tespiti ve yüz landmarkları
            faces = self.face_analyzer.get(img_np)
            
            if not faces:
                print("[ERROR] Görüntüde yüz tespit edilemedi!")
                return Response({
                    'error': 'No face detected in the image'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            print(f"[DEBUG] Tespit edilen yüz sayısı: {len(faces)}")
            
            # Yüzleri güven skoru (detection score) ve büyüklüğüne göre sırala
            faces.sort(key=lambda x: (x.det_score, (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1])), reverse=True)
            
            # İlk (en güvenilir/büyük) yüzü al
            best_face = faces[0]
            print(f"[DEBUG] Seçilen yüzün güven skoru: {best_face.det_score}")
            
            # Yüz koordinatları
            bbox = best_face.bbox.astype(int)
            x1, y1, x2, y2 = bbox
            bbox_list = [int(x1), int(y1), int(x2), int(y2)]
            print(f"[DEBUG] Yüz koordinatları (x1, y1, x2, y2): {bbox_list}")
            
            # Landmarkları al (5 nokta: sol göz, sağ göz, burun, sol ağız, sağ ağız)
            landmarks = best_face.landmark
            if landmarks is None or len(landmarks) == 0:
                # Eğer landmark yoksa, bbox'tan hesapla
                w, h = x2 - x1, y2 - y1
                landmarks = np.array([
                    [x1 + w * 0.3, y1 + h * 0.4],  # Sol göz
                    [x1 + w * 0.7, y1 + h * 0.4],  # Sağ göz 
                    [x1 + w * 0.5, y1 + h * 0.6],  # Burun
                    [x1 + w * 0.3, y1 + h * 0.8],  # Sol ağız köşesi
                    [x1 + w * 0.7, y1 + h * 0.8],  # Sağ ağız köşesi
                ])
                print("[DEBUG] Landmarklar bbox'tan hesaplandı")
            else:
                # Landmark formatı değişmiş olabilir, uyumlu hale getir
                landmarks = np.array(landmarks)
                if landmarks.shape != (5, 2):
                    landmarks = landmarks.reshape(5, 2)
                print("[DEBUG] Landmarklar modelden alındı")
            
            print(f"[DEBUG] Landmark koordinatları:\n{landmarks}")
            
            # Yüzü hizala ve kırp (112x112 boyut)
            aligned_face = self.align_and_crop(img_np, landmarks, size=112)
            print(f"[DEBUG] Yüz hizalama ve kırpma tamamlandı. Boyut: {aligned_face.shape}")
            
            # Tespit edilen ve hizalanan yüzü kaydet
            face_file_name = f"user_{user.id}_face_{file_uuid}_aligned.{file_ext}"
            face_file_path = os.path.join(media_dir, face_file_name)
            cv2.imwrite(face_file_path, cv2.cvtColor(aligned_face, cv2.COLOR_RGB2BGR))
            face_image_url = os.path.join(settings.MEDIA_URL, 'face_images', face_file_name)
            print(f"[DEBUG] Hizalanmış yüz kaydedildi: {face_file_path}")
            
            # Yüz tanıma ile vektörü çıkar (MobileFaceNet vektörü döndürür)
            # Hizalanmış yüzü 112x112'de işleyerek vektör çıkarabilirsiniz
            # Alternatif: aligned_face ile direkt vektör çıkarma işlemi yapabilirsiniz
            face_vector_np = best_face.embedding
            original_vector_size = len(face_vector_np)
            print(f"[DEBUG] Orijinal vektör boyutu: {original_vector_size}")
            
            # 512 boyutlu vektör için boyut ayarlaması
            if len(face_vector_np) != 512:
                if len(face_vector_np) > 512:
                    face_vector_np = face_vector_np[:512]  # İlk 512 değeri al
                    print(f"[DEBUG] Vektör 512 boyuta kırpıldı")
                else:
                    # Eksik boyutları sıfırla doldur
                    padding = np.zeros(512 - len(face_vector_np))
                    face_vector_np = np.concatenate([face_vector_np, padding])
                    print(f"[DEBUG] Vektör 512 boyuta genişletildi (sıfır dolgu)")
            
            # NORMALİZASYON KALDIRILDI - İSTEĞE GÖRE
            # Sadece vektör istatistiklerini yazdır
            print(f"[DEBUG] Vektör boyutu: {len(face_vector_np)}")
            print(f"[DEBUG] Vektör min: {np.min(face_vector_np)}, max: {np.max(face_vector_np)}")
            print(f"[DEBUG] Vektör ortalama: {np.mean(face_vector_np)}, std: {np.std(face_vector_np)}")
            print(f"[DEBUG] Vektör norm: {np.linalg.norm(face_vector_np)}")
            
            # TÜM VEKTÖRÜ YAZDIR
            print(f"[DEBUG] TÜM VEKTÖR: {face_vector_np.tolist()}")
            
            # FaceVectorSerializer'ın beklediği formatta veri oluştur
            vector_list = face_vector_np.tolist()  # Numpy dizisini Python listesine dönüştür
            vector_size = len(vector_list)
            
            # FaceVector modelini oluşturmak için serializer kullan
            from .serializers import FaceVectorSerializer
            
            # Mobil uygulama metadatasını metadata nesnesine dahil et
            combined_metadata = {
                'source': 'mobile_upload',
                'extractor': 'scrfd_mobilefacenet',
                'model_info': 'ArcFace MobileFaceNet 512-dim Vector',  # Vektör boyutunu belirt
                'source_ip': request.META.get('REMOTE_ADDR'),
                'image_dimensions': f"{image.size[0]}x{image.size[1]}",
                'image_path': file_path,
                'image_url': image_url,
                'face_image_url': face_image_url,
                'detection_score': float(best_face.det_score),
                'bbox': bbox_list,
                'landmarks': landmarks.tolist(),
                'vector_size': vector_size,
                'normalized': False,  # Normalizasyon durumunu belirt - normalize edilmemiş
                # Mobil uygulama metadata'sı
                'client_source': source_info,
                'device_id': device_info,
                'user_agent': user_agent,
                'original_dimensions': f"{original_width}x{original_height}",
                'has_local_backup': client_metadata.get('has_local_backup', False),
                'expo_compression': {
                    'width': 500,
                    'quality': 0.7,
                    'format': 'JPEG'
                }
            }
            
            serializer_data = {
                'user': user.id,
                'name': name,
                'vector_data': vector_list,  # Listeye dönüştürülmüş vektör
                'face_image_base64': base64_data,
                'is_active': True,
                'metadata': combined_metadata
            }
            
            serializer = FaceVectorSerializer(data=serializer_data)
            if not serializer.is_valid():
                print(f"[ERROR] Serializer hataları: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            face_vector = serializer.save()
            print(f"[DEBUG] Yüz vektörü başarıyla veritabanına kaydedildi. Vector ID: {face_vector.id}")
            
            # Kullanıcının yüz kaydı yapıldığını belirt
            user.is_face_registered = True
            user.save()
            print(f"[DEBUG] Kullanıcı {user.username} için yüz kaydı yapıldı")
            
            # Yanıt için response serializer kullan
            from .serializers import FaceVectorResponseSerializer
            response_serializer = FaceVectorResponseSerializer(face_vector)
            
            # API yanıtına sadece gerekli bilgileri ekle (debug bilgileri terminalde)
            response_data = response_serializer.data
            response_data.update({
                'success': True,
                'message': 'Face registered successfully',
                'image_url': image_url,
                'face_image_url': face_image_url
            })
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            import traceback
            print(f"[ERROR] İşlem sırasında hata oluştu:")
            traceback.print_exc()
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

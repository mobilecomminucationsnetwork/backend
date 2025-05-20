import json
import uuid
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone
from channels.db import database_sync_to_async
from .models import Door

# WebSocket logger
websocket_logger = logging.getLogger('websocket')

class DoorConsumer(AsyncWebsocketConsumer):
    # Bağlı request_id'leri ve kaynakları izlemek için sınıf değişkeni
    active_requests = {}  # {request_id: {'source_client_id': client_id, 'timestamp': timestamp}}
    
    async def connect(self):
        self.door_id = self.scope['url_route']['kwargs']['door_id']
        self.door_group_name = f'door_{self.door_id}'
        self.client_id = str(uuid.uuid4())[:8]  # Kısa bir ID
        
        # Bağlantı bilgilerini loglama
        client_info = self.scope['client']
        websocket_logger.info(f"Client [{self.client_id}] is connecting to door {self.door_id} from {client_info[0]}:{client_info[1]}")
        
        # Headers bilgilerini loglama
        headers = dict(self.scope['headers'])
        headers_str = '\n'.join([f"    {k.decode()}: {v.decode()}" for k, v in self.scope['headers']])
        websocket_logger.debug(f"Client [{self.client_id}] Headers:\n{headers_str}")
        
        # Kapı grubuna katıl
        await self.channel_layer.group_add(
            self.door_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Client türünü belirle (mobile veya raspberry)
        query_string = self.scope.get('query_string', b'').decode()
        params = dict(item.split('=') for item in query_string.split('&') if '=' in item)
        self.client_type = params.get('client_type', 'unknown')
        
        # Bağlantı başarılı mesajı
        connect_message = {
            'type': 'connection_established',
            'message': f'Kapı {self.door_id} için bağlantı kuruldu',
            'timestamp': str(timezone.now()),
            'client_id': self.client_id,
            'client_type': self.client_type
        }
        
        websocket_logger.info(f"Client [{self.client_id}] type [{self.client_type}] connected successfully to door {self.door_id}")
        await self.send(text_data=json.dumps(connect_message))
    
    async def disconnect(self, close_code):
        # Ayrılma bilgisini logla
        websocket_logger.info(f"Client [{self.client_id}] disconnected from door {self.door_id} with code {close_code}")
        
        # Kapı grubundan ayrıl
        await self.channel_layer.group_discard(
            self.door_group_name,
            self.channel_name
        )
        
        # Bu client'a ait aktif istekleri temizle
        for request_id in list(self.active_requests.keys()):
            if self.active_requests[request_id].get('source_client_id') == self.client_id:
                del self.active_requests[request_id]
                websocket_logger.info(f"Cleaned up request {request_id} for disconnected client [{self.client_id}]")
    
    # WebSocket'ten mesaj alma
    async def receive(self, text_data):
        try:
            # Alınan mesajı logla (base64 için çok uzun olacağından kısaltılabilir)
            if len(text_data) > 200:
                log_text = f"{text_data[:100]}...{text_data[-100:]}"
            else:
                log_text = text_data
                
            websocket_logger.info(f"Client [{self.client_id}] received message: {log_text}")
            
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            # face_registration_complete mesajını engelleme
            if message_type == 'face_registration_complete':
                websocket_logger.info(f"Received face_registration_complete message from client [{self.client_id}]")
                
                # İstemciye yanıt gönder
                response_message = {
                    'type': 'face_registration_response',
                    'success': True,
                    'timestamp': str(timezone.now())
                }
                
                await self.send(text_data=json.dumps(response_message))
                websocket_logger.info(f"Sent face_registration_response to client [{self.client_id}]")
                return
            
            if message_type == 'status_update':
                status = text_data_json.get('status')
                
                # İşlemi logla
                websocket_logger.info(f"Client [{self.client_id}] requested status update to {status} for door {self.door_id}")
                
                # Kapı durumunu güncelle
                update_result = await self.update_door_status(status)
                websocket_logger.info(f"Door {self.door_id} status update result: {update_result}")
                
                # Tüm istemcilere yayın yap
                await self.channel_layer.group_send(
                    self.door_group_name,
                    {
                        'type': 'door_status',
                        'status': status,
                        'client_id': self.client_id,
                        'timestamp': str(timezone.now())
                    }
                )
                websocket_logger.info(f"Status update {status} broadcasted to group {self.door_group_name}")
            
            

            elif message_type == 'face_recognition_request':
                # Yüz tanıma isteği (mobile client'tan gelir)
                face_image_base64 = text_data_json.get('face_image_base64')
                request_id = text_data_json.get('request_id', str(uuid.uuid4()))
                name = text_data_json.get('name')

                print("name: ")
                print(name)

                if not face_image_base64:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'face_image_base64 field is required',
                        'timestamp': str(timezone.now())
                    }))
                    return
                
                # Base64 önekini kaldır
                if ';base64,' in face_image_base64:
                    base64_data = face_image_base64.split(';base64,')[1]
                else:
                    base64_data = face_image_base64
                
                # İsteği aktif istekler listesine ekle
                self.active_requests[request_id] = {
                    'source_client_id': self.client_id,
                    'timestamp': str(timezone.now())
                }
                
                # Mesajı doğrudan bütün client'lara gönderir
                # Client türü filtresi olmadan
                await self.channel_layer.group_send(
                    self.door_group_name,
                    {
                        'type': 'broadcast_face',
                        'message_type': 'face_recognition_request',
                        'name':  name,
                        'face_image_base64': base64_data,
                        'request_id': request_id,
                        'source_client_id': self.client_id,
                        'timestamp': str(timezone.now())
                    }
                )
                
                websocket_logger.info(f"Face recognition request from client [{self.client_id}] broadcasted to group {self.door_group_name}")
                
                # İstenen face_recognition_result mesajını beklemeden direk yanıt döndür,
                # böylece client beklemeden devam edebilir ve bağlantıyı kapatabilir
                result_message = {
                    'type': 'face_recognition_result',
                    'result': 'in_progress',
                    'name':  name,
                    'request_id': request_id,
                    'timestamp': str(timezone.now()),
                    'message': 'Face recognition request is being processed'
                }
                
                await self.send(text_data=json.dumps(result_message))
                websocket_logger.info(f"Sent in_progress response for request {request_id} to client [{self.client_id}]")
            
            elif message_type == 'face_recognition_result':
                # Yüz tanıma sonucu (Raspberry Pi'den gelir)
                result = text_data_json.get('result')
                request_id = text_data_json.get('request_id')
                confidence = text_data_json.get('confidence', 0)
                
                # Bu sonucun kaynak isteğiyle ilişkilendirilmiş olduğunu kontrol et
                request_source = None
                if request_id in self.active_requests:
                    request_source = self.active_requests[request_id].get('source_client_id')
                    # İsteği işledikten sonra listeden kaldır
                    del self.active_requests[request_id]
                
                # Mesajı doğrudan bütün client'lara gönderir
                # Client türü filtresi olmadan
                await self.channel_layer.group_send(
                    self.door_group_name,
                    {
                        'type': 'broadcast_face',
                        'message_type': 'face_recognition_result',
                        'result': result,
                        'request_id': request_id,
                        'confidence': confidence,
                        'source_client_id': self.client_id,
                        'original_source_client_id': request_source,
                        'timestamp': str(timezone.now())
                    }
                )
                
                websocket_logger.info(f"Face recognition result from client [{self.client_id}]: {result}")

            elif message_type == 'face_vector_delete':
                # Silinecek yüz vektörünün name'ini kontrol et
                vector_name = text_data_json.get('name')
                
                if not vector_name:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'name field is required',
                        'timestamp': str(timezone.now())
                    }))
                    return
                
                # İşlemi logla
                websocket_logger.info(f"Client [{self.client_id}] requested to delete face vector with name '{vector_name}'")
                
                # FaceVector silme işlemini async olarak çağır
                delete_result = await self.delete_face_vector_by_name(vector_name)
                websocket_logger.info(f"Face vector delete by name result: {delete_result}")
                
                # Silinen vektörlerin ID'lerini al
                deleted_vector_ids = delete_result.get('deleted_ids', [])
                
                # Tüm istemcilere her silinen vektör için ayrı ayrı yayın yap
                for vector_id in deleted_vector_ids:
                    await self.channel_layer.group_send(
                        self.door_group_name,
                        {
                            'type': 'face_vector_deleted',
                            'vector_id': vector_id,
                            'vector_name': vector_name,
                            'success': delete_result.get('success', False),
                            'client_id': self.client_id,
                            'timestamp': str(timezone.now())
                        }
                    )
                
                # İşlem sonucunu istemciye bildir
                await self.send(text_data=json.dumps({
                    'type': 'face_vector_delete_by_name_result',
                    'vector_name': vector_name,
                    'success': delete_result.get('success', False),
                    'message': delete_result.get('message', ''),
                    'deleted_count': delete_result.get('deleted_count', 0),
                    'deleted_ids': deleted_vector_ids,
                    'timestamp': str(timezone.now())
                }))
                
                websocket_logger.info(f"Face vector delete by name notification broadcasted to group {self.door_group_name}")

            elif message_type == 'heartbeat':
                # Heartbeat yanıtı
                websocket_logger.debug(f"Client [{self.client_id}] sent heartbeat")
                
                heartbeat_response = {
                    'type': 'heartbeat_response',
                    'timestamp': str(timezone.now()),
                    'client_id': self.client_id
                }
                
                await self.send(text_data=json.dumps(heartbeat_response))
                websocket_logger.debug(f"Heartbeat response sent to client [{self.client_id}]")
            
        except json.JSONDecodeError:
            error_msg = "Geçersiz JSON formatı"
            websocket_logger.error(f"Client [{self.client_id}] sent invalid JSON: {text_data[:100]}")
            
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': error_msg,
                'timestamp': str(timezone.now())
            }))
        except Exception as e:
            error_msg = str(e)
            websocket_logger.error(f"Client [{self.client_id}] error processing message: {error_msg}")
            
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': error_msg,
                'timestamp': str(timezone.now())
            }))
    
    # Kapı durum mesajını alındığında çağrılır - mevcut kodu koruyoruz
    async def door_status(self, event):
        status = event.get('status')
        timestamp = event.get('timestamp')
        source_client = event.get('client_id')
        
        # Mesajı logla
        websocket_logger.info(f"Door status event received: door {self.door_id} -> {status}")
        
        # Bu mesaj kendinden geliyorsa tekrar aynı istemciye gönderme
        if source_client == self.client_id:
            websocket_logger.debug(f"Skipping door status message for originating client [{self.client_id}]")
            return
        
        # WebSocket'e mesaj gönder
        message = {
            'type': 'door_status',
            'status': status,
            'timestamp': timestamp
        }
        
        await self.send(text_data=json.dumps(message))
        websocket_logger.info(f"Door status message sent to client [{self.client_id}]")
    
    # Yüz tanıma mesajları için yeni broadcast handler
    async def broadcast_face(self, event):
        source_client_id = event.get('source_client_id')
        
        # Bu mesaj kendinden geliyorsa tekrar aynı istemciye gönderme
        if source_client_id == self.client_id:
            websocket_logger.debug(f"Skipping face message for originating client [{self.client_id}]")
            return
        
        # Event'ten mesaj tipini al ve uygun mesajı oluştur
        message_type = event.get('message_type')
        
        if message_type == 'face_recognition_request':
            # Face recognition isteği oluştur
            message = {
                'type': 'face_recognition_request',
                'face_image_base64': event.get('face_image_base64'),
                'name': event.get('name'),
                'request_id': event.get('request_id'),
                'timestamp': event.get('timestamp')
            }
        elif message_type == 'face_recognition_result':
            # İstek sahibini kontrol et
            original_source = event.get('original_source_client_id')
            
            # Eğer bu client orijinal isteği gönderen değilse, sonucu gönderme
            # Zaten mobile client'a in_progress yanıtı gönderildi
            if original_source and original_source != self.client_id:
                websocket_logger.debug(f"Skipping result for request not initiated by client [{self.client_id}]")
                return
                
            # Face recognition sonucu oluştur
            message = {
                'type': 'face_recognition_result',
                'result': event.get('result'),
                
                'request_id': event.get('request_id'),
                'confidence': event.get('confidence'),
                'timestamp': event.get('timestamp')
            }
        else:
            # Bilinmeyen mesaj tipi
            websocket_logger.warning(f"Unknown face message type: {message_type}")
            return
        
        # WebSocket'e mesaj gönder
        await self.send(text_data=json.dumps(message))
        websocket_logger.info(f"Face {message_type} message sent to client [{self.client_id}]")
    
    async def face_vector_deleted(self, event):
        vector_id = event.get('vector_id')
        vector_name = event.get('vector_name', '')  # İsim bilgisini ekle
        success = event.get('success')
        timestamp = event.get('timestamp')
        source_client = event.get('client_id')
        
        # Mesajı logla
        websocket_logger.info(f"Face vector deleted event received: vector ID {vector_id}, name '{vector_name}', success: {success}")
        
        # Bu mesaj kendinden geliyorsa tekrar aynı istemciye gönderme
        if source_client == self.client_id:
            websocket_logger.debug(f"Skipping face vector deleted message for originating client [{self.client_id}]")
            return
        
        # WebSocket'e mesaj gönder
        message = {
            'type': 'face_vector_deleted',
            'vector_id': vector_id,
            'name': vector_name,  # İsim bilgisini ekle
            'success': success,
            'timestamp': timestamp
        }
        
        await self.send(text_data=json.dumps(message))
        websocket_logger.info(f"Face vector deleted message sent to client [{self.client_id}]")

    # Kapı komutları (door_command) mesaj tipi için handler ekliyoruz
    async def door_command(self, event):
        # Mesajı logla
        command = event.get('command', 'unknown')
        websocket_logger.info(f"Door command event received: {command}")
        
        # Mesajı olduğu gibi istemciye gönder
        await self.send(text_data=json.dumps(event))
        websocket_logger.info(f"Door command sent to client [{self.client_id}]")
    
    

    @database_sync_to_async
    def update_door_status(self, status):
        try:
            door = Door.objects.get(id=self.door_id)
            door.current_status = status
            door.updated_at = timezone.now()
            door.save()
            return {"success": True, "door_id": str(self.door_id), "status": status}
        except Door.DoesNotExist:
            return {"success": False, "error": "Door not found", "door_id": str(self.door_id)}
        except Exception as e:
            return {"success": False, "error": str(e), "door_id": str(self.door_id)}



    @database_sync_to_async
    def delete_face_vector_by_name(self, name):
        try:
            # Hem FaceVector hem de AnonymousFaceVector modellerinde arama yap
            from .models import FaceVector, AnonymousFaceVector
            
            deleted_count = 0
            deleted_ids = []
            
            # Normal FaceVector'lerde ara ve sil
            try:
                face_vectors = FaceVector.objects.filter(name=name)
                if face_vectors.exists():
                    # Silmeden önce ID'leri kaydet
                    for fv in face_vectors:
                        deleted_ids.append(str(fv.id))
                    
                    count = face_vectors.count()
                    face_vectors.delete()
                    deleted_count += count
            except Exception as e:
                return {
                    "success": False, 
                    "message": f"Error deleting FaceVectors: {str(e)}", 
                    "name": name
                }
            
            # AnonymousFaceVector'lerde ara ve sil
            try:
                anon_vectors = AnonymousFaceVector.objects.filter(name=name)
                if anon_vectors.exists():
                    # Silmeden önce ID'leri kaydet
                    for av in anon_vectors:
                        deleted_ids.append(str(av.id))
                    
                    count = anon_vectors.count()
                    anon_vectors.delete()
                    deleted_count += count
            except Exception as e:
                return {
                    "success": False, 
                    "message": f"Error deleting AnonymousFaceVectors: {str(e)}", 
                    "name": name
                }
            
            if deleted_count > 0:
                return {
                    "success": True, 
                    "message": f"Deleted {deleted_count} face vectors with name '{name}'", 
                    "name": name,
                    "deleted_count": deleted_count,
                    "deleted_ids": deleted_ids
                }
            else:
                return {
                    "success": False, 
                    "message": f"No face vectors found with name '{name}'", 
                    "name": name,
                    "deleted_count": 0,
                    "deleted_ids": []
                }
        except Exception as e:
            return {
                "success": False, 
                "message": str(e), 
                "name": name,
                "deleted_count": 0,
                "deleted_ids": []
            }
# backend/websocket.py
import asyncio
import websockets
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

class DoorCommandConsumer(AsyncWebsocketConsumer):
    door_clients = {}  # door_id -> set of client connections
    
    async def connect(self):
        # Bağlantı isteğini kabul et
        await self.accept()
        
        # Bağlantı parametrelerini al
        query_string = self.scope['query_string'].decode()
        params = dict(item.split('=') for item in query_string.split('&') if '=' in item)
        
        # Kapı ID'sini al
        self.door_id = params.get('door_id')
        self.client_type = params.get('client_type', 'device')  # 'device' veya 'app'
        
        if not self.door_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'door_id parametresi gerekli'
            }))
            await self.close()
            return
        
        # Kapı ID'si için istemci kaydet
        if self.door_id not in self.door_clients:
            self.door_clients[self.door_id] = set()
        
        self.door_clients[self.door_id].add(self)
        
        # Raspberry Pi cihazına hoş geldin mesajı
        if self.client_type == 'device':
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': f'Kapı {self.door_id} için bağlantı kuruldu'
            }))

    async def disconnect(self, close_code):
        # İstemci kaldırıldı
        if hasattr(self, 'door_id') and self.door_id in self.door_clients:
            self.door_clients[self.door_id].remove(self)
            
            # Eğer kapı için başka istemci kalmadıysa, kapıyı temizle
            if not self.door_clients[self.door_id]:
                del self.door_clients[self.door_id]

    async def receive(self, text_data):
        data = json.loads(text_data)
        command_type = data.get('type')
        
        if command_type == 'status_update':
            # Raspberry Pi'den durumu güncellemesi alındı
            door_id = data.get('door_id')
            status = data.get('status')
            
            # Kapı durumunu veritabanında güncelle
            from api.models import Door
            door = Door.objects.get(id=door_id)
            door.current_status = status
            door.save()
            
            # Diğer istemcileri bilgilendir (mobil uygulamalar)
            await self.notify_clients(door_id, {
                'type': 'door_status_changed',
                'door_id': door_id,
                'status': status,
                'timestamp': str(door.updated_at)
            }, exclude=[self])
        
        elif command_type == 'heartbeat':
            # Cihaz ile backend arasında bağlantı kontrolü
            await self.send(text_data=json.dumps({
                'type': 'heartbeat_response',
                'timestamp': str(datetime.now())
            }))
    
    @classmethod
    async def send_door_command(cls, door_id, command):
        """Backend'den kapı cihazına komut gönder"""
        if door_id not in cls.door_clients:
            return False
        
        # Kapıya bağlı tüm cihazlara komut gönder
        device_clients = [client for client in cls.door_clients[door_id] 
                         if getattr(client, 'client_type', '') == 'device']
        
        if not device_clients:
            return False
        
        # Komut gönder
        for client in device_clients:
            await client.send(text_data=json.dumps(command))
        
        return True
    
    @classmethod
    async def notify_clients(cls, door_id, message, exclude=None):
        """Kapı ile ilgili tüm istemcilere bildirim gönder"""
        if door_id not in cls.door_clients:
            return
        
        exclude = exclude or []
        
        for client in cls.door_clients[door_id]:
            if client not in exclude:
                await client.send(text_data=json.dumps(message))
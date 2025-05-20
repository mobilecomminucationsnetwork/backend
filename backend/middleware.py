# backend/middleware.py
import logging
import time
import uuid
import json

logger = logging.getLogger('django.request')
websocket_logger = logging.getLogger('websocket')

class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Benzersiz istek ID'si
        request_id = str(uuid.uuid4())
        request.id = request_id
        
        # Başlangıç zamanı
        start_time = time.time()
        
        # İstek bilgilerini detaylı loglama
        headers = '\n'.join([f'    {key}: {value}' for key, value in request.headers.items()])
        body = ''
        
        if request.body:
            try:
                body = request.body.decode('utf-8')
            except UnicodeDecodeError:
                body = str(request.body)
            
            # JSON body ise daha okunabilir hale getir
            if 'application/json' in request.headers.get('Content-Type', ''):
                try:
                    json_body = json.loads(body)
                    body = json.dumps(json_body, indent=4)
                except json.JSONDecodeError:
                    pass
        
        request_log = f"""
======== REQUEST [{request_id}] ========
PATH: {request.path}
METHOD: {request.method}
CLIENT: {request.META.get('REMOTE_ADDR')}:{request.META.get('REMOTE_PORT', '')}
GET PARAMS: {request.GET}
POST PARAMS: {request.POST}
BODY: 
{body}
HEADERS: 
{headers}
======== END REQUEST [{request_id}] ========
        """
        logger.debug(request_log)
        
        # Response alınması
        response = self.get_response(request)
        
        # Bitiş zamanı ve süre hesaplama
        end_time = time.time()
        duration = end_time - start_time
        
        # Response detaylarını loglama
        response_headers = '\n'.join([f'    {key}: {value}' for key, value in response.items()])
        
        response_body = ''
        if hasattr(response, 'content'):
            try:
                response_body = response.content.decode('utf-8')
                
                # JSON response ise daha okunabilir hale getir
                if 'application/json' in response.get('Content-Type', ''):
                    try:
                        json_body = json.loads(response_body)
                        response_body = json.dumps(json_body, indent=4)
                    except json.JSONDecodeError:
                        pass
            except:
                response_body = "Binary content"
        
        response_log = f"""
======== RESPONSE [{request_id}] ========
STATUS: {response.status_code}
DURATION: {duration:.3f}s
HEADERS: 
{response_headers}
CONTENT: 
{response_body[:2000]}{"..." if len(response_body) > 2000 else ""}
======== END RESPONSE [{request_id}] ========
        """
        logger.debug(response_log)
        
        return response
from django.urls import path
from . import views

urlpatterns = [
     # Mevcut URL'ler
     path('api/users/', views.UserListCreateView.as_view(), name='user-list'),
     path('api/users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
     path('api/users/<int:pk>/register-face/', views.UserRegisterFaceView.as_view(), name='user-register-face'),
     
     # Yeni eklenen kimlik doğrulama URL'leri
     path('api/auth/register/', views.UserRegisterView.as_view(), name='user-register'),
     path('api/auth/login/', views.UserLoginView.as_view(), name='user-login'),
     path('api/auth/logout/', views.UserLogoutView.as_view(), name='user-logout'),
     
     # Diğer URL'ler
     path('api/face/verify/', views.FaceVerificationView.as_view(), name='face-verify'),
     
     path('api/access-logs/', views.AccessLogListView.as_view(), name='access-log-list'),
     path('api/access-logs/<uuid:pk>/', views.AccessLogDetailView.as_view(), name='access-log-detail'),
     
     path('api/devices/', views.DeviceListCreateView.as_view(), name='device-list'),
     path('api/devices/<uuid:pk>/', views.DeviceDetailView.as_view(), name='device-detail'),
     path('api/devices/<uuid:pk>/heartbeat/', views.DeviceHeartbeatView.as_view(), name='device-heartbeat'),

     path('api/face-vectors/store-anonymous/', 
          views.FaceVectorViewSet.as_view({'post': 'store_anonymous'}),
          name='face-vector-store-anonymous'),
     
     # Benzer yüz vektörlerini bulma endpoint'i
     path('api/face-vectors/find-similar/',
          views.FaceVectorViewSet.as_view({'post': 'find_similar'}),
          name='face-vector-find-similar'),
     
     # Sonra genel CRUD URL'leri
     path('api/face-vectors/', views.FaceVectorViewSet.as_view({
          'get': 'list',
          'post': 'create'
     }), name='face-vector-list'),
     
     path('api/face-vectors/<uuid:pk>/', views.FaceVectorViewSet.as_view({
          'get': 'retrieve',
          'put': 'update',
          'patch': 'partial_update',
          'delete': 'destroy'
     }), name='face-vector-detail'),

     
     # Yeni endpoint: Anonim yüz vektörleri için
     path('api/anonymous-face-vectors/', 
          views.AnonymousFaceVectorViewSet.as_view({'get': 'list', 'post': 'create'}),
          name='anonymous-face-vector-list'),
     
     path('api/anonymous-face-vectors/<uuid:pk>/', 
          views.AnonymousFaceVectorViewSet.as_view({
               'get': 'retrieve', 
               'put': 'update', 
               'patch': 'partial_update', 
               'delete': 'destroy'
          }),
          name='anonymous-face-vector-detail'),
     
     path('api/anonymous-face-vectors/find-similar/',
          views.AnonymousFaceVectorViewSet.as_view({'post': 'find_similar'}),
          name='anonymous-face-vector-find-similar'),
     
     # Eski store_anonymous endpoint'ini koruyun (geriye dönük uyumluluk için)
     path('api/face-vectors/store-anonymous/',
          views.FaceVectorViewSet.as_view({'post': 'store_anonymous'}),
          name='face-vector-store-anonymous'),

     
     #Door endpoints
     path('api/doors/', 
          views.DoorViewSet.as_view({'get': 'list', 'post': 'create'}),
          name='door-list'),

     path('api/doors/<uuid:pk>/', 
          views.DoorViewSet.as_view({
          'get': 'retrieve', 
          'put': 'update', 
          'delete': 'destroy'
          }),
          name='door-detail'),

     path('api/doors/<uuid:pk>/set-status/', 
          views.DoorViewSet.as_view({'post': 'set_status'}),
          name='door-set-status'),
     
     path('api/doors/open-doors/', views.OpenDoorsView.as_view(), name='open-doors'),
     path('api/doors/close-doors/', views.CloseDoorsView.as_view(), name='close-doors'),
    
     # Yüz doğrulama endpoint'i (door_id desteğiyle güncellendi)
     path('api/face/verify/', views.FaceVerificationView.as_view(), name='face-verify'),

     path('api/doors/<str:action>/', views.DoorControlView.as_view(), name='door-control'),


]
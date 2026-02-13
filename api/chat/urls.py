from django.urls import path
from chat import views

urlpatterns = [
    path('conversation/', views.chat, name='chat'),
    path('conversations/', views.conversation_list, name='conversation-list'),
    path('conversations/messages/', views.conversation_messages, name='conversation-messages'),
]

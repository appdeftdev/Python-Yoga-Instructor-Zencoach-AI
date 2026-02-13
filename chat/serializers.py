from rest_framework import serializers
from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for Message model"""
    
    class Meta:
        model = Message
        fields = ['id', 'message_type', 'content', 'created_at', 'query_sent_at', 'audio','audio_metadata', 'response_received_at']
        read_only_fields = ['id', 'created_at', 'query_sent_at', 'response_received_at']


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for Conversation model"""
    messages = MessageSerializer(many=True, read_only=True)
    message_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'topic', 'status', 'openai_conversation_id', 'audio', 'audio_metadata',
            'is_active', 'started_at', 'last_message_at', 'ended_at',
            'messages', 'message_count'
        ]
        read_only_fields = [
            'id', 'openai_conversation_id', 'started_at', 
            'last_message_at', 'ended_at', 'messages', 'message_count'
        ]


class ChatRequestSerializer(serializers.Serializer):
    """Serializer for chat API request"""
    message = serializers.CharField(
        max_length=2000,
        required=False, 
        allow_blank=True,
        help_text="User message to send to the bot"
    )
    conversation_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID of existing conversation to continue, or null for new conversation"
    )
    audio = serializers.FileField(
        required=False,
        help_text="Voice input audio file"
    )

    audio_metadata = serializers.JSONField(
        required=False,
        help_text="Audio metadata like duration, format, language"
    )

class ChatResponseSerializer(serializers.Serializer):
    """Serializer for chat API response"""
    conversation_id = serializers.IntegerField()
    bot_message = serializers.CharField()
    message_id = serializers.IntegerField()
    is_new_conversation = serializers.BooleanField()
    openai_conversation_id = serializers.CharField(allow_null=True)
    query_sent_at = serializers.DateTimeField()
    response_received_at = serializers.DateTimeField()
    
    def to_representation(self, instance):
        """Override to format timestamps as HH:MM"""
        data = super().to_representation(instance)
        
        # Format timestamps to HH:MM
        if data.get('query_sent_at'):
            data['query_sent_at'] = instance['query_sent_at'].strftime('%H:%M')
        if data.get('response_received_at'):
            data['response_received_at'] = instance['response_received_at'].strftime('%H:%M')
            
        return data


class ConversationListSerializer(serializers.ModelSerializer):
    """Serializer for conversation list API - returns only conversation_id and topic"""
    
    class Meta:
        model = Conversation
        fields = ['id', 'topic']
        read_only_fields = ['id', 'topic']


class ConversationMessagesRequestSerializer(serializers.Serializer):
    """Serializer for conversation messages API request"""
    conversation_id = serializers.IntegerField(
        help_text="ID of the conversation to get messages for"
    )


class ConversationMessagesSerializer(serializers.ModelSerializer):
    """Serializer for conversation messages API"""
    
    class Meta:
        model = Message
        fields = ['id', 'message_type', 'content','audio', 'audio_metadata', 'created_at', 'query_sent_at', 'response_received_at']
        read_only_fields = ['id', 'created_at', 'query_sent_at', 'response_received_at']

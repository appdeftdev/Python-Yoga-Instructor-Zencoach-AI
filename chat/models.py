from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class Conversation(models.Model):
    """Parent model for chat conversations"""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='conversations',
        help_text="User who owns this conversation"
    )
    topic = models.CharField(
        max_length=100,
        blank=True,
        help_text="Topic or theme of this conversation"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        help_text="Current status of the conversation"
    )

    openai_conversation_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="OpenAI conversation/thread ID for context"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this conversation is currently active"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'conversation'
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'
        ordering = ['-last_message_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['started_at']),
            models.Index(fields=['last_message_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.topic or 'General'} ({self.get_status_display()})"
    
    @property
    def message_count(self):
        """Get total number of messages in this conversation"""
        return self.messages.count()
    
    @property
    def duration(self):
        """Get conversation duration"""
        if self.ended_at:
            return self.ended_at - self.started_at
        return timezone.now() - self.started_at


class Message(models.Model):
    """Sub-class of Conversation - represents individual messages within a conversation"""
    
    MESSAGE_TYPES = [
        ('user', 'User Message'),
        ('bot', 'Bot Response'),
        ('system', 'System Message'),
    ]
    
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
        help_text="Conversation this message belongs to"
    )
    message_type = models.CharField(
        max_length=10,
        choices=MESSAGE_TYPES,
        help_text="Type of message (user, bot, or system)"
    )
    content = models.TextField(
        help_text="The actual message content"
    )
    audio = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Audio file path or URL"
    )
    audio_metadata = models.JSONField(
        blank=True,
        null=True,
        help_text="Audio metadata like duration, format, size, language"
    )
    query_sent_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Timestamp when user query was sent"
    )
    response_received_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Timestamp when AI response was received"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'message'
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['message_type']),
        ]
    
    def __str__(self):
        return f"{self.get_message_type_display()} - {self.content[:50]}..."

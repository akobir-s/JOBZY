import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model

from .models import Message

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """Private chat over `ws/chat/<room_name>/`.

    Room names are of the form `<username_a>__<username_b>`; a client may only
    join a room whose name contains their own username.
    """

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'
        self.user = self.scope['user']

        if not self.user.is_authenticated or not self.can_join_room():
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    def can_join_room(self):
        participants = self.room_name.split('__')
        return self.user.username in participants

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    @database_sync_to_async
    def _save_message(self, recipient_username, content):
        recipient = User.objects.get(username=recipient_username)
        Message.objects.create(sender=self.user, recipient=recipient, content=content)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({'error': 'Invalid JSON payload'}))
            return

        content = (data.get('message') or '').strip()
        recipient_username = (data.get('receiver') or '').strip()

        if not content or not recipient_username:
            await self.send(text_data=json.dumps(
                {'error': "Both 'message' and 'receiver' are required"}))
            return
        if recipient_username not in self.room_name.split('__'):
            await self.send(text_data=json.dumps(
                {'error': 'Receiver is not a participant of this room'}))
            return

        try:
            await self._save_message(recipient_username, content)
        except User.DoesNotExist:
            await self.send(text_data=json.dumps({'error': 'Receiver not found'}))
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': content,
                'sender': self.user.username,
                'receiver': recipient_username,
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event.get('message', ''),
            'sender': event.get('sender', ''),
            'receiver': event.get('receiver', ''),
        }))

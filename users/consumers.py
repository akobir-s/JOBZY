import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from .models import Message  

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'
        self.user = self.scope['user']  # Get the authenticated user

        # Check if user is authenticated
        if not self.user.is_authenticated:
            await self.close()
            return

        # Add permission check (customize this based on your app)
        # Example: room_name could be "user1_user2" for private chats
        if not self.can_join_room():
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    def can_join_room(self):
        # Example logic: room_name like "user1_user2" for private chats
        users = self.room_name.split('_')
        return self.user.username in users  # Only allow users in the room name

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data.get('message', '')
            sender = self.user.username  # Use the authenticated user
            receiver = data.get('receiver', '')

            # Save to database
            receiver_user = User.objects.get(username=receiver)
            Message.objects.create(
                sender=self.user,
                recipient=receiver_user,
                content=message,
                # Add booking if your app uses it
            )

            # Broadcast to the group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender': sender,
                    'receiver': receiver,
                }
            )
        except User.DoesNotExist:
            await self.send(text_data=json.dumps({'error': 'Receiver not found'}))
        except Exception as e:
            print(f"Error in receive: {str(e)}")
            await self.send(text_data=json.dumps({'error': 'Something went wrong'}))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event.get('message', ''),
            'sender': event.get('sender', ''),
            'receiver': event.get('receiver', ''),
        }))
        
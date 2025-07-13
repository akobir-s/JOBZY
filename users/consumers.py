import json
from channels.generic.websocket import AsyncWebsocketConsumer


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'

        # Илова ба гурӯҳи каналҳо
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Ҳангоми қатъ шудан, хориҷ шудан аз гурӯҳ
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data.get('message', '')
            sender = data.get('sender', '')  # Агар лозим бошад
            receiver = data.get('receiver', '')  # Агар лозим бошад

            # Фиристодани паём ба гурӯҳ
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender': sender,
                    'receiver': receiver,
                }
            )
        except Exception as e:
            print('Хатогӣ дар receive:', str(e))
            await self.close()

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event.get('message', ''),
            'sender': event.get('sender', ''),
            'receiver': event.get('receiver', ''),
        }))

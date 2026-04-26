import json
from channels.generic.websocket import AsyncWebsocketConsumer


class TripLocationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer. Clients connect to ws://host/ws/trip/<trip_id>/
    and receive live GPS updates as the driver pushes them.
    """

    async def connect(self):
        self.trip_id = self.scope['url_route']['kwargs']['trip_id']
        self.group_name = f"trip_{self.trip_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send(json.dumps({'type': 'connection', 'message': f'Tracking trip {self.trip_id}'}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def location_update(self, event):
        """Receive location from group (broadcast from driver push) and forward to WebSocket client."""
        await self.send(json.dumps({
            'type': 'location_update',
            'latitude': event['latitude'],
            'longitude': event['longitude'],
            'speed_kmh': event['speed_kmh'],
        }))

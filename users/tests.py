from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from server.asgi import application

from .models import (
    AvailabilitySlot,
    Message,
    Booking,
    Notification,
    ProfessionalProfile,
    ProfessionalService,
    Review,
    ServiceCategory,
)

User = get_user_model()


def make_user(username, phone, **extra):
    return User.objects.create_user(
        username=username, password='StrongPass123', phone=phone, **extra
    )


class AuthTests(APITestCase):
    def test_register_returns_tokens_and_hashes_password(self):
        response = self.client.post('/register/', {
            'username': 'alice', 'password': 'StrongPass123',
            'first_name': 'Alice', 'last_name': 'A', 'phone': '+992900000001',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertNotIn('password', response.data['user'])

        user = User.objects.get(username='alice')
        self.assertNotEqual(user.password, 'StrongPass123')
        self.assertTrue(user.check_password('StrongPass123'))

    def test_login_returns_tokens_and_tracks_previous_login(self):
        make_user('bob', '+992900000002')

        first = self.client.post('/login/', {'username': 'bob', 'password': 'StrongPass123'})
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertIn('access', first.data)

        second = self.client.post('/login/', {'username': 'bob', 'password': 'StrongPass123'})
        self.assertEqual(second.status_code, status.HTTP_200_OK)

        bob = User.objects.get(username='bob')
        self.assertIsNotNone(bob.previous_login)

    def test_login_with_bad_password_is_rejected(self):
        make_user('carol', '+992900000003')
        response = self.client.post('/login/', {'username': 'carol', 'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh_token(self):
        """Regression: used to 400 because token_blacklist was not in INSTALLED_APPS."""
        make_user('dave', '+992900000004')
        login = self.client.post('/login/', {'username': 'dave', 'password': 'StrongPass123'})
        access, refresh = login.data['access'], login.data['refresh']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        response = self.client.post('/logout/', {'refresh': refresh})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Logged out successfully')

        # The blacklisted refresh token must no longer mint new access tokens.
        reuse = self.client.post('/api/token/refresh/', {'refresh': refresh})
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_without_refresh_field_returns_400(self):
        make_user('erin', '+992900000005')
        login = self.client.post('/login/', {'username': 'erin', 'password': 'StrongPass123'})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = self.client.post('/logout/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ProfessionalProfileTests(APITestCase):
    def setUp(self):
        self.user = make_user('pro', '+992900000010')
        self.client.force_authenticate(self.user)

    def test_creating_profile_flags_user_as_professional(self):
        response = self.client.post('/my-profile/', {
            'bio': 'Experienced plumber', 'hourly_rate': '25.00',
            'years_of_experience': 5, 'address': 'Dushanbe',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_professional)

    def test_duplicate_profile_is_rejected(self):
        payload = {'bio': 'x', 'hourly_rate': '10.00', 'years_of_experience': 1,
                   'address': 'Dushanbe'}
        self.client.post('/my-profile/', payload)
        second = self.client.post('/my-profile/', payload)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_profile_returns_200_not_201(self):
        """Regression: GET used to return HTTP 201 Created."""
        self.client.post('/my-profile/', {
            'bio': 'x', 'hourly_rate': '10.00', 'years_of_experience': 1,
            'address': 'Dushanbe',
        })
        response = self.client.get('/my-profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class BookingFlowTests(APITestCase):
    def setUp(self):
        self.client_user = make_user('client1', '+992900000020')
        self.pro_user = make_user('pro1', '+992900000021')
        self.profile = ProfessionalProfile.objects.create(
            user=self.pro_user, bio='Pro', hourly_rate='30.00',
            years_of_experience=3, address='Dushanbe',
        )
        self.category = ServiceCategory.objects.create(name='Plumbing', slug='plumbing', icon='p')
        self.service = ProfessionalService.objects.create(
            professional=self.profile, category=self.category, title='Fix sink',
            description='Sink repair', fixed_price='50.00', duration=60,
        )
        self.slot = AvailabilitySlot.objects.create(
            professional=self.profile,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
        )

    def _create_booking(self):
        self.client.force_authenticate(self.client_user)
        return self.client.post('/bookings/', {
            'professional': self.profile.id, 'service': self.service.id, 'slot': self.slot.id,
        })

    def test_booking_creation_notifies_professional_and_marks_slot(self):
        response = self._create_booking()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_booked)
        self.assertTrue(Notification.objects.filter(user=self.pro_user).exists())

    def test_double_booking_same_slot_is_rejected(self):
        self._create_booking()
        second = self.client.post('/bookings/', {
            'professional': self.profile.id, 'service': self.service.id, 'slot': self.slot.id,
        })
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_client_cannot_confirm_own_booking(self):
        booking_id = self._create_booking().data['id']
        response = self.client.post(f'/bookings/{booking_id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_professional_confirms_then_completes(self):
        booking_id = self._create_booking().data['id']

        self.client.force_authenticate(self.pro_user)
        confirm = self.client.post(f'/bookings/{booking_id}/confirm/')
        self.assertEqual(confirm.status_code, status.HTTP_200_OK)

        complete = self.client.post(f'/bookings/{booking_id}/complete/')
        self.assertEqual(complete.status_code, status.HTTP_200_OK)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_completed_jobs, 1)

    def test_cancelling_frees_the_slot(self):
        booking_id = self._create_booking().data['id']
        response = self.client.post(f'/bookings/{booking_id}/cancel/',
                                    {'cancellation_reason': 'Changed my mind'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_booked)

    def test_booking_visible_to_both_parties_only(self):
        self._create_booking()
        outsider = make_user('outsider', '+992900000022')

        self.client.force_authenticate(self.pro_user)
        self.assertEqual(len(self.client.get('/bookings/').data), 1)

        self.client.force_authenticate(outsider)
        self.assertEqual(len(self.client.get('/bookings/').data), 0)


class ReviewTests(APITestCase):
    def setUp(self):
        self.client_user = make_user('reviewer', '+992900000030')
        self.pro_user = make_user('pro2', '+992900000031')
        self.profile = ProfessionalProfile.objects.create(
            user=self.pro_user, bio='Pro', hourly_rate='30.00',
            years_of_experience=3, address='Dushanbe',
        )
        self.category = ServiceCategory.objects.create(name='Wiring', slug='wiring', icon='w')
        self.service = ProfessionalService.objects.create(
            professional=self.profile, category=self.category, title='Rewire',
            description='Rewiring', fixed_price='80.00', duration=120,
        )
        self.booking = Booking.objects.create(
            client=self.client_user, professional=self.profile,
            service=self.service, status='COMPLETED',
        )
        self.client.force_authenticate(self.client_user)

    def test_review_updates_average_rating(self):
        response = self.client.post('/reviews/', {
            'booking': self.booking.id, 'rating': 4, 'comment': 'Good work',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_reviews, 1)
        self.assertAlmostEqual(self.profile.average_rating, 4.0)

    def test_review_does_not_inflate_completed_jobs(self):
        """Regression: the review signal used to increment total_completed_jobs."""
        before = self.profile.total_completed_jobs
        self.client.post('/reviews/', {
            'booking': self.booking.id, 'rating': 5, 'comment': 'Great',
        })
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_completed_jobs, before)

    def test_duplicate_review_is_rejected(self):
        payload = {'booking': self.booking.id, 'rating': 5, 'comment': 'Great'}
        self.client.post('/reviews/', payload)
        self.assertEqual(self.client.post('/reviews/', payload).status_code,
                         status.HTTP_400_BAD_REQUEST)

    def test_cannot_review_incomplete_booking(self):
        self.booking.status = 'PENDING'
        self.booking.save()
        response = self.client.post('/reviews/', {
            'booking': self.booking.id, 'rating': 5, 'comment': 'Great',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deleting_review_recalculates_rating(self):
        self.client.post('/reviews/', {
            'booking': self.booking.id, 'rating': 4, 'comment': 'Good',
        })
        Review.objects.filter(booking=self.booking).delete()

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_reviews, 0)
        self.assertEqual(self.profile.average_rating, 0.0)


class MessagingTests(APITestCase):
    def setUp(self):
        self.sender = make_user('sender', '+992900000040')
        self.recipient = make_user('recipient', '+992900000041')

    def test_recipient_can_see_received_message(self):
        """Regression: get_queryset only filtered on sender, hiding received mail."""
        self.client.force_authenticate(self.sender)
        created = self.client.post('/messages/', {
            'recipient': self.recipient.id, 'content': 'Hello there',
        })
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.recipient)
        listed = self.client.get('/messages/')
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]['content'], 'Hello there')

        inbox = self.client.get('/messages/inbox/')
        self.assertEqual(len(inbox.data), 1)

    def test_unrelated_user_sees_nothing(self):
        self.client.force_authenticate(self.sender)
        self.client.post('/messages/', {'recipient': self.recipient.id, 'content': 'Hi'})

        self.client.force_authenticate(make_user('nosy', '+992900000042'))
        self.assertEqual(len(self.client.get('/messages/').data), 0)


class NotificationTests(APITestCase):
    def setUp(self):
        self.user = make_user('notified', '+992900000050')
        for index in range(3):
            Notification.objects.create(user=self.user, message=f'Note {index}',
                                        link='/bookings/1/')
        self.client.force_authenticate(self.user)

    def test_unread_count_and_mark_all_as_read(self):
        self.assertEqual(self.client.get('/notifications/unread_count/').data['unread_count'], 3)

        response = self.client.post('/notifications/mark_all_as_read/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/notifications/unread_count/').data['unread_count'], 0)

    def test_mark_single_as_read(self):
        notification = Notification.objects.filter(user=self.user).first()
        response = self.client.post(f'/notifications/{notification.id}/mark_as_read/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_read'])

    def test_relative_link_is_stored_intact(self):
        """Regression: link was a URLField but stores app-relative paths."""
        notification = Notification.objects.filter(user=self.user).first()
        self.assertEqual(notification.link, '/bookings/1/')


class PermissionTests(APITestCase):
    def test_admin_dashboard_requires_staff(self):
        user = make_user('plain', '+992900000060')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get('/admin-dashboard/').status_code,
                         status.HTTP_403_FORBIDDEN)

    def test_admin_dashboard_returns_full_payload(self):
        admin = User.objects.create_superuser(
            username='root', password='StrongPass123', phone='+992900000061')
        self.client.force_authenticate(admin)

        response = self.client.get('/admin-dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data['data']
        for section in ('user_stats', 'professional_stats', 'service_stats',
                        'booking_stats', 'payment_stats', 'review_stats', 'system_health'):
            self.assertIn(section, data)
        self.assertEqual(len(data['user_stats']['monthly_registrations']), 12)
        self.assertEqual(len(data['payment_stats']['monthly_revenue']), 12)

    def test_public_endpoints_are_open(self):
        for url in ('/search/professionals/', '/public-services/', '/categories/'):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK, url)

    def test_private_endpoints_require_auth(self):
        for url in ('/bookings/', '/messages/', '/notifications/', '/user-profile/'):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED, url)


class SchemaTests(APITestCase):
    def test_swagger_ui_loads(self):
        self.assertEqual(self.client.get('/swagger/').status_code, status.HTTP_200_OK)

    def test_redoc_loads(self):
        self.assertEqual(self.client.get('/redoc/').status_code, status.HTTP_200_OK)

    def test_openapi_schema_generates_without_errors(self):
        response = self.client.get('/swagger.json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        schema = response.json()
        self.assertIn('paths', schema)
        self.assertIn('Bearer', schema.get('securityDefinitions', {}))

        for path in ('/login/', '/register/', '/logout/', '/bookings/',
                     '/admin-dashboard/', '/public-services/', '/notifications/'):
            self.assertIn(path, schema['paths'], f'{path} missing from OpenAPI schema')


@override_settings(CHANNEL_LAYERS={
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
})
class WebSocketChatTests(TransactionTestCase):
    """Covers the chat consumer end to end, including JWT handshake auth.

    Uses the in-memory channel layer so the suite does not require Redis.
    """

    def setUp(self):
        self.alice = make_user('alice_ws', '+992900000070')
        self.bob = make_user('bob_ws', '+992900000071')
        self.room = 'alice_ws__bob_ws'

    def _token(self, user):
        return str(AccessToken.for_user(user))

    async def _connect(self, user, room=None):
        room = room or self.room
        communicator = WebsocketCommunicator(
            application, f'/ws/chat/{room}/?token={self._token(user)}'
        )
        connected, _ = await communicator.connect()
        return communicator, connected

    def test_authenticated_participant_can_connect_and_send(self):
        async def scenario():
            alice_conn, connected = await self._connect(self.alice)
            self.assertTrue(connected)

            bob_conn, bob_connected = await self._connect(self.bob)
            self.assertTrue(bob_connected)

            await alice_conn.send_json_to({'message': 'Hi Bob', 'receiver': 'bob_ws'})
            received = await bob_conn.receive_json_from(timeout=5)

            self.assertEqual(received['message'], 'Hi Bob')
            self.assertEqual(received['sender'], 'alice_ws')

            await alice_conn.disconnect()
            await bob_conn.disconnect()

        async_to_sync(scenario)()
        self.assertTrue(Message.objects.filter(sender=self.alice, content='Hi Bob').exists())

    def test_connection_without_token_is_rejected(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, f'/ws/chat/{self.room}/')
            connected, _ = await communicator.connect()
            self.assertFalse(connected)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_outsider_cannot_join_room(self):
        outsider = make_user('mallory', '+992900000072')

        async def scenario():
            communicator, connected = await self._connect(outsider)
            self.assertFalse(connected)
            await communicator.disconnect()

        async_to_sync(scenario)()

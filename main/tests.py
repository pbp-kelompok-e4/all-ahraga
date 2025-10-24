from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Venue, LocationArea, SportCategory, VenueSchedule, Booking, Review, UserProfile
from .models import Transaction
from datetime import date, time


class LandingAndDashboardTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username='owner2', password='ownerpass')
		self.customer = User.objects.create_user(username='cust2', password='custpass')
		UserProfile.objects.create(user=self.customer, is_customer=True)
		self.customer2 = User.objects.create_user(username='cust3', password='custpass3')
		UserProfile.objects.create(user=self.customer2, is_customer=True)

		self.area = LocationArea.objects.create(name='AreaX')
		self.sport = SportCategory.objects.create(name='SportX')
		self.venue = Venue.objects.create(owner=self.owner, name='VenueX', description='D', location=self.area, price_per_hour=50, sport_category=self.sport)
		self.schedule = VenueSchedule.objects.create(venue=self.venue, date=date.today(), start_time=time(9,0), end_time=time(10,0))
		self.booking = Booking.objects.create(customer=self.customer, venue_schedule=self.schedule, total_price=50)
		Transaction.objects.create(booking=self.booking, status='PENDING', payment_method='TRANSFER', revenue_venue=50)
		self.review = Review.objects.create(customer=self.customer, target_venue=self.venue, rating=5, comment='Great')

		self.schedule2 = VenueSchedule.objects.create(venue=self.venue, date=date.today(), start_time=time(11,0), end_time=time(12,0))
		self.booking2 = Booking.objects.create(customer=self.customer2, venue_schedule=self.schedule2, total_price=60)
		Transaction.objects.create(booking=self.booking2, status='PENDING', payment_method='TRANSFER', revenue_venue=60)

	def test_landing_shows_featured_and_feedback(self):
		url = reverse('landing')
		resp = self.client.get(url)
		self.assertEqual(resp.status_code, 200)
		content = resp.content.decode()
		self.assertIn('VenueX', content)
		self.assertIn('Great', content)

	def test_my_bookings_shows_booking_for_customer(self):
		self.client.login(username='cust2', password='custpass')
		url = reverse('my_bookings')
		resp = self.client.get(url)
		self.assertEqual(resp.status_code, 200)
		self.assertIn('VenueX', resp.content.decode())

	def test_ajax_add_review_creates_review(self):
		self.client.login(username='cust3', password='custpass3')
		url = reverse('add_review_ajax')
		resp = self.client.post(url, {'booking_id': self.booking2.id, 'rating': '4', 'message': 'Nice venue'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
		self.assertEqual(resp.status_code, 200)
		data = resp.json()
		self.assertTrue(data.get('success'))
		self.assertTrue(Review.objects.filter(customer=self.customer2, target_venue=self.venue, comment='Nice venue').exists())

	def test_ajax_prevent_duplicate_review(self):
		self.client.login(username='cust3', password='custpass3')
		url = reverse('add_review_ajax')
		Review.objects.create(customer=self.customer2, target_venue=self.venue, rating=2, comment='Initial')
		resp = self.client.post(url, {'booking_id': self.booking2.id, 'rating': '5', 'message': 'Another'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
		self.assertEqual(resp.status_code, 400)
		data = resp.json()
		self.assertFalse(data.get('success'))

	def test_add_feedback_view_creates_review(self):
		self.client.login(username='cust3', password='custpass3')
		url = reverse('add_feedback')
		resp = self.client.post(url, {'rating': '4', 'message': 'Form feedback'})
		self.assertEqual(resp.status_code, 302)
		self.assertTrue(Review.objects.filter(customer=self.customer2, comment='Form feedback').exists())

	def test_edit_feedback_allows_owner(self):
		self.client.login(username='cust3', password='custpass3')
		rev = Review.objects.create(customer=self.customer2, target_venue=self.venue, rating=3, comment='To edit')
		url = reverse('edit_feedback', args=[rev.id])
		resp = self.client.post(url, {'rating': '5', 'message': 'Updated msg'})
		self.assertEqual(resp.status_code, 302)
		rev.refresh_from_db()
		self.assertEqual(rev.rating, 5)
		self.assertEqual(rev.comment, 'Updated msg')

	def test_delete_feedback_allows_owner(self):
		self.client.login(username='cust3', password='custpass3')
		rev = Review.objects.create(customer=self.customer2, target_venue=self.venue, rating=4, comment='To delete')
		url = reverse('delete_feedback', args=[rev.id])
		resp = self.client.post(url, {})
		self.assertEqual(resp.status_code, 302)
		self.assertFalse(Review.objects.filter(id=rev.id).exists())

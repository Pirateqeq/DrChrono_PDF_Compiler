import requests
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock

from verify.exceptions import DrChronoAuthError
from search.services import search_patients


class SearchPatientsTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testuser')

    def make_request(self):
        request = self.factory.get('/')
        request.user = self.user
        return request

    @patch('search.services.requests.get')
    @patch('search.services.get_valid_access_token')
    @patch('verify.services.get_valid_access_token')
    def test_returns_patients_and_cursor_on_success(self, mock_token, mock_search_token, mock_get):
        mock_token.return_value = 'valid_token'
        mock_search_token.return_value = 'valid_token'
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            'results': [{'id': 1, 'first_name': 'John', 'last_name': 'Smith'}],
            'next': 'https://next-page-cursor',
        }
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        patients, cursor = search_patients(self.make_request(), {'last_name': 'Smith'})

        self.assertEqual(len(patients), 1)
        self.assertEqual(patients[0]['first_name'], 'John')
        self.assertEqual(cursor, 'https://next-page-cursor')

    @patch('search.services.requests.get')
    @patch('search.services.get_valid_access_token')
    @patch('verify.services.get_valid_access_token')
    def test_calls_patients_summary_endpoint(self, mock_token, mock_search_token, mock_get):
        mock_token.return_value = 'valid_token'
        mock_search_token.return_value = 'valid_token'
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'results': [], 'next': None}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        search_patients(self.make_request(), {'last_name': 'Smith'})

        call_url = mock_get.call_args[0][0]
        self.assertIn('patients_summary', call_url)

    @patch('search.services.requests.get')
    @patch('search.services.get_valid_access_token')
    @patch('verify.services.get_valid_access_token')
    def test_converts_dob_from_mm_dd_yyyy(self, mock_token, mock_search_token, mock_get):
        mock_token.return_value = 'valid_token'
        mock_search_token.return_value = 'valid_token'
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'results': [], 'next': None}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        search_patients(self.make_request(), {'date_of_birth': '05/15/1980'})

        params = mock_get.call_args[1]['params']
        self.assertEqual(params['date_of_birth'], '1980-05-15')

    @patch('search.services.requests.get')
    @patch('search.services.get_valid_access_token')
    @patch('verify.services.get_valid_access_token')
    def test_raises_auth_error_on_401(self, mock_token, mock_search_token, mock_get):
        mock_token.return_value = 'valid_token'
        mock_search_token.return_value = 'valid_token'
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = requests.HTTPError(response=mock_resp)
        mock_get.return_value = mock_resp

        with self.assertRaises(DrChronoAuthError):
            search_patients(self.make_request(), {'last_name': 'Smith'})

    @patch('search.services.requests.get')
    @patch('search.services.get_valid_access_token')
    @patch('verify.services.get_valid_access_token')
    def test_raises_auth_error_on_403(self, mock_token, mock_search_token, mock_get):
        mock_token.return_value = 'valid_token'
        mock_search_token.return_value = 'valid_token'
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.raise_for_status.side_effect = requests.HTTPError(response=mock_resp)
        mock_get.return_value = mock_resp

        with self.assertRaises(DrChronoAuthError):
            search_patients(self.make_request(), {'last_name': 'Smith'})

    @patch('search.services.requests.get')
    @patch('search.services.get_valid_access_token')
    @patch('verify.services.get_valid_access_token')
    def test_raises_value_error_on_other_http_error(self, mock_token, mock_search_token, mock_get):
        mock_token.return_value = 'valid_token'
        mock_search_token.return_value = 'valid_token'
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = 'Internal Server Error'
        mock_resp.raise_for_status.side_effect = requests.HTTPError(response=mock_resp)
        mock_get.return_value = mock_resp

        with self.assertRaises(ValueError):
            search_patients(self.make_request(), {'last_name': 'Smith'})

    @patch('search.services.requests.get')
    @patch('search.services.get_valid_access_token')
    @patch('verify.services.get_valid_access_token')
    def test_raises_value_error_on_network_error(self, mock_token, mock_search_token, mock_get):
        mock_token.return_value = 'valid_token'
        mock_search_token.return_value = 'valid_token'
        mock_get.side_effect = requests.RequestException("Network down")

        with self.assertRaises(ValueError):
            search_patients(self.make_request(), {'last_name': 'Smith'})
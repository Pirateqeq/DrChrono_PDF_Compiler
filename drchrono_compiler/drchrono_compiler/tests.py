import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.template.loader import render_to_string
from django.urls import resolve, reverse

ROUTES = [
    ('verify_app:connect_drchrono', {}, '/'),
    ('verify_app:oauth_callback', {}, '/oauth/callback'),
    ('search_app:search', {}, '/search/'),
    ('search_app:results', {}, '/search/results/'),
    ('appts_app:historical_list', {'patient_id': 101}, '/appts/patient/101/'),
    ('pdf_app:generate_selected', {'patient_id': 101}, '/pdf/patient/101/generate-selected/'),
]


@pytest.mark.parametrize('name, kwargs, path', ROUTES)
def test_named_routes(name, kwargs, path):
    assert reverse(name, kwargs=kwargs) == path
    assert resolve(path.replace('%20', ' ')).view_name == name


def test_system_check_passes():
    call_command('check')


class TestLayout:
    def test_signed_out(self, rf):
        request = rf.get('/')
        request.user = AnonymousUser()

        html = render_to_string('layout.html', request=request)

        assert 'Not connected' in html

    def test_signed_in(self, auth_client):
        html = auth_client.get(reverse('search_app:search')).content.decode()

        assert 'Connected' in html
        assert 'Not connected' not in html
        assert f'href="{reverse("search_app:search")}"' in html

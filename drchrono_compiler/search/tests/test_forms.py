from django.test import TestCase
from search.forms import PatientSearchForm


class PatientSearchFormTests(TestCase):

    def test_all_empty_is_invalid(self):
        form = PatientSearchForm(data={})
        self.assertFalse(form.is_valid())

    def test_first_name_only_is_valid(self):
        form = PatientSearchForm(data={'first_name': 'John'})
        self.assertTrue(form.is_valid())

    def test_last_name_only_is_valid(self):
        form = PatientSearchForm(data={'last_name': 'Smith'})
        self.assertTrue(form.is_valid())

    def test_dob_only_is_valid(self):
        form = PatientSearchForm(data={'date_of_birth': '1980-05-15'})
        self.assertTrue(form.is_valid())

    def test_dob_accepts_mm_dd_yyyy_format(self):
        form = PatientSearchForm(data={'date_of_birth': '05/15/1980'})
        self.assertTrue(form.is_valid())

    def test_all_fields_is_valid(self):
        form = PatientSearchForm(data={
            'first_name': 'John',
            'last_name': 'Smith',
            'date_of_birth': '1980-05-15',
        })
        self.assertTrue(form.is_valid())
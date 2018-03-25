from datetime import timedelta
from unittest import mock

import responses
from django.http import HttpResponseForbidden
from django.test import TestCase, Client
from django.utils import timezone
from rest_framework.reverse import reverse

from kw_webapp.tasks import build_API_sync_string_for_user_for_levels
from kw_webapp.tests import sample_api_responses
from kw_webapp.tests.utils import create_user, create_userspecific, create_profile, create_reading
from kw_webapp.tests.utils import create_vocab


class TestViews(TestCase):
    def setUp(self):
        self.user = create_user("user1")
        self.user.set_password("password")
        self.user.save()
        create_profile(self.user, "some_key", 5)
        # create a piece of vocab with one reading.
        self.vocabulary = create_vocab("radioactive bat")
        self.cat_reading = create_reading(self.vocabulary, "ねこ", "猫", 5)

        # setup a review with two synonyms
        self.review = create_userspecific(self.vocabulary, self.user)

        self.client = Client()
        self.client.login(username="user1", password="password")

    @responses.activate
    def test_sync_now_endpoint_returns_correct_json(self):
        responses.add(responses.GET,
                      "https://www.wanikani.com/api/user/{}/user-information".format(self.user.profile.api_key),
                      json=sample_api_responses.user_information_response_with_higher_level,
                      status=200,
                      content_type="application/json")

        responses.add(responses.GET, build_API_sync_string_for_user_for_levels(self.user, [5, 17]),
                      json=sample_api_responses.single_vocab_response,
                      status=200,
                      content_type='application/json')

        test = build_API_sync_string_for_user_for_levels(self.user, [5, 17])
        response = self.client.post(reverse("api:user-sync"), data={"full_sync": "true"})

        correct_response = {
            "new_review_count": 0,
            "profile_sync_succeeded": True,
            "new_synonym_count": 0
        }

        self.assertJSONEqual(str(response.content, encoding='utf8'), correct_response)

    def test_removing_synonym_removes_synonym(self):
        dummy_kana = "whatever"
        dummy_characters = "somechar"
        synonym, created = self.review.add_answer_synonym(dummy_kana, dummy_characters)

        self.client.delete(reverse("api:reading-synonym-detail", args=(synonym.id,)))

        self.review.refresh_from_db()

        self.assertListEqual(self.review.reading_synonyms_list(), [])

    def test_reviewing_that_does_not_need_to_be_reviewed_fails(self):
        self.review.needs_review = False
        self.review.save()

        response = self.client.post(reverse("api:review-correct", args=(self.review.id,)), data={'wrong_before': 'false'})
        self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(response.data['detail'])

        response = self.client.post(reverse("api:review-incorrect", args=(self.review.id,)))
        self.assertEqual(response.status_code, 403)
        self.assertIsNotNone(response.data['detail'])

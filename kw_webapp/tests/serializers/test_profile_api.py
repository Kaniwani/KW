from datetime import timedelta, time
from time import sleep

import responses
from django.utils import timezone
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from kw_webapp import constants
from kw_webapp.models import Announcement, Vocabulary
from kw_webapp.tasks import get_vocab_by_kanji, sync_with_wk
from kw_webapp.tests.utils import (
    create_vocab,
    create_reading,
    create_review,
    create_review_for_specific_time,
    mock_invalid_api_user_info_response_v2,
    setupTestFixture,
    mock_for_registration,
    mock_user_response_v2,
    mock_subjects_v2,
    mock_assignments_with_one_assignment,
    mock_study_materials, mock_assignments_with_no_assignments,
)


class TestProfileApi(APITestCase):
    def setUp(self):
        setupTestFixture(self)

    def test_profile_contains_correct_within_day_or_hour_counts(self):
        self.client.force_login(user=self.user)
        self.review.answered_correctly(first_try=True, can_burn=True)
        self.review.save()

        response = self.client.get(reverse("api:user-me"))
        self.assertEqual(
            response.data["profile"]["reviews_within_hour_count"], 0
        )
        self.assertEqual(
            response.data["profile"]["reviews_within_day_count"], 1
        )

    def test_profile_contains_expected_fields(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api:profile-list"))
        data = response.data["results"][0]

        # Ensure new 2.0 fields are all there
        self.assertIsNotNone(
            data["auto_advance_on_success_delay_milliseconds"]
        )
        self.assertIsNotNone(data["use_eijiro_pro_link"])
        self.assertIsNotNone(data["show_kanji_svg_stroke_order"])
        self.assertIsNotNone(data["show_kanji_svg_grid"])
        self.assertIsNotNone(data["kanji_svg_draw_speed"])
        self.assertIsNotNone(data["repeat_until_correct"])

    def test_updating_profile_triggers_srs_correctly(self):
        self.client.force_login(user=self.user)
        response = self.client.get(reverse("api:user-me"))

        self.assertEqual(
            response.data["profile"]["srs_counts"]["apprentice"], 1
        )
        self.assertEqual(response.data["profile"]["srs_counts"]["guru"], 0)
        self.assertEqual(response.data["profile"]["srs_counts"]["master"], 0)
        self.assertEqual(
            response.data["profile"]["srs_counts"]["enlightened"], 0
        )
        self.assertEqual(response.data["profile"]["srs_counts"]["burned"], 0)
        user_dict = dict(response.data)
        user_dict["profile"]["on_vacation"] = True
        user_dict["profile"]["follow_me"] = True

        self.client.put(
            reverse("api:profile-detail", (self.user.profile.id,)),
            user_dict,
            format="json",
        )

    def test_burnt_items_arent_included_when_getting_next_review_date(self):
        self.client.force_login(user=self.user)
        current_time = timezone.now()
        self.review.next_review_date = current_time
        self.review.needs_review = False
        self.review.save()

        older_burnt_review = create_review(create_vocab("test"), self.user)
        older_burnt_review.burned = True
        older_burnt_review.needs_review = False
        an_hour_ago = current_time - timedelta(hours=1)
        older_burnt_review.next_review_date = an_hour_ago
        older_burnt_review.save()

        response = self.client.get(reverse("api:user-me"))

        self.assertEqual(
            response.data["profile"]["next_review_date"], current_time
        )

    def test_ordering_on_announcements_works(self):

        Announcement.objects.create(
            creator=self.user, title="ASD123", body="ASDSAD"
        )
        sleep(1)
        Announcement.objects.create(
            creator=self.user, title="ASD1234", body="ASDSAD"
        )
        sleep(1)
        Announcement.objects.create(
            creator=self.user, title="ASD1345", body="ASDSAD"
        )
        sleep(1)
        Announcement.objects.create(
            creator=self.user, title="ASD123456", body="ASDSAD"
        )
        sleep(1)

        response = self.client.get(reverse("api:announcement-list"))

        announcements = response.data["results"]
        self.assertGreater(
            announcements[0]["pub_date"], announcements[1]["pub_date"]
        )
        self.assertGreater(
            announcements[1]["pub_date"], announcements[2]["pub_date"]
        )
        self.assertGreater(
            announcements[2]["pub_date"], announcements[3]["pub_date"]
        )

    def test_get_vocab_by_kanji_works_in_case_of_multiple_reading_vocab(self):
        v = create_vocab("my vocab")
        create_reading(v, "kana_1", "kanji", 5)
        create_reading(v, "kana_2", "kanji", 5)
        get_vocab_by_kanji("kanji")

    def test_get_vocab_by_kanji_correctly_fails_on_duplicate_kanji(self):
        v = create_vocab("my vocab")
        create_reading(v, "kana_1", "kanji", 5)
        v2 = create_vocab("my vocab")
        create_reading(v2, "kana_2", "kanji", 5)

        self.assertRaises(
            Vocabulary.MultipleObjectsReturned, get_vocab_by_kanji, "kanji"
        )

    @responses.activate
    def test_users_with_invalid_api_keys_correctly_get_their_flag_changed_in_profile(
        self
    ):
        self.user.profile.api_key = "ABC123"
        mock_invalid_api_user_info_response_v2()
        self.user.profile.api_valid = True
        self.user.profile.save()

        sync_with_wk(self.user.id)

        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.api_valid)

    def test_sending_patch_to_profile_correctly_updates_information(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:profile-list"))
        data = response.data
        id = data["results"][0]["id"]
        self.client.patch(
            reverse("api:profile-detail", args=(id,)),
            data={"on_vacation": True},
            format="json",
        )
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        assert self.user.profile.vacation_date is not None

    @responses.activate
    def test_sending_put_to_profile_correctly_updates_information(self):
        self.client.force_login(self.user)
        mock_user_response_v2()

        response = self.client.get(reverse("api:profile-list"))
        data = response.data
        id = data["results"][0]["id"]
        request = data["results"][0]
        request["on_vacation"] = True
        response = self.client.put(
            reverse("api:profile-detail", args=(id,)),
            data=request,
            format="json",
        )
        assert response.status_code == 200
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        assert self.user.profile.vacation_date is not None
        data = response.data
        assert data is not None

    @responses.activate
    def test_enable_follow_me_syncs_user_immediately(self):
        # Given
        mock_user_response_v2()
        mock_assignments_with_no_assignments()

        self.client.force_login(self.user)
        self.user.profile.follow_me = False
        self.user.profile.save()
        response = self.client.get(reverse("api:profile-list"))
        data = response.data
        id = data["results"][0]["id"]

        # When
        self.client.patch(
            reverse("api:profile-detail", args=(id,)),
            data={"follow_me": True},
            format="json",
        )

        # Then
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        assert self.user.profile.follow_me is True

    @responses.activate
    def test_attempting_to_sync_with_invalid_api_key_sets_correct_profile_value(
        self
    ):
        # Given
        self.client.force_login(self.user)
        self.user.profile.api_key = "SomeGarbage"
        self.user.profile.save()
        mock_invalid_api_user_info_response_v2()

        # When
        self.client.post(reverse("api:user-sync"))

        # Then
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        assert self.user.profile.api_valid is False

    @responses.activate
    def test_registration(self):
        mock_subjects_v2()
        mock_assignments_with_one_assignment()
        mock_user_response_v2()
        mock_study_materials()
        response = self.client.post(
            reverse("api:auth:user-list"),
            data={
                "username": "createme",
                "password": "password",
                "api_key_v2": constants.API_KEY_V2,
                "email": "asdf@email.com",
            },
        )
        assert response.status_code == 201

    def test_review_incorrect_submissions_return_full_modified_review_object(
        self
    ):
        self.client.force_login(self.user)

        # We have to bump this to two to be able to see the drop in streak.
        self.review.streak = 2
        self.review.save()
        self.review.refresh_from_db()

        previous_streak = self.review.streak
        previous_incorrect = self.review.incorrect

        response = self.client.post(
            reverse("api:review-incorrect", args=(self.review.id,))
        )
        self.assertEqual(response.data["id"], self.review.id)
        self.assertEqual(response.data["streak"], previous_streak - 1)
        self.assertEqual(response.data["incorrect"], previous_incorrect + 1)

    def skip_nones(self, thedict):
        return {k: v for k, v in thedict.items() if v is not None}

    @responses.activate
    def test_api_is_validated_any_time_it_is_modified(self):
        self.client.force_login(self.user)
        # Setup
        invalid_api_key = "invalid_key!"
        mock_invalid_api_user_info_response_v2()

        # Test upon PUT in profile.
        self.user.profile.api_key = invalid_api_key
        self.user.profile.api_valid = False
        self.user.profile.save()

        response = self.client.put(
            reverse("api:profile-detail", args=(self.user.profile.id,)),
            data=self.skip_nones(self.user.profile.__dict__),
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.patch(
            reverse("api:profile-detail", args=(self.user.profile.id,)),
            data={"api_key_v2": invalid_api_key},
        )
        self.assertEqual(response.status_code, 400)

        # Make sure it doesnt get accidentally set if we patch another field.
        response = self.client.patch(
            reverse("api:profile-detail", args=(self.user.profile.id,)),
            data={"kanji_svg_draw_speed": 4},
        )
        self.assertFalse(response.data["api_valid"])

    @responses.activate
    def test_thing(self):
        self.client.force_login(self.user)
        # Now patch it to a valid key, which should set it to true.
        mock_user_response_v2()
        response = self.client.patch(
            reverse("api:profile-detail", args=(self.user.profile.id,)),
            data={"api_key_v2": "ANYTHING"},
        )

        self.assertTrue(response.data["api_valid"])

    def test_searching_based_on_reading_returns_distinct_responses(self):
        reading_to_search = "eyylmao"
        v = create_vocab("vocabulary with 2 readings.")
        create_reading(v, reading_to_search, "character_1", 5)
        create_reading(v, reading_to_search, "character_2", 5)

        create_review(v, self.user)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("api:review-list")
            + "?reading_contains={}".format(reading_to_search)
        )
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(len(data["results"]), 1)

    def test_upcoming_reviews_no_longer_wrap_around(self):
        self.client.force_login(self.user)
        # We place nothing in the upcoming hour, ergo
        for i in range(1, 26):
            for j in range(0, i):
                create_review_for_specific_time(
                    self.user,
                    "review_{}".format(i),
                    (timezone.now() + timedelta(hours=i)).replace(minute=0),
                )

        response = self.client.get(reverse("api:user-me"))
        data = response.data
        upcoming_reviews = data["profile"]["upcoming_reviews"]
        self.assertEqual(upcoming_reviews[0], 0)
        self.assertEqual(upcoming_reviews[23], 23)

    def test_reading_review_detail_levels_from_profile(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("api:profile-list"))
        data = response.data["results"][0]
        self.assertEqual(data["info_detail_level_on_success"], 1)
        self.assertEqual(data["info_detail_level_on_failure"], 0)
        patch = {}
        patch["info_detail_level_on_success"] = 2
        patch["info_detail_level_on_failure"] = 2

        response = self.client.patch(
            reverse("api:profile-detail", args=(data["id"],)), data=patch
        )
        data = response.data
        self.assertEqual(data["info_detail_level_on_success"], 2)
        self.assertEqual(data["info_detail_level_on_failure"], 2)

        # Oh no this is too high, should 400
        patch["info_detail_level_on_failure"] = 4
        response = self.client.patch(
            reverse("api:profile-detail", args=(data["id"],)), data=patch
        )
        self.assertEqual(response.status_code, 400)

    def test_preprocessor_future_reviews_counts_correctly_provides_same_day_review_count(
        self
    ):
        create_review_for_specific_time(
            self.user, "some word", timezone.now() + timedelta(minutes=30)
        )
        create_review_for_specific_time(
            self.user, "some word", timezone.now() + timedelta(hours=12)
        )
        create_review_for_specific_time(
            self.user, "some word", timezone.now() + timedelta(hours=48)
        )

        self.client.force_login(user=self.user)
        response = self.client.get(reverse("api:user-me"))

        self.assertEqual(
            response.data["profile"]["reviews_within_day_count"], 2
        )
        self.assertEqual(
            response.data["profile"]["reviews_within_hour_count"], 1
        )

    def test_future_review_counts_preprocessor_does_not_include_currently_active_reviews(
        self
    ):
        within_day_review = create_review_for_specific_time(
            self.user, "some word", timezone.now() + timedelta(hours=12)
        )
        within_day_review.needs_review = True
        within_day_review.save()

        self.client.force_login(user=self.user)
        response = self.client.get(reverse("api:user-me"))

        self.assertEqual(
            response.data["profile"]["reviews_within_day_count"], 0
        )
        self.assertEqual(
            response.data["profile"]["reviews_within_hour_count"], 0
        )

    def test_review_count_returns_sane_values_when_user_has_no_vocabulary_unlocked(
        self
    ):
        self.review.delete()

        self.client.force_login(user=self.user)
        response = self.client.get(reverse("api:user-me"))

        self.assertEqual(
            response.data["profile"]["reviews_within_day_count"], 0
        )
        self.assertEqual(
            response.data["profile"]["reviews_within_hour_count"], 0
        )

    def test_profile_srs_counts_are_correct(self):
        self.client.force_login(user=self.user)
        response = self.client.get(reverse("api:user-me"))

        self.assertEqual(
            response.data["profile"]["srs_counts"]["apprentice"], 1
        )
        self.assertEqual(response.data["profile"]["srs_counts"]["guru"], 0)
        self.assertEqual(response.data["profile"]["srs_counts"]["master"], 0)
        self.assertEqual(
            response.data["profile"]["srs_counts"]["enlightened"], 0
        )
        self.assertEqual(response.data["profile"]["srs_counts"]["burned"], 0)

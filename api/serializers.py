import datetime
from collections import OrderedDict

import requests
from django.contrib.auth.models import User
from django.db.models import Q, Count, TimeField
from django.utils import timezone
from django.db.models.functions import TruncHour, TruncDate
from rest_framework import serializers

from api import serializer_fields
from api.validators import WanikaniApiKeyValidatorV2
from kw_webapp.constants import (
    KwSrsLevel,
    KANIWANI_SRS_LEVELS,
    STREAK_TO_SRS_LEVEL_MAP_KW,
)
from kw_webapp.models import (
    Profile,
    Vocabulary,
    UserSpecific,
    Reading,
    Level,
    Tag,
    AnswerSynonym,
    FrequentlyAskedQuestion,
    Announcement,
    Report,
    MeaningSynonym,
)
from kw_webapp.tasks import (
    get_users_lessons,
    get_users_current_reviews,
    get_users_future_reviews,
    get_users_reviews,
    build_upcoming_srs_for_user,
)

import logging

logger = logging.getLogger(__name__)


class ReportCountSerializer(serializers.BaseSerializer):
    """
    Serializer which aggregates report counts by vocabulary.
    """

    def to_representation(self, obj):
        return (
            Report.objects.values("reading")
            .annotate(report_count=Count("reading"))
            .order_by("-report_count")
        )


class SrsCountSerializer(serializers.BaseSerializer):
    """
    Serializer for simply showing SRS counts, e.g., how many apprentice items a user has,
    how many guru, etc.
    """

    def to_representation(self, user):
        all_reviews = get_users_reviews(user)
        ordered_srs_counts = OrderedDict.fromkeys(
            [level.name.lower() for level in KwSrsLevel]
        )
        for level in KwSrsLevel:
            ordered_srs_counts[level.name.lower()] = all_reviews.filter(
                streak__in=KANIWANI_SRS_LEVELS[level.name]
            ).count()
        return ordered_srs_counts


class SimpleUpcomingReviewSerializer(serializers.BaseSerializer):
    """
    Serializer containing information about upcoming reviews, without any relevant srs information.
    """

    def to_representation(self, user):
        return build_upcoming_srs_for_user(user)


class DetailedUpcomingReviewCountSerializer(serializers.BaseSerializer):
    """
    Serializer for counting reviews on an hourly basis for the next 24 hours
    """

    def to_representation(self, user):
        now = timezone.now()
        one_day_from_now = now + datetime.timedelta(hours=24)

        reviews = (
            get_users_reviews(user)
            .filter(next_review_date__range=(now, one_day_from_now))
            .annotate(hour=TruncHour("next_review_date", tzinfo=timezone.utc))
            .annotate(date=TruncDate("next_review_date", tzinfo=timezone.utc))
            .values("streak", "date", "hour")
            .annotate(review_count=Count("id"))
            .order_by("date", "hour")
        )
        expected_hour = now.hour
        hours = [
            hour % 24 for hour in range(expected_hour, expected_hour + 24)
        ]

        retval = OrderedDict.fromkeys(hours)

        for key in retval.keys():
            retval[key] = OrderedDict.fromkeys(
                [level.name for level in KwSrsLevel], 0
            )

        for review in reviews:
            found_hour = review["hour"].hour
            while found_hour != expected_hour:
                expected_hour = (expected_hour + 1) % 24
            streak = review["streak"]
            srs_level = STREAK_TO_SRS_LEVEL_MAP_KW[streak].name
            retval[expected_hour][srs_level] += review["review_count"]

        real_retval = [
            [count for srs_rank, count in hourly_count.items()]
            for hour, hourly_count in retval.items()
        ]
        return real_retval


class ReviewCountSerializer(serializers.BaseSerializer):
    def to_representation(self, user):
        return {
            "reviews_count": self.get_reviews_count(user),
            "lessons_count": self.get_lessons_count(user),
        }

    def get_reviews_count(self, obj):
        return get_users_current_reviews(obj).count()

    def get_lessons_count(self, obj):
        return get_users_lessons(obj).count()


class ProfileSerializer(serializers.ModelSerializer):
    name = serializers.ReadOnlyField(source="user.username")
    next_review_date = serializers.SerializerMethodField()
    unlocked_levels = serializers.StringRelatedField(many=True, read_only=True)
    reviews_within_hour_count = serializers.SerializerMethodField()
    reviews_within_day_count = serializers.SerializerMethodField()
    srs_counts = SrsCountSerializer(source="user", many=False, read_only=True)
    # upcoming_reviews = DetailedUpcomingReviewCountSerializer(source='user', many=False, read_only=True)
    upcoming_reviews = SimpleUpcomingReviewSerializer(
        source="user", many=False, read_only=True
    )
    join_date = serializers.SerializerMethodField()
    api_key_v2 = serializers.CharField(
        max_length=40,
        validators=[WanikaniApiKeyValidatorV2()],
        allow_null=True,
    )

    class Meta:
        model = Profile
        fields = (
            "id",
            "name",
            "api_key_v2",
            "api_valid",
            "level",
            "follow_me",
            "auto_advance_on_success",
            "unlocked_levels",
            "last_wanikani_sync_date",
            "auto_expand_answer_on_success",
            "auto_expand_answer_on_failure",
            "on_vacation",
            "vacation_date",
            "reviews_within_day_count",
            "reviews_within_hour_count",
            "srs_counts",
            "minimum_wk_srs_level_to_review",
            "maximum_wk_srs_level_to_review",
            "upcoming_reviews",
            "next_review_date",
            "join_date",
            "auto_advance_on_success_delay_milliseconds",
            "use_eijiro_pro_link",
            "show_kanji_svg_stroke_order",
            "show_kanji_svg_grid",
            "kanji_svg_draw_speed",
            "info_detail_level_on_success",
            "info_detail_level_on_failure",
            "order_reviews_by_level",
            "burn_reviews",
            "repeat_until_correct"
        )

        read_only_fields = (
            "id",
            "name",
            "api_valid",
            "level",
            "unlocked_levels",
            "vacation_date",
            "reviews_within_day_count",
            "reviews_within_hour_count",
            "srs_counts",
            "next_review_date",
            "last_wanikani_sync_date",
            "join_date"
        )

    def get_join_date(self, obj):
        """
        So this is a hack. By default the modelserializer expects a datefield, but a fewww users have datetimefields as their join_date,
        due to an old version of the model. Eventually we should fix those users but for now this methodfield does the trick.
        """
        return obj.join_date

    def save(self, **kwargs):
        return super().save(**kwargs)

    def get_next_review_date(self, obj):
        user = obj.user
        if self.get_reviews_count(obj) == 0:
            reviews = get_users_future_reviews(user)
            if reviews:
                next_review_date = reviews[0].next_review_date
                return next_review_date

    def get_reviews_count(self, obj):
        return get_users_current_reviews(obj.user).count()

    def get_reviews_within_hour_count(self, obj):
        return get_users_future_reviews(
            obj.user, time_limit=datetime.timedelta(hours=1)
        ).count()

    def get_reviews_within_day_count(self, obj):
        return get_users_future_reviews(
            obj.user, time_limit=datetime.timedelta(hours=24)
        ).count()


class RegistrationSerializer(serializers.ModelSerializer):
    api_key_v2 = serializers.CharField(
        write_only=True,
        max_length=40,
        validators=[WanikaniApiKeyValidatorV2()],
        required=True,
    )
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ("api_key_v2", "password", "username", "email")

    def validate_password(self, value):
        if len(value) < 4:
            raise serializers.ValidationError("Password is not long enough!")
        return value

    def validate_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            return value
        else:
            raise serializers.ValidationError("Email is already in use!")

    def validate_username(self, value):
        try:
            User.objects.get(username=value)
        except User.DoesNotExist:
            return value
        else:
            raise serializers.ValidationError("Username is already in use!")

    def create(self, validated_data):
        preexisting_users = User.objects.filter(
            Q(username=validated_data.get("username"))
            | Q(email=validated_data.get("email"))
        )

        if preexisting_users.count() > 0:
            raise serializers.ValidationError(
                "Username or email already in use!"
            )

        api_key_v2 = validated_data.pop("api_key_v2", None)
        user = User.objects.create(**validated_data)
        user.set_password(validated_data.get("password"))
        user.save()
        Profile.objects.create(
            user=user, api_key_v2=api_key_v2, level=1
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(many=False, read_only=True)
    api_key_v2 = serializers.CharField(
        write_only=True,
        max_length=40,
        validators=[WanikaniApiKeyValidatorV2()],
        allow_null=True,
        allow_blank=True,
    )
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            "api_key_v2",
            "password",
            "username",
            "email",
            "profile",
        )
        read_only_fields = (
            "id",
            "last_login",
            "is_active",
            "date_joined",
            "is_staff",
            "is_superuser",
            "profile",
        )

    def validate_password(self, value):
        if len(value) < 4:
            raise serializers.ValidationError("Password is not long enough!")
        return value

    def validate_email(self, value):
        try:
            User.objects.get(email=value)
        except User.DoesNotExist:
            return value
        else:
            raise serializers.ValidationError("Email is already in use!")

    def validate_username(self, value):
        try:
            User.objects.get(username=value)
        except User.DoesNotExist:
            return value
        else:
            raise serializers.ValidationError("Username is already in use!")

    def create(self, validated_data):
        preexisting_users = User.objects.filter(
            Q(username=validated_data.get("username"))
            | Q(email=validated_data.get("email"))
        )

        if preexisting_users.count() > 0:
            raise serializers.ValidationError(
                "Username or email already in use!"
            )

        api_key = validated_data.pop("api_key", None)

        user = User.objects.create(**validated_data)
        user.set_password(validated_data.get("password"))
        Profile.objects.create(user=user, api_key=api_key, level=1)

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile")
        profile_serializer = ProfileSerializer(data=profile_data)
        profile_serializer.save()
        instance.save()


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("name",)


class ReadingSerializer(serializers.ModelSerializer):
    parts_of_speech = serializers.StringRelatedField(many=True, read_only=True)

    class Meta:
        model = Reading
        fields = (
            "id",
            "character",
            "kana",
            "level",
            "sentence_en",
            "sentence_ja",
            "furigana_sentence_ja",
            "common",
            "furigana",
            "pitch",
            "parts_of_speech",
        )


class VocabularySerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super(VocabularySerializer, self).__init__(*args, **kwargs)
        # If this is part of the review response, simply omit the review field, reducing DB calls.
        if "nested_in_review" in self.context:
            self.fields.pop("review")
            self.fields.pop("is_reviewable")

    readings = ReadingSerializer(many=True, read_only=True)
    review = serializers.SerializerMethodField()
    is_reviewable = serializers.SerializerMethodField()

    class Meta:
        model = Vocabulary
        fields = ("id", "meaning", "readings", "review", "is_reviewable", "manual_reading_whitelist")

    # Grab the ID of the related review for this particular user.
    def get_review(self, obj):
        if "request" in self.context:
            try:
                return UserSpecific.objects.get(
                    user=self.context["request"].user, vocabulary=obj
                ).id
            except UserSpecific.DoesNotExist:
                return None
        return None

    def get_is_reviewable(self, obj):
        if "request" in self.context:
            try:
                minimum_level_to_review = self.context[
                    "request"
                ].user.profile.get_minimum_wk_srs_threshold_for_review()
                maximum_level_to_review = self.context[
                    "request"
                ].user.profile.get_maximum_wk_srs_threshold_for_review()
                return (
                    UserSpecific.objects.filter(
                        user=self.context["request"].user,
                        vocabulary=obj,
                        wanikani_srs_numeric__range=(
                            minimum_level_to_review,
                            maximum_level_to_review,
                        ),
                    ).count()
                    > 0
                )

            except UserSpecific.DoesNotExist:
                return None
        return None


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = "__all__"
        read_only_fields = ("created_by", "created_at")


class ReportListSerializer(ReportSerializer):
    reading = ReadingSerializer(many=False, read_only=True)


class HyperlinkedVocabularySerializer(VocabularySerializer):
    readings = serializers.HyperlinkedRelatedField(
        many=True, read_only=True, view_name="api:reading-detail"
    )

    class Meta(VocabularySerializer.Meta):
        pass


class MeaningSynonymSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeaningSynonym
        fields = "__all__"

    def validate(self, data):
        review = data["review"]
        if review.user != self.context["request"].user:
            raise serializers.ValidationError(
                "Can not make a synonym for a review that is not yours!"
            )
        return data


class ReadingSynonymSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerSynonym
        fields = "__all__"

    def validate(self, data):
        review = data["review"]
        if review.user != self.context["request"].user:
            raise serializers.ValidationError(
                "Can not make a synonym for a review that is not yours!"
            )
        return data

    def create(self, validated_data):
        return super().create(validated_data)

    def is_valid(self, raise_exception=False):
        return super().is_valid(True)


class ReviewSerializer(serializers.ModelSerializer):
    vocabulary = VocabularySerializer(
        many=False, read_only=True, context={"nested_in_review": True}
    )
    reading_synonyms = ReadingSynonymSerializer(many=True, read_only=True)
    meaning_synonyms = MeaningSynonymSerializer(many=True, read_only=True)

    class Meta:
        model = UserSpecific
        fields = "__all__"

        read_only_fields = (
            "id",
            "vocabulary",
            "correct",
            "incorrect",
            "streak",
            "user",
            "needs_review",
            "last_studied",
            "unlock_date",
            "wanikani_srs",
            "reading_synonyms",
            "meaning_synonyms",
            "wanikani_srs_numeric",
            "wanikani_burned",
            "burned",
            "critical",
        )


class StubbedReviewSerializer(ReviewSerializer):
    class Meta(ReviewSerializer.Meta):
        fields = (
            "id",
            "vocabulary",
            "correct",
            "incorrect",
            "streak",
            "notes",
            "reading_synonyms",
            "meaning_synonyms",
        )


class LevelSerializer(serializers.Serializer):
    level = serializers.IntegerField(read_only=True)
    unlocked = serializers.BooleanField(read_only=True)
    vocabulary_count = serializers.IntegerField(read_only=True)
    vocabulary_url = serializer_fields.VocabularyByLevelHyperlinkedField(
        read_only=True
    )
    lock_url = serializers.CharField(read_only=True)
    fully_unlocked = serializers.BooleanField(read_only=True)
    unlock_url = serializers.CharField(read_only=True)


class FrequentlyAskedQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FrequentlyAskedQuestion
        fields = "__all__"


class AnnouncementSerializer(serializers.ModelSerializer):
    creator = serializers.ReadOnlyField(source="creator.username")

    class Meta:
        model = Announcement
        fields = ("title", "body", "pub_date", "creator")


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.CharField(max_length=200)
    body = serializers.CharField(max_length=1000)

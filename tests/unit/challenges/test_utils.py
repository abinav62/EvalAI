import boto3
import datetime
import os
import unittest
import mock
import tzlocal

from allauth.account.models import EmailAddress
from challenges.models import Challenge
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from hosts.models import ChallengeHost, ChallengeHostTeam
from moto import mock_ecr, mock_sts
from rest_framework.test import APIClient, APITestCase

import challenges.utils as utils


class BaseTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

        self.test_file_path = os.path.join(
            settings.BASE_DIR, "examples", "example1", "test_annotation.txt"
        )
        self.user = User.objects.create(
            username="myUser",
            email="user@test.com",
            password="secret_password",
        )

        EmailAddress.objects.create(
            user=self.user, email="user@test.com", primary=True, verified=True
        )

        self.challenge_host_team = ChallengeHostTeam.objects.create(
            team_name="Test Challenge Host Team", created_by=self.user
        )

        self.challenge = Challenge.objects.create(
            title="Test Challenge",
            short_description="Short description",
            description="Descriptione",
            terms_and_conditions="Terms and conditions",
            submission_guidelines="Submission guidelines",
            creator=self.challenge_host_team,
            published=False,
            is_registration_open=True,
            enable_forum=True,
            queue="test_queue",
            anonymous_leaderboard=False,
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=1),
            approved_by_admin=False,
            aws_account_id="id",
            aws_access_key_id="accesskeyid",
            aws_secret_access_key="secretkey",
            use_host_credentials=True,
        )
        self.challenge.slug = "{}-{}".format(
            self.challenge.title.replace(" ", "-").lower(), self.challenge.pk
        )[:199]
        self.challenge.save()

        self.aws_keys = {
            "AWS_ACCOUNT_ID": self.challenge.aws_account_id,
            "AWS_ACCESS_KEY_ID": self.challenge.aws_access_key_id,
            "AWS_SECRET_ACCESS_KEY": self.challenge.aws_secret_access_key,
            "AWS_REGION": self.challenge.aws_region,
        }
        self.client.force_authenticate(user=self.user)
        self.ecr_client = boto3.client("ecr", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"), aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"), aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),)
        self.sts_client = boto3.client("sts", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"), aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"), aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),)
    def test_get_file_content(self):
        test_file_content = utils.get_file_content(self.test_file_path, "rb")
        expected = "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n"
        self.assertEqual(test_file_content.decode(), expected)

    def test_convert_to_aws_ecr_compatible_format(self):
        input = "Test Convert to Compatible!"
        expected = "test-convert-to-compatible!"
        response = utils.convert_to_aws_ecr_compatible_format(input)
        assert expected == response

    def test_convert_to_aws_federated_user_format(self):
        input = "1234asdf!@#$%^&*(),.-= "
        expected = "1234asdf@,.-=-"
        response = utils.convert_to_aws_federated_user_format(input)
        assert expected == response
        
    def test_get_aws_credentials_for_challenge(self):
        expected = self.aws_keys
        response = utils.get_aws_credentials_for_challenge(self.challenge.pk)
        assert expected == response
        
        
@mock_ecr
@mock_sts
class TestECRRepository(BaseTestCase):
    def setup(self):
        super(TestECRRepository, self).setup()

    @mock.patch("base.utils.get_boto3_client")
    def test_get_or_create_ecr_repository_when_repository_exists(self, client):
        client.return_value = self.ecr_client
        expected = self.ecr_client.create_repository(repositoryName="TestRepo")
        self.aws_keys["AWS_ACCOUNT_ID"] = expected["repository"]["registryId"]
        response = utils.get_or_create_ecr_repository("TestRepo", self.aws_keys)
        assert expected["repository"] == response[0]
        self.aws_keys["AWS_ACCOUNT_ID"] = self.challenge.aws_account_id

    @mock.patch("base.utils.get_boto3_client")
    def test_get_or_create_ecr_repository_when_repository_does_not_exist(self, client):
        client.return_value = self.ecr_client
        response = utils.get_or_create_ecr_repository("TestRepo", self.aws_keys)
        expected = self.ecr_client.describe_repositories(repositoryNames=["TestRepo"])
        assert response == (expected["repositories"][0], True)

    @mock.patch("base.utils.get_boto3_client")
    def test_create_federated_user(self, client):
        client.return_value = self.sts_client
        expected = {
            'Credentials': {
                'AccessKeyId': 'AKIAIOSFODNN7EXAMPLE', 
                'SecretAccessKey': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYzEXAMPLEKEY', 
                'SessionToken': 'AQoDYXdzEPT//////////wEXAMPLEtc764bNrC9SAPBSM22wDOk4x4HIZ8j4FZTwdQWLWsKWHGBuFqwAeMicRXmxfpSPfIeoIYRqTflfKD8YUuwthAx7mSEI/qkPpKPi/kMcGdQrmGdeehM4IC1NtBmUpp2wUE8phUZampKsburEDy0KPkyQDYwT7WZ0wq5VSXDvp75YU9HFvlRd8Tx6q6fE8YQcHNVXAkiY9q6d+xo0rKwT38xVqr7ZD0u0iPPkUL64lIZbqBAz+scqKmlzm8FDrypNC9Yjc8fPOLn9FX9KSYvKTr4rvx3iSIlTJabIQwj2ICCR/oLxBA==', 
                'Expiration': datetime.datetime(2020, 1, 22, 8, 30, 27, 186000, tzinfo=tzlocal())
            }, 
            'FederatedUser': {
                'FederatedUserId': '123456789012:testTeam',
                'Arn': 'arn:aws:sts::123456789012:federated-user/testTeam'
            }, 
            'PackedPolicySize': 6, 
            'ResponseMetadata': {
                'RequestId': 'c6104cbe-af31-11e0-8154-cbc7ccf896c7',
                'HTTPStatusCode': 200, 
                'HTTPHeaders': {'server': 'amazon.com'}, 'RetryAttempts': 0
            }
        }

        response = utils.create_federated_user("testTeam", "testRepo", self.aws_keys)
        print(response)
        assert response == expected

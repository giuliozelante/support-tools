# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the GitHub Services."""

# pylint: disable=missing-docstring,protected-access

import collections
import json
import unittest
import urlparse

import github_issue_converter
import github_services
import issues

from issues_test import DEFAULT_USERNAME
from issues_test import SINGLE_COMMENT
from issues_test import SINGLE_ISSUE
from issues_test import COMMENT_ONE
from issues_test import COMMENT_TWO
from issues_test import COMMENT_THREE
from issues_test import COMMENTS_DATA
from issues_test import NO_ISSUE_DATA
from issues_test import USER_MAP
from issues_test import REPO


# The GitHub username.
GITHUB_USERNAME = DEFAULT_USERNAME
# The GitHub repo name.
GITHUB_REPO = REPO
# The GitHub oauth token.
GITHUB_TOKEN = "oauth_token"
# The URL used for calls to GitHub.
GITHUB_API_URL = "https://api.github.com"


class TestIssueExporter(unittest.TestCase):
  """Tests for the IssueService."""

  def setUp(self):
    self.github_service = github_services.FakeGitHubService(GITHUB_USERNAME,
                                                            GITHUB_REPO,
                                                            GITHUB_TOKEN)
    self.github_user_service = github_services.UserService(
        self.github_service)
    self.github_issue_service = github_services.IssueService(
        self.github_service, comment_delay=0)
    self.issue_exporter = issues.IssueExporter(
        self.github_issue_service, self.github_user_service,
        NO_ISSUE_DATA, GITHUB_REPO, USER_MAP)
    self.issue_exporter.Init()

    self.TEST_ISSUE_DATA = [
        {
            "id": "1",
            "number": "1",
            "title": "Title1",
            "state": "open",
            "comments": {
                "items": [COMMENT_ONE, COMMENT_TWO, COMMENT_THREE],
            },
            "labels": ["Type-Issue", "Priority-High"],
            "owner": {"kind": "projecthosting#issuePerson",
                      "name": "User1"
                     },
        },
        {
            "id": "2",
            "number": "2",
            "title": "Title2",
            "state": "closed",
            "owner": {"kind": "projecthosting#issuePerson",
                      "name": "User2"
                     },
            "labels": [],
            "comments": {
                "items": [COMMENT_ONE],
            },
        },
        {
            "id": "3",
            "number": "3",
            "title": "Title3",
            "state": "closed",
            "comments": {
                "items": [COMMENT_ONE, COMMENT_TWO],
            },
            "labels": ["Type-Defect"],
            "owner": {"kind": "projecthosting#issuePerson",
                      "name": "User3"
                     }
        }]


  def testGetAllPreviousIssues(self):
    self.assertEqual(0, len(self.issue_exporter._previously_created_issues))
    content = [{"number": 1, "title": "issue_title", "comments": 2}]
    self.github_service.AddResponse(content=content)
    self.issue_exporter._GetAllPreviousIssues()
    self.assertEqual(1, len(self.issue_exporter._previously_created_issues))
    self.assertTrue(
        "issue_title" in self.issue_exporter._previously_created_issues)

    previous_issue = (
        self.issue_exporter._previously_created_issues["issue_title"])
    self.assertEqual(1, previous_issue["id"])
    self.assertEqual("issue_title", previous_issue["title"])
    self.assertEqual(2, previous_issue["comment_count"])

  def testCreateIssue(self):
    content = {"number": 1234}
    self.github_service.AddResponse(content=content)

    issue_number = self.issue_exporter._CreateIssue(SINGLE_ISSUE)
    self.assertEqual(1234, issue_number)

  def testCreateIssueFailedOpenRequest(self):
    self.github_service.AddFailureResponse()
    with self.assertRaises(issues.ServiceError):
      self.issue_exporter._CreateIssue(SINGLE_ISSUE)

  def testCreateIssueFailedCloseRequest(self):
    content = {"number": 1234}
    self.github_service.AddResponse(content=content)
    self.github_service.AddFailureResponse()
    issue_number = self.issue_exporter._CreateIssue(SINGLE_ISSUE)
    self.assertEqual(1234, issue_number)

  def testCreateComments(self):
    self.assertEqual(0, self.issue_exporter._comment_number)
    self.issue_exporter._CreateComments(COMMENTS_DATA, 1234, SINGLE_ISSUE)
    self.assertEqual(4, self.issue_exporter._comment_number)

  def testCreateCommentsFailure(self):
    self.github_service.AddFailureResponse()
    self.assertEqual(0, self.issue_exporter._comment_number)
    with self.assertRaises(issues.ServiceError):
      self.issue_exporter._CreateComments(COMMENTS_DATA, 1234, SINGLE_ISSUE)

  def testStart(self):
    self.issue_exporter._issue_json_data = self.TEST_ISSUE_DATA

    # Note: Some responses are from CreateIssues, others are from CreateComment.
    self.github_service.AddResponse(content={"number": 1})
    self.github_service.AddResponse(content={"number": 10})
    self.github_service.AddResponse(content={"number": 11})
    self.github_service.AddResponse(content={"number": 2})
    self.github_service.AddResponse(content={"number": 20})
    self.github_service.AddResponse(content={"number": 3})
    self.github_service.AddResponse(content={"number": 30})

    self.issue_exporter.Start()

    self.assertEqual(3, self.issue_exporter._issue_total)
    self.assertEqual(3, self.issue_exporter._issue_number)
    # Comment counts are per issue and should match the numbers from the last
    # issue created, minus one for the first comment, which is really
    # the issue description.
    self.assertEqual(1, self.issue_exporter._comment_number)
    self.assertEqual(1, self.issue_exporter._comment_total)

  def testStart_SkipDeletedComments(self):
    comment = {
        "content": "one",
        "id": 1,
        "published": "last year",
        "author": {"name": "user@email.com"},
        "updates": {
            "labels": ["added-label", "-removed-label"],
            },
        }

    self.issue_exporter._issue_json_data = [
        {
            "id": "1",
            "number": "1",
            "title": "Title1",
            "state": "open",
            "comments": {
                "items": [
                    COMMENT_ONE,
                    comment,
                    COMMENT_TWO,
                    comment],
            },
            "labels": ["Type-Issue", "Priority-High"],
            "owner": {"kind": "projecthosting#issuePerson",
                      "name": "User1"
                     },
        }]

    # Verify the comment data from the test issue references all comments.
    self.github_service.AddResponse(content={"number": 1})
    self.issue_exporter.Start()
    # Remember, the first comment is for the issue.
    self.assertEqual(3, self.issue_exporter._comment_number)
    self.assertEqual(3, self.issue_exporter._comment_total)

    # Set the deletedBy information for the comment object, now they
    # should be ignored by the export.
    comment["deletedBy"] = {}

    self.github_service.AddResponse(content={"number": 1})
    self.issue_exporter._previously_created_issues = {}
    self.issue_exporter.Start()
    self.assertEqual(1, self.issue_exporter._comment_number)
    self.assertEqual(1, self.issue_exporter._comment_total)

  def testStart_SkipAlreadyCreatedIssues(self):
    self.issue_exporter._previously_created_issues["Title1"] = {
        "id": 1,
        "title": "Title1",
        "comment_count": 3
        }
    self.issue_exporter._previously_created_issues["Title2"] = {
        "id": 2,
        "title": "Title2",
        "comment_count": 1
        }
    self.issue_exporter._issue_json_data = self.TEST_ISSUE_DATA

    self.github_service.AddResponse(content={"number": 3})

    self.issue_exporter.Start()

    self.assertEqual(2, self.issue_exporter._skipped_issues)
    self.assertEqual(3, self.issue_exporter._issue_total)
    self.assertEqual(3, self.issue_exporter._issue_number)

  def testStart_ReAddMissedComments(self):
    self.issue_exporter._previously_created_issues["Title1"] = {
        "id": 1,
        "title": "Title1",
        "comment_count": 1  # Missing 2 comments.
        }
    self.issue_exporter._issue_json_data = self.TEST_ISSUE_DATA

    # First requests to re-add comments, then create issues.
    self.github_service.AddResponse(content={"number": 11})
    self.github_service.AddResponse(content={"number": 12})

    self.github_service.AddResponse(content={"number": 2})
    self.github_service.AddResponse(content={"number": 3})

    self.issue_exporter.Start()
    self.assertEqual(1, self.issue_exporter._skipped_issues)
    self.assertEqual(3, self.issue_exporter._issue_total)
    self.assertEqual(3, self.issue_exporter._issue_number)


if __name__ == "__main__":
  unittest.main(buffer=True)

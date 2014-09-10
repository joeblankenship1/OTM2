# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

from datetime import datetime, timedelta

from django.contrib.gis.geos import Point
from django.contrib.sites.models import Site

from treemap.models import Plot
from treemap.tests.base import OTMTestCase
from treemap.tests import (make_instance, make_commander_user,
                           make_admin_user, make_request)

from otm_comments.models import (EnhancedThreadedComment,
                                 EnhancedThreadedCommentFlag)
from otm_comments.views import (comment_moderation, flag, unflag,
                                archive, unarchive, hide_flags,
                                hide, show)


def make_comment(model, user, text='testing 1 2 3', **kwargs):
    site = Site.objects.all()[0]
    return EnhancedThreadedComment.objects.create(
        content_object=model, user=user, comment=text, site=site, **kwargs)


class CommentTestCase(OTMTestCase):
    # A base class for comment tests
    def setUp(self):
        super(CommentTestCase, self).setUp()
        self.instance = make_instance()
        self.user = make_commander_user(self.instance)
        self.admin = make_admin_user(self.instance)
        self.plot = Plot(geom=Point(0, 0), instance=self.instance)
        self.plot.save_with_user(self.user)


class EnhancedCommentTest(CommentTestCase):
    def test_creating_comment_on_plots_sets_instance(self):
        ec = make_comment(self.plot, self.user)

        self.assertEqual(self.instance, ec.instance)

        ec.save()

        retrieved_ec = EnhancedThreadedComment.objects.get(pk=ec.pk)

        self.assertEqual(self.instance, retrieved_ec.instance)


class CommentReviewTest(CommentTestCase):
    def _get_comments(self, **get_params):
        context = comment_moderation(make_request(get_params), self.instance)

        return context['comments']

    def test_comments_pagination(self):
        make_comment(self.plot, self.user)
        make_comment(self.plot, self.user)
        make_comment(self.plot, self.user)
        make_comment(self.plot, self.user)
        make_comment(self.plot, self.user)

        comments_p1 = self._get_comments(size='2')

        self.assertEqual(False, comments_p1.has_previous())
        self.assertEqual(1, comments_p1.number)
        self.assertEqual(3, comments_p1.paginator.num_pages)
        self.assertEqual(2, len(comments_p1))
        self.assertEqual(2, comments_p1.next_page_number())

    def test_archived_filter(self):
        ecomment1 = make_comment(self.plot, self.user, is_archived=True,
                                 is_removed=False)
        ecomment2 = make_comment(self.plot, self.user, is_archived=False,
                                 is_removed=True)

        comments = self._get_comments()

        # Without any parameters, you get all comments
        self.assertEqual(2, len(comments))

        comments = self._get_comments(archived='True')

        self.assertEqual(1, len(comments))
        self.assertEqual(ecomment1, comments[0])

        comments = self._get_comments(archived='False')

        self.assertEqual(1, len(comments))
        self.assertEqual(ecomment2, comments[0])

    def test_hidden_filter(self):
        ecomment1 = make_comment(self.plot, self.user, is_archived=True,
                                 is_removed=False)
        ecomment2 = make_comment(self.plot, self.user, is_archived=False,
                                 is_removed=True)

        comments = self._get_comments()

        # Without any parameters, you get all comments
        self.assertEqual(2, len(comments))

        comments = self._get_comments(removed='True')

        self.assertEqual(1, len(comments))
        self.assertEqual(ecomment2, comments[0])

        comments = self._get_comments(removed='False')

        self.assertEqual(1, len(comments))
        self.assertEqual(ecomment1, comments[0])

    def test_sorting(self):
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)

        ecomment1 = make_comment(self.plot, self.user, submit_date=today)
        ecomment2 = make_comment(self.plot, self.user, submit_date=last_week)
        ecomment3 = make_comment(self.plot, self.user, submit_date=yesterday)

        comments = self._get_comments()

        # The default sort order is submit_date, with the most recent first
        self.assertEqual(3, len(comments))
        self.assertEqual(ecomment1, comments[0])
        self.assertEqual(ecomment3, comments[1])
        self.assertEqual(ecomment2, comments[2])

        # You can sort on arbitrary fields
        comments = self._get_comments(sort='id')

        self.assertEqual(3, len(comments))
        self.assertEqual(ecomment1, comments[0])
        self.assertEqual(ecomment2, comments[1])
        self.assertEqual(ecomment3, comments[2])

        comments = self._get_comments(sort='-id')

        # Adding a '-' reverses the sort order
        self.assertEqual(3, len(comments))
        self.assertEqual(ecomment3, comments[0])
        self.assertEqual(ecomment2, comments[1])
        self.assertEqual(ecomment1, comments[2])


def _comment_ids_to_params(*args):
    return {'comment-ids': ','.join(str(arg) for arg in args)}


class CommentModerationTestCase(CommentTestCase):
    def setUp(self):
        super(CommentModerationTestCase, self).setUp()
        self.comment = make_comment(self.plot, self.user)
        self.comment2 = make_comment(self.plot, self.user)


class CommentFlagTestCase(CommentModerationTestCase):
    def test_flagging(self):
        self.assertFalse(self.comment.is_flagged)
        self.assertFalse(self.comment.is_flagged_by_user(self.user))
        self.assertFalse(self.comment.is_flagged_by_user(self.admin))

        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)

        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertEqual(1, EnhancedThreadedCommentFlag.objects
                         .all().count(),
                         "There should be 1 comment flag row created")
        self.assertTrue(updated_comment.is_flagged)
        self.assertTrue(updated_comment.is_flagged_by_user(self.user))
        self.assertFalse(updated_comment.is_flagged_by_user(self.admin))

    def test_can_unflag(self):
        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertTrue(updated_comment.is_flagged)

        req = make_request(user=self.user, method='POST')
        unflag(req, self.instance, self.comment.id)
        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertFalse(updated_comment.is_flagged)

    def test_cant_double_flag(self):
        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        self.assertEqual(1, EnhancedThreadedCommentFlag.objects
                         .all().count(),
                         "There should be 1 comment flag row created")

        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        self.assertEqual(1, EnhancedThreadedCommentFlag.objects
                         .all().count(),
                         "There should still be 1 comment flag row")

    def test_flag_unflag_flag_makes_two_rows(self):
        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        self.assertEqual(1, EnhancedThreadedCommentFlag.objects
                         .all().count(),
                         "There should be 1 comment flag row created")

        req = make_request(user=self.user, method='POST')
        unflag(req, self.instance, self.comment.id)
        self.assertEqual(1, EnhancedThreadedCommentFlag.objects
                         .all().count(),
                         "There should still 1 comment flag row after unflag")

        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        self.assertEqual(2, EnhancedThreadedCommentFlag.objects.all().count(),
                         "There should be 2 comment flag rows")

    def test_flag_hide_flags_flag_makes_two_rows(self):
        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        self.assertEqual(1, EnhancedThreadedCommentFlag.objects.all().count(),
                         "There should be 1 comment flag row created")

        req = make_request(user=self.admin, method='POST',
                           params=_comment_ids_to_params(self.comment.id))
        hide_flags(req, self.instance)
        self.assertEqual(1, EnhancedThreadedCommentFlag.objects.all().count(),
                         "There should still 1 comment flag row after unflag")

        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        self.assertEqual(2, EnhancedThreadedCommentFlag.objects.all().count(),
                         "There should be 2 comment flag rows")

    def test_multiple_flags(self):
        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        req = make_request(user=self.admin, method='POST')
        flag(req, self.instance, self.comment.id)

        self.assertEqual(2, EnhancedThreadedCommentFlag.objects.all().count(),
                         "There should be 2 comment flag rows")
        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertTrue(updated_comment.is_flagged)

        req = make_request(user=self.user, method='POST')
        unflag(req, self.instance, self.comment.id)
        self.assertEqual(2, EnhancedThreadedCommentFlag.objects.all().count(),
                         "Unflagging should not remove comment rows")
        self.assertTrue(updated_comment.is_flagged,
                        "Removing 1 of 2 flags leaves the comment flagged")
        self.assertFalse(updated_comment.is_flagged_by_user(self.user))
        self.assertTrue(updated_comment.is_flagged_by_user(self.admin))

    def test_hide_flags(self):
        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment.id)
        req = make_request(user=self.admin, method='POST')
        flag(req, self.instance, self.comment.id)
        self.assertEqual(2, EnhancedThreadedCommentFlag.objects
                         .filter(hidden=False).count(),
                         "There should be 2 non-hidden comment flag rows")
        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertTrue(updated_comment.is_flagged_by_user(self.user))
        self.assertTrue(updated_comment.is_flagged_by_user(self.admin))

        req = make_request(user=self.admin, method='POST',
                           params=_comment_ids_to_params(self.comment.id))
        hide_flags(req, self.instance)
        self.assertEqual(2, EnhancedThreadedCommentFlag.objects
                         .filter(hidden=True).count(),
                         "There should be 2 hidden comment flag rows")
        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertFalse(updated_comment.is_flagged_by_user(self.user))
        self.assertFalse(updated_comment.is_flagged_by_user(self.admin))

    def test_batch_hide_flags(self):
        req = make_request(user=self.admin, method='POST')
        flag(req, self.instance, self.comment.id)

        req = make_request(user=self.user, method='POST')
        flag(req, self.instance, self.comment2.id)

        self.assertEqual(2, EnhancedThreadedCommentFlag.objects
                         .filter(hidden=False).count(),
                         "There should be 2 non-hidden comment flag rows")

        req = make_request(user=self.admin, method='POST',
                           params=_comment_ids_to_params(
                               self.comment.id, self.comment2.id))
        hide_flags(req, self.instance)
        self.assertEqual(2, EnhancedThreadedCommentFlag.objects
                         .filter(hidden=True).count(),
                         "There should be 2 hidden comment flag rows")


class CommentArchiveTestCase(CommentModerationTestCase):
    def test_archive(self):
        self.assertFalse(self.comment.is_archived)
        req = make_request(user=self.user, method='POST',
                           params=_comment_ids_to_params(self.comment.id))
        archive(req, self.instance)

        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertTrue(updated_comment.is_archived)

    def test_unarchive(self):
        self.comment.is_archived = True
        self.comment.save()

        req = make_request(user=self.user, method='POST',
                           params=_comment_ids_to_params(self.comment.id))
        unarchive(req, self.instance)

        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertFalse(updated_comment.is_archived)

    def test_batch_archive(self):
        self.assertFalse(self.comment.is_archived)
        self.assertFalse(self.comment2.is_archived)
        req = make_request(user=self.user, method='POST',
                           params=_comment_ids_to_params(
                               self.comment.id, self.comment2.id))
        archive(req, self.instance)
        updated_comments = EnhancedThreadedComment.objects.all()
        for updated_comment in updated_comments:
            self.assertTrue(updated_comment.is_archived)

    def test_flagging_unarchives(self):
        self.comment.is_archived = True
        self.comment.save()

        req = make_request(user=self.user, method='POST',
                           params=_comment_ids_to_params(self.comment.id))
        flag(req, self.instance, self.comment.id)
        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertFalse(updated_comment.is_archived)


class CommentHideAndShowTestCase(CommentModerationTestCase):
    def test_hide(self):
        self.assertFalse(self.comment.is_removed)
        req = make_request(user=self.user, method='POST',
                           params=_comment_ids_to_params(
                               self.comment.id))
        hide(req, self.instance)

        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertTrue(updated_comment.is_removed)

    def test_show(self):
        self.comment.is_removed = True
        self.comment.save()

        req = make_request(user=self.user, method='POST',
                           params=_comment_ids_to_params(
                               self.comment.id))
        show(req, self.instance)

        updated_comment = EnhancedThreadedComment.objects.get(
            pk=self.comment.id)
        self.assertFalse(updated_comment.is_removed)

    def test_batch_hide(self):
        self.assertFalse(self.comment.is_removed)
        self.assertFalse(self.comment2.is_removed)
        req = make_request(user=self.user, method='POST',
                           params=_comment_ids_to_params(
                               self.comment.id, self.comment2.id))
        hide(req, self.instance)
        updated_comments = EnhancedThreadedComment.objects.all()
        for updated_comment in updated_comments:
            self.assertTrue(updated_comment.is_removed)

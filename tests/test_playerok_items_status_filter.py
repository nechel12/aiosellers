import unittest

from aiosellers.playerok.graphql import GraphQLQuery


class PublicItemsFilterTests(unittest.TestCase):
    def test_public_items_use_approved_only_status(self):
        query = GraphQLQuery.get_items(game_id="game-1", count=10)

        status = query["variables"]["filter"]["status"]
        self.assertEqual(status, ["APPROVED"])
        self.assertNotIn("PENDING_MODERATION", status)
        self.assertNotIn("PENDING_APPROVAL", status)

    def test_owner_items_keep_approved_only_status(self):
        query = GraphQLQuery.get_items(user_id="seller-1", count=10)

        self.assertEqual(query["variables"]["filter"]["status"], ["APPROVED"])

import unittest

from app.classifier.document_classifier import DocumentClassifier


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.classifier = DocumentClassifier()

    def test_classifies_notification_from_title(self):
        result = self.classifier.classify("Companies Act notification G.S.R. 123(E)", "")
        self.assertEqual(result.category, "Notifications")
        self.assertGreaterEqual(result.rule_score, 0.9)

    def test_classifies_rules_and_amendments(self):
        self.assertEqual(self.classifier.classify("Companies (Accounts) Rules, 2014", "").category, "Rules")
        self.assertEqual(self.classifier.classify("Amendment to Companies Rules", "").category, "Amendments")

    def test_ambiguous_document_is_other(self):
        result = self.classifier.classify("Document", "Company references without a document type")
        self.assertEqual(result.category, "Other")
        self.assertLess(result.rule_score, 0.5)

    def test_explicit_act_title_wins_over_generic_body_mentions(self):
        result = self.classifier.classify("Companies Act, 2013", "This Act refers to several notifications and orders.")
        self.assertEqual(result.category, "Acts")

    def test_all_required_categories_are_available(self):
        examples = {
            "Acts": "Companies Act, 2013",
            "Notifications": "Notification G.S.R. 123(E)",
            "Circulars": "Circular on Companies",
            "Rules": "Companies (Accounts) Rules, 2014",
            "Orders": "Order under Companies Act",
            "Amendments": "Amendment to Companies Rules",
            "Other": "General document",
        }
        for expected, title in examples.items():
            with self.subTest(expected=expected):
                self.assertEqual(self.classifier.classify(title, "").category, expected)

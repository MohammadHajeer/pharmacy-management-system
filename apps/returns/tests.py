from django.test import SimpleTestCase

from .models import CustomerReturnLine, PostedStatus, ReturnStatus


class ReturnChoiceTests(SimpleTestCase):
    def test_return_and_refund_states_match_phase_one(self):
        self.assertEqual(set(ReturnStatus.values), {"DRAFT", "POSTED", "VOID"})
        self.assertEqual(set(PostedStatus.values), {"POSTED", "REVERSED"})

    def test_return_conditions_match_phase_one(self):
        self.assertEqual(
            set(CustomerReturnLine.Condition.values),
            {"RESALABLE", "NON_RESELLABLE"},
        )

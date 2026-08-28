from django.test import SimpleTestCase

from .models import CustomerRefund, CustomerReturnLine, RefundStatus, ReturnStatus


class ReturnChoiceTests(SimpleTestCase):
    def test_return_and_refund_states_match_phase_one(self):
        self.assertEqual(set(ReturnStatus.values), {"DRAFT", "POSTED", "VOID"})
        self.assertEqual(set(RefundStatus.values), {"POSTED"})
        self.assertEqual(CustomerRefund._meta.get_field("status").default, "POSTED")
        self.assertIn(
            "returns_customer_refund_posted_only",
            {constraint.name for constraint in CustomerRefund._meta.constraints},
        )

    def test_return_conditions_match_phase_one(self):
        self.assertEqual(
            set(CustomerReturnLine.Condition.values),
            {"RESELLABLE", "NON_RESELLABLE"},
        )

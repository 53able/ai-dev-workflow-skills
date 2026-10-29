import unittest

from shop import invoice


class InvoiceTest(unittest.TestCase):
    def test_first_invoice_goes_to_window_a(self):
        self.assertEqual(invoice.queue_for(invoice.next_number()), "A")


if __name__ == "__main__":
    unittest.main()

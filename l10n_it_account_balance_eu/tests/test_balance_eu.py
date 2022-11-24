from datetime import datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


def _get_balance_line_amount(bal_lines, line_code):
    for line in bal_lines:
        if line["code"] == line_code:
            return line["amount"]


@tagged("-at_install", "post_install")
class TestBalanceEU(TransactionCase):
    def setUp(self):
        # add env on cls and many other things
        super(TestBalanceEU, self).setUp()

    def _add_move(self, ref, journal, date, debit_list, credit_list):
        lines = []
        for i in debit_list:
            acc_id = self.env["account.account"].search([("code", "=", i[0])])
            if not acc_id:
                self.assertTrue(acc_id)
            else:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "debit": i[1],
                            "credit": 0,
                            "account_id": acc_id.id,
                        },
                    )
                )
        for i in credit_list:
            acc_id = self.env["account.account"].search([("code", "=", i[0])])
            if not acc_id:
                self.assertTrue(acc_id)
            else:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "debit": 0,
                            "credit": i[1],
                            "account_id": acc_id.id,
                        },
                    )
                )
        move_vals = {
            "ref": ref,
            "journal_id": journal.id,
            "date": date,
            "line_ids": lines,
        }
        move = self.env["account.move"].create(move_vals)
        move.action_post()

    def _get_balance_values(self, date_start, date_end, values_precision):
        wiz_balance_eu = self.env["account.balance.eu.wizard"].create(
            {
                "date_from": date_start,
                "date_to": date_end,
                "values_precision": values_precision,
                "hide_acc_amount_0": True,
                "only_posted_move": True,
                "ignore_closing_move": True,
            }
        )
        form_data = wiz_balance_eu.get_data()
        return self.env[
            "report.l10n_it_account_balance_eu.balance_eu_html_report"
        ]._get_report_values(wiz_balance_eu, data=form_data)

    def test_balance_eu_1(self):
        journal = self.env["account.journal"].search(
            [("company_id", "=", self.env.user.company_id.id)], limit=1
        )
        self._add_move(
            "vendita a cliente",
            journal,
            datetime(2023, 3, 1).date(),
            (("150100", 37.52),),  # debit
            (("260100", 6.77), ("310100", 30.75)),  # credit
        )
        self._add_move(
            "incasso da cliente",
            journal,
            datetime(2023, 4, 5).date(),
            (("182001", 37.52),),  # debit
            (("150100", 37.52),),  # credit
        )
        self._add_move(
            "giroconto per generare un delta nel PATRIMONIALE "
            + "su bilancio UE arrotondato alla unità",
            journal,
            datetime(2023, 4, 1).date(),
            (
                ("110100", 100.10),
                ("110600", 200.20),
                ("110800", 300.30),
                ("120500", 399.40),  # debit
            ),
            (("210100", 1000),),  # credit
        )
        self._add_move(
            "giroconto per generare un delta nel CONTO ECONOMICO "
            + "su bilancio UE arrotondato alla unità",
            journal,
            datetime(2023, 4, 1).date(),
            (
                ("410100", 100.10),
                ("411100", 200.20),
                ("430100", 300.30),
                ("440100", 399.40),  # debit
            ),
            (("310300", 1000),),  # credit
        )
        # checks with decimals
        bal_values = self._get_balance_values(
            datetime(2023, 1, 1).date(), datetime(2023, 12, 31).date(), "d"
        )
        self.assertEqual(bal_values.get("balance_state"), "OK")
        bal_lines = bal_values.get("balance_ue_lines")
        self.assertEqual(_get_balance_line_amount(bal_lines, "PA.C21a"), 0)
        self.assertEqual(_get_balance_line_amount(bal_lines, "PA"), 1037.52)
        self.assertEqual(_get_balance_line_amount(bal_lines, "E.A"), 1030.75)
        self.assertEqual(_get_balance_line_amount(bal_lines, "E=F"), 30.75)
        # checks without decimals
        bal_values = self._get_balance_values(
            datetime(2023, 1, 1).date(), datetime(2023, 12, 31).date(), "u"
        )
        self.assertEqual(bal_values.get("balance_state"), "OK")
        bal_lines = bal_values.get("balance_ue_lines")
        self.assertEqual(_get_balance_line_amount(bal_lines, "PA.C21a"), 0)
        self.assertEqual(_get_balance_line_amount(bal_lines, "PA"), 1037)
        self.assertEqual(_get_balance_line_amount(bal_lines, "E.A"), 1030)
        self.assertEqual(_get_balance_line_amount(bal_lines, "E=F"), 31)

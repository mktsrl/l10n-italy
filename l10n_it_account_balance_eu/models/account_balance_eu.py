# Copyright 2022 MKT srl
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import operator

from babel.numbers import format_decimal

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


def my_round(val, precision):
    # il round arrotonda il 5 al pari più vicino (1.5 -> 2 e 2.5 -> 2)
    # aggiungo un infinitesimo per farlo arrotondare sempre per eccesso
    return round(val + 1e-10, precision)


class AccountBalanceEU(models.Model):
    _name = "account.balance.eu"
    _description = "Account Balance EU line"
    zone_bal = fields.Selection(
        [
            ("PA", "Assets"),
            ("PP", "Liabilities"),
            ("EC", "Income statement"),
        ],
        string="Zone",
        required=True,
    )
    code = fields.Char(string="Code", size=8)
    name = fields.Char(
        string="Description",
    )
    long_desc = fields.Char(
        string="Complete Description",
    )
    sign_calculation = fields.Selection(
        selection=[
            ("-", "Subtract"),
            ("", "Add"),
        ],
        string="-",
    )
    sign_display = fields.Selection(
        selection=[
            ("+", "Positive"),
            ("-", "Negative"),
        ],
        string="Sign",
    )
    sequence = fields.Integer(
        string="#",
        required=False,
    )
    tag_xbrl = fields.Char(
        string="Name XBRL",
    )
    parent_id = fields.Many2one(
        comodel_name="account.balance.eu",
        string="Parent",
        index=True,
    )
    child_ids = fields.One2many(
        comodel_name="account.balance.eu",
        inverse_name="parent_id",
        string="Childs",
    )
    complete_name = fields.Char(
        string="Complete Name",
        compute="_compute_complete_name",
        store=True,
    )

    def get_parent_path(self):
        self.ensure_one()
        if self.parent_id:
            line = self.parent_id.get_parent_path()
        else:
            line = ""
        return line + self.name + " / "  #

    @api.depends("code", "name", "parent_id", "parent_id.complete_name")
    def _compute_complete_name(self):
        for line in self:
            if line.parent_id:
                p = line.parent_id.get_parent_path()
            else:
                p = ""
            line.complete_name = "[%s] %s%s" % (line.code, p, line.name)

    def name_get(self):
        res = []
        for line in self:
            res.append((line.id, line.complete_name))
        return res

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        if not args:
            args = []
        if name:
            records = self.search(
                [("complete_name", operator, name)] + args,
                limit=limit,
            )
        else:
            records = self.search(args, limit=limit)
        return records.name_get()

    @api.constrains("code", "zone_bal")
    def _check_code_zone(self):
        for line in self:
            if (line.zone_bal == "PA") and (not line.code.startswith("PA")):
                raise ValidationError(_("ASSETS codes must starting by PA"))
            elif (line.zone_bal == "PP") and (not line.code.startswith("PP")):
                raise ValidationError(_("LIABILITIES codes must starting by PP"))
            elif (line.zone_bal == "EC") and (not line.code.startswith("E")):
                raise ValidationError(_("INCOME STATEMENT codes must starting by E"))

    @api.model
    def account_balance_eu_debit_association(
        self, acc_code, account_balance_eu_id, force_update=False
    ):
        acc_ids = self.env["account.account"].search([("code", "=ilike", acc_code)])
        for acc_id in acc_ids:
            if (not acc_id.account_balance_eu_debit_id) or (
                force_update
                and (acc_id.account_balance_eu_debit_id.id != account_balance_eu_id)
            ):
                acc_id.write({"account_balance_eu_debit_id": account_balance_eu_id})

    @api.model
    def account_balance_eu_credit_association(
        self, acc_code, account_balance_eu_id, force_update=False
    ):
        acc_ids = self.env["account.account"].search([("code", "=ilike", acc_code)])
        for acc_id in acc_ids:
            if (not acc_id.account_balance_eu_credit_id) or (
                force_update
                and (acc_id.account_balance_eu_debit_id.id != account_balance_eu_id)
            ):
                acc_id.write({"account_balance_eu_credit_id": account_balance_eu_id})

    def cal_balance_ue_line_amount(self, balance_ue_lines, code):
        total_amount = 0
        rounded_amount = 0
        account_balance_eu_child_ids = self.env["account.balance.eu"].search(
            [("parent_id", "=", balance_ue_lines[code]["balance_line"].id)]
        )
        for child in account_balance_eu_child_ids:
            if child.child_ids:
                self.cal_balance_ue_line_amount(balance_ue_lines, child.code)
            if child.sign_calculation == "-":
                rounded_amount -= balance_ue_lines[child.code]["rounded_amount"]
                total_amount -= balance_ue_lines[child.code]["total_amount"]
            else:
                rounded_amount += balance_ue_lines[child.code]["rounded_amount"]
                total_amount += balance_ue_lines[child.code]["total_amount"]
        balance_ue_lines[code]["rounded_amount"] = my_round(rounded_amount, 2)
        balance_ue_lines[code]["total_amount"] = total_amount

    def add_calc_type_domain(self, domain, calc_type, account_balance_eu_id):
        if calc_type == "d":
            domain.append(("account_balance_eu_debit_id", "=", account_balance_eu_id))
        elif calc_type == "a":
            domain.append(("account_balance_eu_credit_id", "=", account_balance_eu_id))
        elif calc_type == "non_assoc":
            domain.append(("account_balance_eu_debit_id", "=", False))
            domain.append(("account_balance_eu_credit_id", "=", False))

    def get_account_list_amount(
        self,
        company_id,
        currency_precision,
        date_from,
        date_to,
        only_posted_move,
        hide_acc_amount_0,
        ignore_closing_move,
        calc_type,
        account_balance_eu_id,
        sign_display,
        balance_line_amount,
        account_list,
    ):
        domain = []
        domain.append(("company_id", "=", company_id))
        self.add_calc_type_domain(domain, calc_type, account_balance_eu_id)
        acc_model = self.env["account.account"]
        account_ids = acc_model.read_group(
            domain,
            fields=[
                "id",
                "code",
                "name",
                "account_balance_eu_debit_id",
                "account_balance_eu_credit_id",
            ],
            groupby=[
                "id",
                "code",
                "name",
                "account_balance_eu_debit_id",
                "account_balance_eu_credit_id",
            ],
            orderby="code",
            lazy=False,
        )
        if account_ids:
            for item in account_ids:
                account_id = False
                for d in item.get("__domain"):
                    if type(d) is tuple and d[0] == "id":
                        account_id = d[2]
                if account_id:
                    acc_credit_id = item.get("account_balance_eu_credit_id")
                    acc_debit_id = item.get("account_balance_eu_debit_id")
                    domain = []
                    domain.append(("company_id", "=", company_id))
                    domain.append(("account_id", "=", account_id))
                    domain.append(("date", ">=", date_from))
                    domain.append(("date", "<=", date_to))
                    if only_posted_move:
                        domain.append(("move_id.state", "=", "posted"))
                    if ignore_closing_move:
                        domain.append(("move_id.closing_type", "!=", "closing"))
                        domain.append(("move_id.closing_type", "!=", "loss_profit"))
                    aml_model = self.env["account.move.line"]
                    amls = aml_model.read_group(
                        domain,
                        ["debit", "credit", "account_id"],
                        ["account_id"],
                        lazy=False,
                    )
                    if amls:
                        for line in amls:
                            acc_amount = my_round(
                                line.get("debit") - line.get("credit"),
                                currency_precision,
                            )
                            if (
                                (calc_type == "non_assoc")  # and (acc_amount != 0)
                                or (
                                    (calc_type == "d")
                                    and ((acc_amount >= 0) or (not acc_credit_id))
                                )
                                or (
                                    (calc_type == "a")
                                    and ((acc_amount < 0) or (not acc_debit_id))
                                )
                            ):
                                if sign_display == "-":
                                    acc_amount = -acc_amount
                                balance_line_amount = balance_line_amount + acc_amount
                                if (not hide_acc_amount_0) or (acc_amount != 0):
                                    account_list.append(
                                        {
                                            "code": item.get("code"),
                                            "desc": item.get("name"),
                                            "amount": acc_amount,
                                        }
                                    )
                    elif not hide_acc_amount_0:
                        account_list.append(
                            {
                                "code": item.get("code"),
                                "desc": item.get("name"),
                                "amount": 0,
                            }
                        )
        return balance_line_amount

    def cal_balance_ue_data(self, form_data):
        balance_ue_lines = {}
        company_id = form_data["company_id"][0]
        currency_precision = (
            self.env["res.currency"].browse(form_data["currency_id"][0]).decimal_places
        )
        date_from = form_data["date_from"]
        date_to = form_data["date_to"]
        only_posted_move = form_data["default_only_posted_move"]
        hide_acc_amount_0 = form_data["default_hide_acc_amount_0"]
        ignore_closing_move = form_data["default_ignore_closing_move"]
        if ignore_closing_move:
            ignore_closing_move = False
            if "account_fiscal_year_closing" in self.env["ir.module.module"].search(
                [("state", "=", "installed")]
            ).mapped("name"):
                move_model = self.env["account.move"]
                if "closing_type" in move_model.fields_get() and move_model.search(
                    [("closing_type", "!=", False)]
                ):
                    ignore_closing_move = True
        account_balance_eu_ids = self.search([])  # env["account.balance.eu"].
        for item in account_balance_eu_ids:
            account_balance_eu_amount = 0
            account_list = []
            if not item.child_ids:
                calcoli = ["d", "a"]  # d=debit a=credit
                for calc_type in calcoli:
                    account_balance_eu_amount = self.get_account_list_amount(
                        company_id,
                        currency_precision,
                        date_from,
                        date_to,
                        only_posted_move,
                        hide_acc_amount_0,
                        ignore_closing_move,
                        calc_type,
                        item.id,
                        item.sign_display,
                        account_balance_eu_amount,
                        account_list,
                    )
            account_list.sort(key=operator.itemgetter("code"))

            if form_data["default_balance_type"] == "u":
                account_balance_eu_amount_rounded = my_round(
                    account_balance_eu_amount, 0
                )
            elif form_data["default_balance_type"] == "d":
                account_balance_eu_amount_rounded = my_round(
                    account_balance_eu_amount, 2
                )
            else:
                account_balance_eu_amount_rounded = account_balance_eu_amount
            balance_ue_lines[item.code] = {
                "balance_line": item,
                "rounded_amount": account_balance_eu_amount_rounded,
                "total_amount": account_balance_eu_amount,
                "account_list": account_list,
            }
        self.cal_balance_ue_line_amount(balance_ue_lines, "E.A")
        self.cal_balance_ue_line_amount(balance_ue_lines, "E.B")
        self.cal_balance_ue_line_amount(balance_ue_lines, "E.C")
        self.cal_balance_ue_line_amount(balance_ue_lines, "E.D")
        self.cal_balance_ue_line_amount(balance_ue_lines, "E.F")
        balance_ue_lines["E=B"]["rounded_amount"] = (
            balance_ue_lines["E.A"]["rounded_amount"]
            - balance_ue_lines["E.B"]["rounded_amount"]
        )
        balance_ue_lines["E=B"]["total_amount"] = (
            balance_ue_lines["E.A"]["total_amount"]
            - balance_ue_lines["E.B"]["total_amount"]
        )
        balance_ue_lines["E=E"]["rounded_amount"] = (
            balance_ue_lines["E=B"]["rounded_amount"]
            + balance_ue_lines["E.C"]["rounded_amount"]
            + balance_ue_lines["E.D"]["rounded_amount"]
        )
        balance_ue_lines["E=E"]["total_amount"] = (
            balance_ue_lines["E=B"]["total_amount"]
            + balance_ue_lines["E.C"]["total_amount"]
            + balance_ue_lines["E.D"]["total_amount"]
        )
        balance_ue_lines["E=F"]["rounded_amount"] = (
            balance_ue_lines["E=E"]["rounded_amount"]
            - balance_ue_lines["E.F"]["rounded_amount"]
        )
        balance_ue_lines["E=F"]["total_amount"] = (
            balance_ue_lines["E=E"]["total_amount"]
            - balance_ue_lines["E.F"]["total_amount"]
        )
        balance_ue_lines["PP=A9"]["rounded_amount"] = balance_ue_lines["E=F"][
            "rounded_amount"
        ]
        balance_ue_lines["PP=A9"]["total_amount"] = balance_ue_lines["E=F"][
            "total_amount"
        ]
        self.cal_balance_ue_line_amount(balance_ue_lines, "PA")
        self.cal_balance_ue_line_amount(balance_ue_lines, "PP")
        balance_ue_lines["PP=A7j2"]["total_amount"] = (
            balance_ue_lines["PA"]["rounded_amount"]
            - balance_ue_lines["PP"]["rounded_amount"]
        ) - (
            balance_ue_lines["PA"]["total_amount"]
            - balance_ue_lines["PP"]["total_amount"]
        )
        if form_data["default_balance_type"] == "u":
            balance_ue_lines["PP=A7j2"]["rounded_amount"] = my_round(
                balance_ue_lines["PP=A7j2"]["total_amount"], 0
            )
        elif form_data["default_balance_type"] == "d":
            balance_ue_lines["PP=A7j2"]["rounded_amount"] = my_round(
                balance_ue_lines["PP=A7j2"]["total_amount"], 2
            )
        else:
            balance_ue_lines["PP=A7j2"]["rounded_amount"] = balance_ue_lines["PP=A7j2"][
                "total_amount"
            ]
        self.cal_balance_ue_line_amount(balance_ue_lines, "PP")
        balance_ue_lines_report_data = []
        for line in balance_ue_lines:
            balance_ue_lines_report_data.append(
                {
                    "code": balance_ue_lines[line]["balance_line"].code,
                    "desc": balance_ue_lines[line]["balance_line"].long_desc,
                    "amount": balance_ue_lines[line]["rounded_amount"],
                    "accounts": balance_ue_lines[line]["account_list"],
                }
            )
        balance_state = "OK"
        log_env = self.env["account.balance.eu.log"]
        log_env.search([("balance_id", "=", form_data["id"])]).unlink()  # clear log
        unlinked_account = []
        tot = 0
        self.get_account_list_amount(
            company_id,
            currency_precision,
            date_from,
            date_to,
            only_posted_move,
            hide_acc_amount_0,
            ignore_closing_move,
            "non_assoc",
            False,
            "",
            tot,
            unlinked_account,
        )
        if (
            balance_ue_lines["PA"]["rounded_amount"]
            != balance_ue_lines["PP"]["rounded_amount"]
        ):
            balance_state = "UNBALANCED"
            log_warnings = (
                "Bilancio NON quadrato: {:s} (Attivo) "
                "- {:s} (Passivo) = {:s}".format(
                    format_decimal(
                        balance_ue_lines["PA"]["rounded_amount"],
                        format="#,##0.00",
                        locale="it_IT",
                    ),
                    format_decimal(
                        balance_ue_lines["PP"]["rounded_amount"],
                        format="#,##0.00",
                        locale="it_IT",
                    ),
                    format_decimal(
                        my_round(
                            balance_ue_lines["PA"]["rounded_amount"]
                            - balance_ue_lines["PP"]["rounded_amount"],
                            2,
                        ),
                        format="#,##0.00",
                        locale="it_IT",
                    ),
                )
            )
        else:
            log_warnings = ""
        if len(unlinked_account) > 0:
            balance_state = "UNLINKED_ACCOUNTS"
            log_warnings += _(
                "\nSono presenti conti non associati a nessuna voce di bilancio:\n"
            )
            for acc in unlinked_account:
                account_id = (
                    self.env["account.account"]
                    .search([("code", "=", acc.get("code"))])
                    .id
                )
                log_env.create(
                    {
                        "balance_id": form_data["id"],
                        "account_id": account_id,
                        "amount": acc.get("amount"),
                    }
                )
        log_warnings = log_warnings.strip()
        if log_warnings == "":
            waring_lines = []
        else:
            waring_lines = log_warnings.split("\n")
        data = {
            "form_data": form_data,
            "balance_ue_lines": balance_ue_lines_report_data,
            "balance_state": balance_state,
            "warnings": waring_lines,
            "unlinked_account": unlinked_account,
        }
        return data


class AccountRefBalanceEU(models.Model):
    _inherit = "account.account"
    account_balance_eu_debit_id = fields.Many2one(
        "account.balance.eu",
        string="Debit (Balance EU)",
        domain="[('child_ids','=',False)]",
        help="Add this account in a Balance EU line amount DEBITS",
    )
    account_balance_eu_credit_id = fields.Many2one(
        "account.balance.eu",
        string="Credit (Balance EU)",
        domain="[('child_ids','=',False)]",
        help="Add this account in a Balance EU line amount CREDITS",
    )

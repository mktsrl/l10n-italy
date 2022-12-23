import operator
from datetime import date

from odoo import api, fields, models


def my_round(val, precision):
    # il round arrotonda il 5 al pari più vicino (1.5 -> 2 e 2.5 -> 2)
    # aggiungo un infinitesimo per farlo arrotondare sempre per eccesso
    return round(val + 1e-10, precision)


class AccountBalanceEULog(models.TransientModel):
    _name = "account.balance.eu.log"
    _description = "Unlinked account in balance EU"
    balance_id = fields.Many2one("account.balance.eu.wizard", string="Balance")
    account_id = fields.Many2one(
        "account.account", string="Account unlinked", readonly=True
    )
    amount = fields.Float(string="Amount", readonly=True)


class CreateBalanceWizard(models.TransientModel):
    _name = "account.balance.eu.wizard"
    _description = "Wizard for balance UE calculation"

    def _default_date_from(self):
        return date(date.today().year - 1, 1, 1)

    def _default_date_to(self):
        return date(date.today().year - 1, 12, 31)

    default_name = fields.Char(string="Description")
    default_date_from = fields.Date(
        string="Balance from date",
        default=_default_date_from,
    )
    default_date_to = fields.Date(
        string="Balance to date",
        default=_default_date_to,
    )
    default_balance_type = fields.Selection(
        [
            ("d", "2 decimals Euro"),
            ("u", "euro units"),
        ],
        string="Values show as",
        default="d",
        required=True,
    )
    default_hide_acc_amount_0 = fields.Boolean(
        string="Hide account with amount 0", default=True
    )
    default_only_posted_move = fields.Boolean(
        string="Use only posted registration", default=True
    )
    log_warnings = fields.Text(string="WARNING:", default="")
    # CAMPI TESTATA BILANCIO
    company_id = fields.Many2one("res.company", string="Company")
    name = fields.Char(string="Name", compute="_compute_period_data")
    year = fields.Integer(string="Year", compute="_compute_period_data")
    currency_id = fields.Many2one("res.currency", string="Currency")
    date_from = fields.Date(string="From date", compute="_compute_period_data")
    date_to = fields.Date(string="To date", compute="_compute_period_data")
    # dati dell'azienda
    company_name = fields.Char(string="Company Name")
    address = fields.Char(string="Address")
    city = fields.Char(string="City")
    rea_office = fields.Char(string="REA office")
    rea_num = fields.Char(string="REA number")
    rea_capital = fields.Float(string="Social Capital")
    fiscalcode = fields.Char(string="Fiscal Code")
    vat_code = fields.Char(string="VAT number")
    vat_code_nation = fields.Char(string="VAT number nation")
    chief_officer_name = fields.Char(string="Chief officer")
    chief_officer_role = fields.Char(string="Chief officer role")
    balance_log_ids = fields.One2many(
        "account.balance.eu.log", "balance_id", auto_join=True
    )
    state = fields.Selection(
        [
            ("OK", "COMPLETE"),
            ("UNLINKED_ACCOUNTS", "CHECK ACCOUNTS"),
            ("UNBALANCED", "UNBALANCED"),
        ],
        string="State",
        default="OK",
        readonly=True,
    )
    balance_ue_lines = {}

    @api.depends("default_name", "default_date_to", "default_date_from")
    def _compute_period_data(self):
        for balance in self:
            balance.date_to = balance.default_date_to
            balance.date_from = balance.default_date_from
            balance.year = balance.date_to.year
            if balance.default_name:
                balance.name = balance.default_name
            else:
                balance.name = "Bilancio " + str(balance.year)

    def cal_balance_ue_line_amount(self, code):
        total_amount = 0
        rounded_amount = 0
        account_balance_eu_child_ids = self.env["account.balance.eu"].search(
            [("parent_id", "=", self.balance_ue_lines[code]["balance_line"].id)]
        )
        for child in account_balance_eu_child_ids:
            if child.child_ids:
                self.cal_balance_ue_line_amount(child.code)
            if child.sign_calculation == "-":
                rounded_amount -= self.balance_ue_lines[child.code]["rounded_amount"]
                total_amount -= self.balance_ue_lines[child.code]["total_amount"]
            else:
                rounded_amount += self.balance_ue_lines[child.code]["rounded_amount"]
                total_amount += self.balance_ue_lines[child.code]["total_amount"]
        self.balance_ue_lines[code]["rounded_amount"] = my_round(rounded_amount, 2)
        self.balance_ue_lines[code]["total_amount"] = total_amount

    def get_account_list_amount(
        self,
        calc_type,
        account_balance_eu_id,
        sign_display,
        balance_line_amount,
        account_list,
    ):
        precision = self.currency_id.decimal_places
        domain = []
        domain.append(("company_id", "=", self.company_id.id))
        if calc_type == "d":
            domain.append(("account_balance_eu_debit_id", "=", account_balance_eu_id))
        elif calc_type == "a":
            domain.append(("account_balance_eu_credit_id", "=", account_balance_eu_id))
        elif calc_type == "non_assoc":
            domain.append(("account_balance_eu_debit_id", "=", False))
            domain.append(("account_balance_eu_credit_id", "=", False))
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
                    domain.append(("company_id", "=", self.company_id.id))
                    domain.append(("account_id", "=", account_id))
                    domain.append(("date", ">=", self.date_from))
                    domain.append(("date", "<=", self.date_to))
                    if self.default_only_posted_move:
                        domain.append(("move_id.state", "=", "posted"))
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
                                line.get("debit") - line.get("credit"), precision
                            )
                            if (
                                ((calc_type == "non_assoc") and (acc_amount != 0))
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
                                if (not self.default_hide_acc_amount_0) or (
                                    acc_amount != 0
                                ):
                                    account_list.append(
                                        {
                                            "code": item.get("code"),
                                            "desc": item.get("name"),
                                            "amount": acc_amount,
                                        }
                                    )
        return balance_line_amount

    def get_balance_ue_data(self):
        self.company_id = self.env.company
        self.currency_id = self.env.company.currency_id
        self.company_name = self.env.company.name
        self.address = self.env.company.street
        self.city = self.env.company.zip + " " + self.env.company.city
        self.rea_office = self.env.company.rea_office.code or ""
        self.rea_num = self.env.company.rea_code or ""
        self.rea_capital = self.env.company.rea_capital
        self.fiscalcode = self.env.company.fiscalcode
        self.vat_code = self.env.company.vat or ""
        self.vat_code_nation = ""
        self.chief_officer_role = ""
        self.chief_officer_name = ""

        if (len(self.vat_code) == 13) and self.vat_code.startswith("IT"):
            self.vat_code_nation = self.vat_code[0:2]
            self.vat_code = self.vat_code[2:]

        account_balance_eu_ids = self.env["account.balance.eu"].search([])
        for item in account_balance_eu_ids:
            account_balance_eu_amount = 0
            account_list = []
            if not item.child_ids:
                calcoli = ["d", "a"]  # d=debit a=credit
                for calc_type in calcoli:
                    account_balance_eu_amount = self.get_account_list_amount(
                        calc_type,
                        item.id,
                        item.sign_display,
                        account_balance_eu_amount,
                        account_list,
                    )
            account_list.sort(key=operator.itemgetter("code"))

            if self.default_balance_type == "u":
                account_balance_eu_amount_rounded = my_round(
                    account_balance_eu_amount, 0
                )
            elif self.default_balance_type == "d":
                account_balance_eu_amount_rounded = my_round(
                    account_balance_eu_amount, 2
                )
            else:
                account_balance_eu_amount_rounded = account_balance_eu_amount
            self.balance_ue_lines[item.code] = {
                "balance_line": item,
                "rounded_amount": account_balance_eu_amount_rounded,
                "total_amount": account_balance_eu_amount,
                "account_list": account_list,
            }
        self.cal_balance_ue_line_amount("E.A")
        self.cal_balance_ue_line_amount("E.B")
        self.cal_balance_ue_line_amount("E.C")
        self.cal_balance_ue_line_amount("E.D")
        self.cal_balance_ue_line_amount("E.F")
        self.balance_ue_lines["E=B"]["rounded_amount"] = (
            self.balance_ue_lines["E.A"]["rounded_amount"]
            - self.balance_ue_lines["E.B"]["rounded_amount"]
        )
        self.balance_ue_lines["E=B"]["total_amount"] = (
            self.balance_ue_lines["E.A"]["total_amount"]
            - self.balance_ue_lines["E.B"]["total_amount"]
        )
        self.balance_ue_lines["E=E"]["rounded_amount"] = (
            self.balance_ue_lines["E=B"]["rounded_amount"]
            + self.balance_ue_lines["E.C"]["rounded_amount"]
            + self.balance_ue_lines["E.D"]["rounded_amount"]
        )
        self.balance_ue_lines["E=E"]["total_amount"] = (
            self.balance_ue_lines["E=B"]["total_amount"]
            + self.balance_ue_lines["E.C"]["total_amount"]
            + self.balance_ue_lines["E.D"]["total_amount"]
        )
        self.balance_ue_lines["E=F"]["rounded_amount"] = (
            self.balance_ue_lines["E=E"]["rounded_amount"]
            - self.balance_ue_lines["E.F"]["rounded_amount"]
        )
        self.balance_ue_lines["E=F"]["total_amount"] = (
            self.balance_ue_lines["E=E"]["total_amount"]
            - self.balance_ue_lines["E.F"]["total_amount"]
        )
        self.balance_ue_lines["PP=A9"]["rounded_amount"] = self.balance_ue_lines["E=F"][
            "rounded_amount"
        ]
        self.balance_ue_lines["PP=A9"]["total_amount"] = self.balance_ue_lines["E=F"][
            "total_amount"
        ]
        self.cal_balance_ue_line_amount("PA")
        self.cal_balance_ue_line_amount("PP")
        self.balance_ue_lines["PP=A7j2"]["total_amount"] = (
            self.balance_ue_lines["PA"]["rounded_amount"]
            - self.balance_ue_lines["PP"]["rounded_amount"]
        ) - (
            self.balance_ue_lines["PA"]["total_amount"]
            - self.balance_ue_lines["PP"]["total_amount"]
        )
        if self.default_balance_type == "u":
            self.balance_ue_lines["PP=A7j2"]["rounded_amount"] = my_round(
                self.balance_ue_lines["PP=A7j2"]["total_amount"], 0
            )
        elif self.default_balance_type == "d":
            self.balance_ue_lines["PP=A7j2"]["rounded_amount"] = my_round(
                self.balance_ue_lines["PP=A7j2"]["total_amount"], 2
            )
        else:
            self.balance_ue_lines["PP=A7j2"]["rounded_amount"] = self.balance_ue_lines[
                "PP=A7j2"
            ]["total_amount"]
        self.cal_balance_ue_line_amount("PP")
        balance_ue_lines_report_data = []
        for line in self.balance_ue_lines:
            balance_ue_lines_report_data.append(
                {
                    "code": self.balance_ue_lines[line]["balance_line"].code,
                    "desc": self.balance_ue_lines[line]["balance_line"].long_desc,
                    "amount": self.balance_ue_lines[line]["rounded_amount"],
                    "accounts": self.balance_ue_lines[line]["account_list"],
                }
            )
        self.state = "OK"
        log_env = self.env["account.balance.eu.log"]
        log_env.search([("balance_id", "=", self.id)]).unlink()  # clear log
        unlinked_account = []
        tot = 0
        self.get_account_list_amount("non_assoc", False, "", tot, unlinked_account)
        if (
            self.balance_ue_lines["PA"]["rounded_amount"]
            != self.balance_ue_lines["PP"]["rounded_amount"]
        ):
            self.state = "UNBALANCED"
            self.log_warnings = (
                "Bilancio NON quadrato: {:.2f} (Attivo) "
                "- {:.2f} (Passivo) = {:.2f}".format(
                    self.balance_ue_lines["PA"]["rounded_amount"],
                    self.balance_ue_lines["PP"]["rounded_amount"],
                    my_round(
                        self.balance_ue_lines["PA"]["rounded_amount"]
                        - self.balance_ue_lines["PP"]["rounded_amount"],
                        2,
                    ),
                )
            )
        else:
            self.log_warnings = ""
        if len(unlinked_account) > 0:
            self.state = "UNLINKED_ACCOUNTS"
            self.log_warnings += (
                "\nSono presenti conti movimentati nel "
                "periodo che non sono associati a nessuna voce di bilancio:\n"
            )
            for acc in unlinked_account:
                account_id = (
                    self.env["account.account"]
                    .search([("code", "=", acc.get("code"))])
                    .id
                )
                log_env.create(
                    {
                        "balance_id": self.id,
                        "account_id": account_id,
                        "amount": acc.get("amount"),
                    }
                )
        self.log_warnings = self.log_warnings.strip()
        data = {
            "form_data": self.read()[0],
            "balance_ue_lines": balance_ue_lines_report_data,
            "warnings": self.log_warnings.split("\n"),
            "unlinked_account": unlinked_account,
        }
        return data

    def balance_eu_html_report(self):
        balance_data = self.get_balance_ue_data()
        return self.env.ref(
            "l10n_it_account_balance_eu.action_report_balance_eu_xml"
        ).report_action(self, data=balance_data)

    def balance_eu_xlsx_report(self):
        balance_data = self.get_balance_ue_data()
        return self.env.ref(
            "l10n_it_account_balance_eu.action_report_balance_eu_xlsx"
        ).report_action(self, data=balance_data)

    def balance_eu_xbrl_report(self):
        balance_data = self.get_balance_ue_data()
        return self.env.ref(
            "l10n_it_account_balance_eu.action_report_balance_eu_xbrl"
        ).report_action(self, data=balance_data)

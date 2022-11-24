from datetime import date

from odoo import _, api, fields, models


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
    _description = "Wizard for balance EU calculation"

    def _default_date_range(self):
        return (
            self.env["date.range"]
            .search([("name", "=", str(date.today().year - 1))])
            .id
        )

    date_range_id = fields.Many2one(
        comodel_name="date.range",
        string="Date range",
        default=_default_date_range,
    )
    default_date_from = fields.Date(string="Balance from date", required=True)
    default_date_to = fields.Date(string="Balance to date", required=True)
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
    default_ignore_closing_move = fields.Boolean(
        string="Ignore closing registration", default=True
    )
    log_warnings = fields.Text(string="WARNING:", default="")
    # BALANCE HEADER
    company_id = fields.Many2one("res.company", string="Company")
    currency_id = fields.Many2one("res.currency", string="Currency")
    name = fields.Char(string="Name", compute="_compute_period_data")
    year = fields.Integer(string="Year", compute="_compute_period_data")
    date_from = fields.Date(string="From date", compute="_compute_period_data")
    date_to = fields.Date(string="To date", compute="_compute_period_data")
    # COMPANY DATA
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
        "account.balance.eu.log",
        "balance_id",
        string="Unlinked Account",
        auto_join=True,
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

    @api.onchange("date_range_id")
    def onchange_date_range_id(self):
        """Handle date range change."""
        self.default_date_from = self.date_range_id.date_start
        self.default_date_to = self.date_range_id.date_end

    @api.depends("date_range_id", "default_date_to", "default_date_from")
    def _compute_period_data(self):
        for balance in self:
            balance.date_to = balance.default_date_to
            balance.date_from = balance.default_date_from
            balance.year = balance.date_to.year
            balance.name = _("Balance EU")
            if balance.date_to.month == balance.date_from.month:
                balance.name = (
                    balance.name
                    + " "
                    + str(balance.date_from.month)
                    + "-"
                    + str(balance.year)
                )
            else:
                balance.name = balance.name + " " + str(balance.year)

    def get_data(self):
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
        return self.read()[0]

    def balance_eu_html_report(self):
        form_data = self.get_data()
        return self.env.ref(
            "l10n_it_account_balance_eu.action_report_balance_eu_xml"
        ).report_action(self, data=form_data)

    def cal_warnings_and_unlinked_acc(self, form_data):
        balance_ue_data = self.env["account.balance.eu"].cal_balance_ue_data(form_data)
        self.state = balance_ue_data.get("balance_state")
        self.log_warnings = "\n".join(balance_ue_data.get("warnings"))

    def balance_eu_xlsx_report(self):
        form_data = self.get_data()
        self.cal_warnings_and_unlinked_acc(form_data)
        return self.env.ref(
            "l10n_it_account_balance_eu.action_report_balance_eu_xlsx"
        ).report_action(self, data=form_data)

    def balance_eu_xbrl_report(self):
        form_data = self.get_data()
        self.cal_warnings_and_unlinked_acc(form_data)
        return self.env.ref(
            "l10n_it_account_balance_eu.action_report_balance_eu_xbrl"
        ).report_action(self, data=form_data)

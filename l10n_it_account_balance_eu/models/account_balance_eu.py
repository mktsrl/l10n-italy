# Copyright 2022 MKT srl
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


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


class AccountRefBalanceEU(models.Model):
    _inherit = "account.account"
    account_balance_eu_debit_id = fields.Many2one(
        "account.balance.eu",
        string="Debit (Balance UE)",
        domain="[('child_ids','=',False)]",
        help="Add this account in a Balance UE line amount DEBITS",
    )
    account_balance_eu_credit_id = fields.Many2one(
        "account.balance.eu",
        string="Credit (Balance UE)",
        domain="[('child_ids','=',False)]",
        help="Add this account in a Balance UE line amount CREDITS",
    )

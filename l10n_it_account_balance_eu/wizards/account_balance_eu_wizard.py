import base64
import operator
from datetime import date

from odoo import api, fields, models


def my_round(val, precision):
    # il round arrotonda il 5 al pari più vicino (1.5 -> 2 e 2.5 -> 2)
    # aggiungo un infinitesimo per farlo arrotondare sempre per eccesso
    return round(val + 1e-10, precision)


class AccountBalanceEULog(models.TransientModel):
    _name = "account.balance.eu.log"
    _description = "Log delle estrazioni fatte per il calcolo bilancio UE"
    balance_id = fields.Many2one("account.balance.eu.wizard", string="Bilancio")
    account_id = fields.Many2one(
        "account.account", string="Conto non associato", readonly=True
    )
    amount = fields.Float(string="Saldo", readonly=True)


class CreateBalanceWizard(models.TransientModel):
    _name = "account.balance.eu.wizard"
    _description = "Wizard per calcolo bilancio UE"

    def _default_date_from(self):
        return date(date.today().year - 1, 1, 1)

    def _default_date_to(self):
        return date(date.today().year - 1, 12, 31)

    # CAMPI DA CHIEDERE
    default_name = fields.Char(string="Descrizione")
    default_date_from = fields.Date(
        string="Data inizio bilancio", default=_default_date_from
    )
    default_date_to = fields.Date(string="Data fine bilancio", default=_default_date_to)
    default_balance_type = fields.Selection(
        [
            ("d", "2 decimali di Euro"),
            ("u", "unità di Euro"),
            # ('m', 'Migliaia di Euro')
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
    log_warnings = fields.Text(string="ATTENZIONE:", default="")
    # CAMPI TESTATA BILANCIO
    company_id = fields.Many2one("res.company", string="Azienda")
    name = fields.Char(string="Etichetta", compute="_compute_period_data")
    year = fields.Integer(string="Anno", compute="_compute_period_data")
    currency_id = fields.Many2one("res.currency", string="Valuta")
    date_from = fields.Date(string="Data inizio", compute="_compute_period_data")
    date_to = fields.Date(string="Data fine", compute="_compute_period_data")
    # dati dell'azienda
    company_name = fields.Char(string="Ragione Sociale")
    address = fields.Char(string="Indirizzo")
    city = fields.Char(string="Città")
    rea_office = fields.Char(string="Ufficio REA")
    rea_num = fields.Char(string="Numero REA")
    rea_capital = fields.Float(string="Capitale Sociale")
    fiscalcode = fields.Char(string="Codice Fiscale")
    vat_code = fields.Char(string="Partita IVA")
    vat_code_nation = fields.Char(string="Paese Partita IVA")
    chief_officer_name = fields.Char(string="Responsabile")
    chief_officer_role = fields.Char(string="Carica del Responsabile")
    # lista con le voci del bilancio (id, tot)
    balance_log_ids = fields.One2many(
        "account.balance.eu.log", "balance_id", auto_join=True
    )
    state = fields.Selection(
        [
            ("OK", "COMPLETO"),
            ("UNLINKED_ACCOUNTS", "VERIFICARE CONTI"),
            ("UNBALANCED", "NON QUADRATO"),
        ],
        string="Stato",
        default="OK",
        readonly=True,
    )
    balance_ue_lines = {}

    @api.depends("default_name", "default_date_to", "default_date_from")
    def _compute_period_data(self):
        for balance in self:
            balance.date_to = balance.default_date_to
            balance.date_from = balance.default_date_from
            balance.year = (
                balance.date_to.year
            )  # Anno su cui viene effettuato il calcolo: proviamo a mettere l'anno del date_to

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
        self.company_id = self.env.company  # VALUTA: company corrente
        self.currency_id = (
            self.env.company.currency_id
        )  # VALUTA: currency_id della company
        self.company_name = self.env.company.name  # Ragione Sociale name
        self.address = self.env.company.street  # Indirizzo street
        self.city = self.env.company.zip + " " + self.env.company.city
        # Registro Imprese
        self.rea_office = self.env.company.rea_office.code or ""
        self.rea_num = self.env.company.rea_code or ""  # REA
        self.rea_capital = self.env.company.rea_capital  # Capitale Sociale
        self.fiscalcode = self.env.company.fiscalcode  # Codice Fiscale fiscalcode
        self.vat_code = self.env.company.vat or ""
        self.vat_code_nation = ""
        self.chief_officer_role = ""  # Ruolo Responsabile
        self.chief_officer_name = ""  # Responsabile

        if (len(self.vat_code) == 13) and self.vat_code.startswith("IT"):
            self.vat_code_nation = self.vat_code[0:2]
            self.vat_code = self.vat_code[2:]

        account_balance_eu_ids = self.env["account.balance.eu"].search([])
        for item in account_balance_eu_ids:
            account_balance_eu_amount = 0
            account_list = []
            if not item.child_ids:
                calcoli = ["d", "a"]  # dare, avere
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
                "Bilancio NON quadrato: {} (Attivo) - {} (Passivo) = {}".format(
                    self.balance_ue_lines["PA"]["rounded_amount"],
                    self.balance_ue_lines["PP"]["rounded_amount"],
                    my_round(
                        self.balance_ue_lines["PA"]["rounded_amount"]
                        - self.balance_ue_lines["PP"]["rounded_amount"],
                        2,
                    ),
                )
                + "\n"
            )
        else:
            self.log_warnings = ""
        if len(unlinked_account) > 0:
            self.state = "UNLINKED_ACCOUNTS"
            self.log_warnings += (
                "\nSono presenti conti movimentati nel periodo che non sono associati  "
                "a nessuna voce di bilancio\n"
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

    def get_xbrl_data_tag(self, field, str_year, value, decimal_precision=-1):
        complete_field = "itcc-ci:" + field
        if decimal_precision >= 0:
            altri_attr = ' unitRef="eur" decimals="{}"'.format(decimal_precision)
            value = f"{value:.{decimal_precision}f}"
        else:
            altri_attr = ""
        return """
    <{} contextRef="{}"{}>{}</{}>""".format(
            complete_field, str_year, altri_attr, value, complete_field
        )

    def get_balance_line_tags(
        self, balance_line_id, balance_ue_lines, str_year, decimal_precision
    ):
        result = ""
        for child in balance_line_id.child_ids:
            result += self.get_balance_line_tags(
                child, balance_ue_lines, str_year, decimal_precision
            )
        if balance_line_id.tag_xbrl:
            amount = None
            i = 0
            while (amount is None) and (i < len(balance_ue_lines)):
                if balance_ue_lines[i]["code"] == balance_line_id["code"]:
                    amount = balance_ue_lines[i]["amount"]
                i += 1
            if amount is not None:
                result += self.get_xbrl_data_tag(
                    balance_line_id.tag_xbrl, str_year, amount, decimal_precision
                )
        return result

    def create_balance_eu_xbrl(self):
        balance_ue_data = self.get_balance_ue_data()
        balance_form_data = balance_ue_data["form_data"]
        xbrl_name = str(balance_form_data["year"]) + "-XBRL-bilancio-esercizio.xbrl"
        i_year = "i_" + str(balance_form_data["year"])
        d_year = "d_" + str(balance_form_data["year"])
        xbrl = """<?xml version = "1.0" encoding = "UTF-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
        xmlns:link="http://www.xbrl.org/2003/linkbase"
        xmlns:xlink="http://www.w3.org/1999/xlink"
        xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
        xmlns:xbrli="http://www.xbrl.org/2003/instance"
        xmlns:itcc-ci="http://www.infocamere.it/itnn/fr/itcc/ci/2018-11-04"
        xmlns:itcc-ci-ese="http://www.infocamere.it/itnn/fr/itcc/ci/ese/2018-11-04">
    <link:schemaRef xlink:type="simple"
        xlink:arcrole="http://www.w3.org/1999/xlink/properties/linkbase"
        xlink:href="itcc-ci-ese-2018-11-04.xsd"/>"""

        xbrl += """
    <context id="{}">
        <entity>
          <identifier scheme="http://www.infocamere.it">{}</identifier>
        </entity>
        <period>
          <instant>{}</instant>
        </period>
        <scenario>
          <itcc-ci-ese:scen>Depositato</itcc-ci-ese:scen>
        </scenario>
    </context>""".format(
            i_year,
            balance_form_data["fiscalcode"],
            balance_form_data["default_date_to"],
        )

        xbrl += """
    <context id="{}">
        <entity>
          <identifier scheme="http://www.infocamere.it">{}</identifier>
        </entity>
        <period>
          <startDate>{}</startDate>
          <endDate>{}</endDate>
        </period>
        <scenario>
          <itcc-ci-ese:scen>Depositato</itcc-ci-ese:scen>
        </scenario>
    </context>""".format(
            d_year,
            balance_form_data["fiscalcode"],
            balance_form_data["default_date_from"],
            balance_form_data["default_date_to"],
        )
        xbrl += """
    <unit id="eur">
        <measure>iso4217:EUR</measure>
    </unit>
    <unit id="shares">
        <measure>xbrli:shares</measure>
    </unit>
    <unit id="pure">
        <measure>xbrli:pure</measure>
    </unit>
    """
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiDenominazione", i_year, balance_form_data["company_name"]
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiSede",
            i_year,
            balance_form_data["address"]
            + " - "
            + self.env.company.zip
            + " - "
            + self.env.company.city,
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiCapitaleSociale", i_year, balance_form_data["rea_capital"], 0
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiCapitaleSocialeInteramenteVersato", i_year, "true"
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiCodiceCciaa", i_year, balance_form_data["rea_office"]
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiPartitaIva", i_year, balance_form_data["vat_code"]
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiCodiceFiscale", i_year, balance_form_data["fiscalcode"]
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiNumeroRea",
            i_year,
            balance_form_data["rea_office"] + " " + balance_form_data["rea_num"],
        )
        xbrl += self.get_xbrl_data_tag("DatiAnagraficiFormaGiuridica", i_year, "")
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiSettoreAttivitaPrevalenteAteco", i_year, ""
        )
        if self.env.company.rea_liquidation_state == "LS":
            tmp_s = "true"
        else:
            tmp_s = "false"
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiSocietaLiquidazione", i_year, tmp_s
        )
        if self.env.company.rea_member_type == "SU":
            tmp_s = "true"
        else:
            tmp_s = "false"
        xbrl += self.get_xbrl_data_tag("DatiAnagraficiSocietaSocioUnico", i_year, tmp_s)
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiSocietaSottopostaAltruiAttivitaDirezioneCoordinamento",
            i_year,
            "false",
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiDenominazioneSocietaEnteEsercitaAttivitaDirezioneCoordinamento",
            i_year,
            "",
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiAppartenenzaGruppo", i_year, "false"
        )
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiDenominazioneSocietaCapogruppo", i_year, ""
        )
        xbrl += self.get_xbrl_data_tag("DatiAnagraficiPaeseCapogruppo", i_year, "")
        xbrl += self.get_xbrl_data_tag(
            "DatiAnagraficiNumeroIscrizioneAlboCooperative", i_year, ""
        )

        if balance_form_data["default_balance_type"] == "d":
            decimal_precision = 2
        else:
            decimal_precision = 0
        tmp_balance_lines = self.env["account.balance.eu"].search([("code", "=", "PA")])
        if len(tmp_balance_lines) == 1:
            xbrl += self.get_balance_line_tags(
                tmp_balance_lines[0],
                balance_ue_data["balance_ue_lines"],
                i_year,
                decimal_precision,
            )
        tmp_balance_lines = self.env["account.balance.eu"].search([("code", "=", "PP")])
        if len(tmp_balance_lines) == 1:
            xbrl += self.get_balance_line_tags(
                tmp_balance_lines[0],
                balance_ue_data["balance_ue_lines"],
                i_year,
                decimal_precision,
            )
        tmp_balance_lines = self.env["account.balance.eu"].search([("code", "=", "E")])
        if len(tmp_balance_lines) == 1:
            xbrl += self.get_balance_line_tags(
                tmp_balance_lines[0],
                balance_ue_data["balance_ue_lines"],
                d_year,
                decimal_precision,
            )

        xbrl += "\n</xbrl>"
        xbrl = xbrl.encode("ascii")

        # get base url
        base_url = self.env["ir.config_parameter"].get_param("web.base.url")
        attachment_obj = self.env["ir.attachment"]
        # create attachment
        attachment = attachment_obj.create(
            {
                "name": xbrl_name,
                "mimetype": "application/xml",
                "datas": base64.b64encode(xbrl),
            }
        )
        # prepare download url
        download_url = "/web/content/" + str(attachment.id) + "?download=true"
        # download
        return {
            "type": "ir.actions.act_url",
            "url": str(base_url) + str(download_url),
            "target": "new",
        }

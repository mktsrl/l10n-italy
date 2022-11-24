from odoo import models


class BalanceEuXlsxReport(models.AbstractModel):
    _name = "report.l10n_it_account_balance_eu.balance_eu_xlsx_report"
    _description = "Esportazione del bilancio UE in formato XLSX"
    _inherit = "report.report_xlsx.abstract"

    def generate_xlsx_report(self, workbook, data, record_data):
        balance_data = data["form_data"]
        sheet = workbook.add_worksheet("Bilancio")
        st_bold18 = workbook.add_format({"bold": True, "font_size": 18})
        sheet.write(0, 0, balance_data["company_name"], st_bold18)
        sheet.set_row(0, 28)
        sheet.write(1, 0, balance_data["address"] + " - " + balance_data["city"])
        sheet.write(2, 0, "Capitale sociale Euro " + str(balance_data["rea_capital"]))
        sheet.write(3, 0, "Bilancio", st_bold18)
        sheet.set_row(3, 28)
        col_title_style = workbook.add_format({"fg_color": "#729fcf"})
        sheet.write(5, 0, "Descrizione", col_title_style)
        sheet.write(5, 1, "Codice", col_title_style)
        sheet.write(5, 2, str(balance_data["year"]), col_title_style)
        st_des = workbook.add_format({"num_format": "@"})
        if balance_data["default_balance_type"] == "d":
            amount_style = workbook.add_format({"num_format": "#,##0.00"})
        elif balance_data["default_balance_type"] == "u":
            amount_style = workbook.add_format({"num_format": "#,##0"})
        row = 6
        max_l_descr = 0
        max_l_importo = 0
        for line in data["balance_ue_lines"]:
            code = line["code"]
            length = len(code[code.find(".") :])
            desc = ""
            for _c in range(length - 1):
                desc += " "
            desc += line["desc"]
            sheet.write(row, 0, desc, st_des)
            sheet.write(row, 1, code)
            sheet.write(row, 2, line["amount"], amount_style)
            row += 1
            if len(desc) > max_l_descr:
                max_l_descr = len(desc)
            length = len(str(line["amount"]))
            if length > max_l_importo:
                max_l_importo = length
        sheet.set_column(0, 0, max_l_descr)
        sheet.set_column(2, 2, max_l_importo)

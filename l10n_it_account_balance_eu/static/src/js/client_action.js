odoo.define("l10n_it_account_balance_eu.client_action", function (require) {
    "use strict";

    var ReportAction = require("report.client_action");
    var core = require("web.core");

    var QWeb = core.qweb;

    const AFRReportAction = ReportAction.extend({
        start: function () {
            return this._super.apply(this, arguments).then(() => {
                this.$buttons = $(
                    QWeb.render(
                        "l10n_it_account_balance_eu.client_action.ControlButtons",
                        {}
                    )
                );
                this.$buttons.on("click", ".o_report_print", this.on_click_print);
                this.$buttons.on("click", ".o_report_xlsx", this.on_click_xlsx);
                this.$buttons.on("click", ".o_report_xbrl", this.on_click_xbrl);

                this.controlPanelProps.cp_content = {
                    $buttons: this.$buttons,
                };

                this._controlPanelWrapper.update(this.controlPanelProps);
            });
        },

        on_click_xlsx: function () {
            const action = {
                type: "ir.actions.report",
                report_type: "xlsx",
                report_name: "l10n_it_account_balance_eu.balance_eu_xlsx_report",
                report_file: this._get_xlsx_name(this.report_file),
                data: this.data,
                context: this.context,
                display_name: this.title,
            };
            return this.do_action(action);
        },

        /**
         * @param {String} str
         * @returns {String}
         */
        _get_xlsx_name: function (str) {
            if (!_.isString(str)) {
                return str;
            }
            const parts = str.split(".");
            return `a_f_r.report_${parts[parts.length - 1]}_xlsx`;
        },

        on_click_xbrl: function () {
            const action = {
                type: "ir.actions.report",
                report_type: "qweb-xml",
                report_name: "l10n_it_account_balance_eu.balance_eu_xbrl_report",
                report_file: String(this.data["year"]) + "-XBRL-bilancio-esercizio.xbrl",
                data: this.data,
                context: this.context,
                display_name: this.title,
            };
            return this.do_action(action);
        },
    });

    core.action_registry.add(
        "l10n_it_account_balance_eu.client_action",
        AFRReportAction
    );

    return AFRReportAction;
});

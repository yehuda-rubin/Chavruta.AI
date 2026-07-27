"""Billing — subscription checkout, webhooks, and invoicing.

Provider stack (chosen after the Israeli-market research, see the production-audit folder): **PayPlus**
as the payment gateway (recurring/tokenized, webhook-driven) and **Green Invoice / Morning** as the
invoicing service that issues the legally-required חשבונית מס/קבלה off each successful charge.

Everything is env-gated: with the PayPlus credentials unset, billing is OFF and the endpoints report
unavailable — local/offline dev is unchanged. The subscription state lives in the `subscriptions`
table (app/db.py) and the paid tier is gated via `accounts.plan` (set by the webhook).
"""

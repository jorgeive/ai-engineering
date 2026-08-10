"""Deterministic multi-turn profiles for conversational-memory stress tests."""

from __future__ import annotations

from evals.stress.metrics import FactField


Fact = tuple[str, FactField]
ScenarioTurn = tuple[int, str, Fact | None]


# A fact is its canonical value plus the snapshot field to inspect. Keeping
# that metadata next to every turn avoids false negatives caused by searching
# human-readable labels such as "scope includes RFQ workflow" verbatim.
GROWING: list[ScenarioTurn] = [
    (1, "Build a B2B procurement SaaS called Nimbus. Use React and Postgres.", ("Nimbus", "project_name")),
    (2, "The product needs an RFQ workflow and a vendor catalogue.", ("RFQ workflow", "any")),
    (3, "Add Okta SSO for employees and external vendors.", ("Okta", "technologies")),
    (4, "The first-release budget is fixed at 60000 EUR.", ("60000", "any")),
    (5, "Keep an immutable audit log for every approval.", ("audit log", "any")),
    (6, "Import legacy vendor data from CSV files of up to 50000 rows.", ("CSV import", "any")),
    (7, "The service will be multi-tenant for three sister companies.", ("multi-tenant", "any")),
    (8, "Send notification fan-out through email and Microsoft Teams.", ("Microsoft Teams", "technologies")),
    (9, "Expose a partner API with OAuth2 client credentials.", ("OAuth2", "any")),
    (10, "Add weekly KPI digests exported as PDFs.", ("weekly KPI", "any")),
    (11, "Support Spanish, English and Portuguese with per-tenant currency.", ("Portuguese", "any")),
    (12, "Make the approver UI responsive; no native application yet.", ("no native application", "any")),
    (13, "Run nightly SAP reconciliation using IDoc files.", ("SAP", "technologies")),
    (14, "Require two-factor authentication for approvals over 10000 EUR.", ("two-factor", "any")),
    (15, "Export purchase orders as UBL XML.", ("UBL XML", "any")),
    (16, "Implement the GDPR right-to-erasure flow for vendor contacts.", ("right-to-erasure", "any")),
    (17, "Add a feature flag for an experimental AI recommendation panel.", ("feature flag", "any")),
    (18, "Let vendors update banking details through a self-service portal.", ("self-service portal", "any")),
    (19, "Meet a P95 page-load SLA under two seconds for 200 users.", ("P95", "any")),
    (20, "Integrate DocuSign after vendor approval for countersignature.", ("DocuSign", "technologies")),
]


PIVOT: list[ScenarioTurn] = [
    (1, "Build a retail loyalty app called Helios with React Native for iOS and Android.", ("Helios", "project_name")),
    (2, "Members scan a QR code at checkout to accrue and redeem points.", ("QR code", "any")),
    (3, "Use a Node.js API over the existing Postgres customer database.", ("Node.js", "technologies")),
    (4, "Send offer notifications segmented by store region.", ("offer notifications", "any")),
    (5, "Pivot: standardise on Flutter. React Native is no longer an option.", ("Flutter", "technologies")),
    (6, "Reconfirm Flutter for both mobile platforms with the same scope.", ("Flutter", "technologies")),
    (7, "Add Apple Wallet and Google Wallet loyalty passes.", ("Apple Wallet", "any")),
    (8, "Integrate the existing POS REST API for point accrual.", ("POS REST API", "any")),
    (9, "Scan product barcodes in store to show item details.", ("barcodes", "any")),
    (10, "Offer geofenced pushes when a member is near a store.", ("geofenced", "any")),
    (11, "Support Apple ID and Google social login.", ("Apple ID", "any")),
    (12, "Build a Vue.js admin panel for campaign scheduling.", ("Vue.js", "technologies")),
    (13, "Send analytics events through Segment to BigQuery.", ("Segment", "technologies")),
    (14, "Add in-app support messaging integrated with Zendesk.", ("Zendesk", "technologies")),
    (15, "Provide digital receipts when a till printer fails.", ("digital receipts", "any")),
    (16, "Version one supports Spanish and Catalan only.", ("Catalan", "any")),
    (17, "Use Firebase Crashlytics for crash and performance reporting.", ("Crashlytics", "technologies")),
    (18, "Prepare app-store screenshots for three device sizes.", ("app-store screenshots", "any")),
    (19, "Show GDPR consent on the first application launch.", ("GDPR consent", "any")),
    (20, "Add offline access to the loyalty card and recent rewards.", ("offline access", "any")),
]


CONTRADICTION: list[ScenarioTurn] = [
    (1, "Build an AP invoice approvals tool called Atlas with Rails and Postgres.", ("Atlas", "project_name")),
    (2, "The team is two developers and a part-time designer.", ("two developers", "any")),
    (3, "The budget is locked at 30000 EUR for the whole engagement.", ("30000", "any")),
    (4, "Add an audit log of every invoice approval, exportable to CSV.", ("audit log", "any")),
    (5, "All approvers must use the existing Azure AD SSO.", ("Azure AD", "technologies")),
    (6, "Show pending approvals grouped by approver on a dashboard.", ("approvals", "any")),
    (7, "Allow bulk approval of up to 50 invoices with confirmation.", ("bulk approval", "any")),
    (8, "Leadership replaced the old budget: it is now locked at 80000 EUR; 30000 is obsolete.", ("80000", "any")),
    (9, "Confirm the new 80000 EUR budget is the one to use for planning.", ("80000", "any")),
    (10, "Add three-way matching against purchase orders and goods receipts.", ("three-way matching", "any")),
    (11, "Integrate Oracle EBS through its REST gateway.", ("Oracle EBS", "technologies")),
    (12, "Route invoices by cost centre to the correct approver.", ("cost centre", "any")),
    (13, "Send a morning email digest of pending approvals.", ("email digest", "any")),
    (14, "Use AWS Textract for OCR-assisted paper invoice entry.", ("Textract", "technologies")),
    (15, "Support multi-currency invoices using daily ECB rates.", ("multi-currency", "any")),
    (16, "Add aging-bucket and supplier-exposure reports.", ("aging-bucket", "any")),
    (17, "Add a comments thread to each invoice.", ("comments thread", "any")),
    (18, "Handle 5000 invoices per day at month-end peak.", ("5000 invoices", "any")),
    (19, "Require a four-eyes approval for invoices over 25000 EUR.", ("four-eyes", "any")),
    (20, "Export approved invoices nightly to Snowflake.", ("Snowflake", "technologies")),
]


SCENARIOS: dict[str, list[ScenarioTurn]] = {
    "growing": GROWING,
    "pivot": PIVOT,
    "contradiction": CONTRADICTION,
}

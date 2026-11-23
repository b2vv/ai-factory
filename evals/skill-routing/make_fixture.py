#!/usr/bin/env python3
"""Build the disposable fixture repository the skill-routing cases run in.

The fixture is a small but realistic product: a billing service with several modules and one
non-trivial class hierarchy, an admin web UI of many screens with real inconsistencies, a
dashboard, a checkout flow, a layout mockup image, a plan, review comments and a feature branch.
It is large enough that the routing phrases have a plausible target and an answer is not
obvious from one tiny file. Deterministic; standard library only; writes only under DEST.

  make_fixture.py DEST       DEST must not exist
"""
import pathlib
import struct
import subprocess
import sys
import zlib

STYLE = """body{font-family:system-ui,sans-serif;margin:0;color:#1f2328}
header{display:flex;gap:24px;align-items:center;padding:12px 24px;background:#0f172a;color:#fff}
header a{color:#cbd5e1;text-decoration:none} header a.active{color:#fff;font-weight:600}
main{padding:24px;max-width:1100px} table{border-collapse:collapse;width:100%}
th,td{border-bottom:1px solid #e5e7eb;padding:8px;text-align:left}
.btn{padding:6px 12px;border-radius:6px;border:1px solid #cbd5e1;background:#fff}
.btn-primary{background:#2563eb;color:#fff;border-color:#2563eb}
.btn-danger{background:#dc2626;color:#fff;border-color:#dc2626}
.card{border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:12px 0}
.muted{color:#9ca3af}"""

NAV = [("users", "Users"), ("teams", "Teams"), ("roles", "Roles"), ("invoices", "Invoices"),
       ("audit-log", "Audit log"), ("settings", "Settings")]


def page(title, body, active=None):
    nav = "".join(f'<a href="{key}.html"{" class=active" if key == active else ""}>{label}</a>'
                  for key, label in NAV)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
            f'<link rel="stylesheet" href="../app.css"></head><body><header><strong>Ledgerly Admin</strong>'
            f'{nav}</header><main>{body}</main></body></html>\n')


def table(head, rows):
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"


ADMIN = {
    # Deliberate inconsistencies: Members/Users, Groups/Teams, Remove/Delete/Archive/Deactivate,
    # Save/Apply/Update, red primary vs blue primary, confirm dialogs on some screens only.
    "users": ("Users", "<h1>Members</h1><p class=muted>People who can sign in.</p>"
              '<button class="btn btn-primary">Invite member</button>'
              + table(["Name", "Email", "Team", "Role", ""],
                      [["Ana Ortiz", "ana@example.test", "Finance", "Admin", '<button class="btn">Remove</button>'],
                       ["Ben Ito", "ben@example.test", "Support", "Viewer", '<button class="btn">Remove</button>'],
                       ["Cleo Park", "cleo@example.test", "Finance", "Editor", '<button class="btn">Remove</button>']])),
    "teams": ("Teams", "<h1>Groups</h1>"
              '<button class="btn btn-danger">New group</button>'
              + table(["Group", "Members", ""],
                      [["Finance", "2", '<button class="btn btn-danger" onclick="return confirm(\'Delete?\')">Delete</button>'],
                       ["Support", "1", '<button class="btn btn-danger" onclick="return confirm(\'Delete?\')">Delete</button>']])),
    "roles": ("Roles", "<h1>Permissions</h1>"
              + table(["Role", "Can edit invoices", "Can manage users", ""],
                      [["Admin", "yes", "yes", '<a href="#">Archive</a>'],
                       ["Editor", "yes", "no", '<a href="#">Archive</a>'],
                       ["Viewer", "no", "no", '<a href="#">Archive</a>']])),
    "invoices": ("Invoices", "<h1>Billing documents</h1>"
                 '<div class="filters"><select><option>All statuses</option><option>Draft</option>'
                 "<option>Sent</option><option>Paid</option></select> <input placeholder=\"Customer\">"
                 ' <button class="btn">Update</button></div>'
                 + table(["No.", "Customer", "Total", "Status", ""],
                         [["INV-1042", "Northwind", "1,200.00", "Sent", '<button class="btn">Deactivate</button>'],
                          ["INV-1043", "Contoso", "310.50", "Draft", '<button class="btn">Deactivate</button>'],
                          ["CN-0007", "Northwind", "-120.00", "Paid", '<button class="btn">Deactivate</button>']])),
    "audit-log": ("Audit log", "<h1>Activity</h1>"
                  + table(["When", "Who", "What"],
                          [["2026-03-02 10:14", "Ana Ortiz", "removed member Dan Lee"],
                           ["2026-03-02 09:51", "Cleo Park", "deleted group Sales"],
                           ["2026-03-01 17:30", "Ana Ortiz", "archived role Auditor"]])),
    "settings": ("Settings", "<h1>Workspace settings</h1>"
                 '<div class="card"><label>Workspace name <input value="Ledgerly"></label>'
                 '<label>Default currency <select><option>EUR</option><option>USD</option></select></label>'
                 '<button class="btn btn-primary">Save</button></div>'
                 '<div class="card"><label>Invoice prefix <input value="INV-"></label>'
                 '<button class="btn">Apply</button></div>'),
}

DASHBOARD = page("Dashboard", "<h1>Dashboard</h1>"
                 '<div class="filters" style="display:flex;gap:6px;align-items:flex-start">'
                 '<select style="height:34px"><option>Last 30 days</option></select>'
                 '<input placeholder="Search customers" style="height:28px;margin-top:4px">'
                 '<button class="btn" style="padding:2px 8px">Apply filters</button>'
                 '<a href="#" style="margin-left:auto;font-size:11px">reset</a></div>'
                 '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">'
                 '<div class="card"><div class=muted>Revenue</div><b>12,400</b></div>'
                 '<div class="card"><div class=muted>Open invoices</div><b>31</b></div>'
                 '<div class="card"><div class=muted>Overdue</div><b style="color:#f87171">4</b></div></div>'
                 + table(["Customer", "Open", "Overdue"], [["Northwind", "3", "1"], ["Contoso", "2", "0"]]))

CHECKOUT = {
    "cart": page("Cart", "<h1>Your plan</h1><div class=card>Team plan · 5 seats · 50.00/month</div>"
                 '<a class="btn btn-primary" href="payment.html">Continue</a>'),
    "payment": page("Payment", "<h1>Payment</h1><form><label>Card number <input inputmode=numeric></label>"
                    "<label>Expiry <input placeholder=MM/YY></label><label>CVC <input></label>"
                    '<button class="btn btn-primary">Pay 50.00</button></form>'
                    '<p class=muted>Errors are shown after you submit.</p>'),
    "confirm": page("Done", "<h1>Thanks!</h1><p>Your subscription is active.</p>"),
}

SIGNUP = page("Sign up", "<h1>Create your account</h1><form>"
              '<input placeholder="Email"><input type="password" placeholder="Password">'
              '<input placeholder="Company"><button class="btn btn-primary">Create account</button></form>'
              '<p class=muted style="font-size:11px">By signing up you agree to the terms.</p>')

LANDING = page("Ledgerly", '<section style="text-align:center;padding:64px;background:linear-gradient(135deg,#7c3aed,#2563eb);color:#fff">'
               "<h1>Supercharge your billing workflow</h1><p>Unlock seamless, AI-powered invoicing.</p>"
               '<button class="btn">Get started free</button></section>'
               '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">'
               '<div class="card">⚡ Fast</div><div class="card">🔒 Secure</div><div class="card">📈 Scalable</div></div>')

DOCUMENTS = '''"""Billing documents and their totals."""
from dataclasses import dataclass, field
from decimal import Decimal

from .models import Customer, Line


@dataclass
class Document:
    number: str
    customer: Customer
    lines: list = field(default_factory=list)
    currency: str = "EUR"

    def subtotal(self):
        return sum((line.amount() for line in self.lines), Decimal("0"))

    def tax(self):
        return (self.subtotal() * self.customer.tax_rate).quantize(Decimal("0.01"))

    def total(self):
        return self.subtotal() + self.tax()

    def render(self, fmt):
        if fmt == "pdf":
            return self._render_pdf()
        if fmt == "html":
            return self._render_html()
        if fmt == "csv":
            return ";".join([self.number, str(self.total())])
        raise ValueError(fmt)

    def _render_pdf(self):
        return b"%PDF-1.4 " + self.number.encode()

    def _render_html(self):
        return f"<h1>{self.number}</h1><p>{self.total()}</p>"


class Invoice(Document):
    def due_days(self):
        return 30 if self.customer.segment == "enterprise" else 14

    def send(self, mailer):
        mailer.send(self.customer.email, f"Invoice {self.number}", self.render("pdf"))


class CreditNote(Document):
    def total(self):
        return -super().total()

    def send(self, mailer):
        mailer.send(self.customer.email, f"Credit note {self.number}", self.render("pdf"))


class Quote(Document):
    valid_days = 30

    def send(self, mailer):
        mailer.send(self.customer.email, f"Quote {self.number}", self.render("html"))


class RecurringInvoice(Invoice, Quote):
    """An invoice issued every period; borrows the quote's validity window."""

    def next_number(self):
        prefix, n = self.number.rsplit("-", 1)
        return f"{prefix}-{int(n) + 1:04d}"


class ProformaInvoice(Quote):
    def due_days(self):
        return 0

    def send(self, mailer):
        if self.customer.segment == "enterprise":
            mailer.send(self.customer.email, f"Pro forma {self.number}", self.render("pdf"))
        else:
            mailer.send(self.customer.email, f"Pro forma {self.number}", self.render("html"))
'''

MODELS = '''from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Customer:
    name: str
    email: str
    segment: str = "smb"
    tax_rate: Decimal = Decimal("0.20")


@dataclass
class Line:
    description: str
    quantity: int
    unit_price: Decimal

    def amount(self):
        return self.unit_price * self.quantity
'''

NOTIFY = '''"""Sends customer notifications over several channels."""
import time


class Notifier:
    def __init__(self, email_client, sms_client, slack_client):
        self.email_client = email_client
        self.sms_client = sms_client
        self.slack_client = slack_client

    def notify(self, customer, channel, text):
        if channel == "email":
            for attempt in range(3):
                try:
                    return self.email_client.send(customer.email, "Ledgerly", text)
                except ConnectionError:
                    time.sleep(2 ** attempt)
        elif channel == "sms":
            for attempt in range(3):
                try:
                    return self.sms_client.send(customer.phone, text[:160])
                except ConnectionError:
                    time.sleep(2 ** attempt)
        elif channel == "slack":
            for attempt in range(3):
                try:
                    return self.slack_client.post(customer.slack_channel, text)
                except ConnectionError:
                    time.sleep(2 ** attempt)
        raise ValueError(channel)
'''

REPORT = '''from .documents import Invoice


def rows(documents):
    return [r for r in documents]


def overdue(documents, today):
    return [d for d in documents if isinstance(d, Invoice) and d.due_days() < today]
'''

EXPORT = '''import csv
import io

from .report import rows


def export_csv(documents):
    out = io.StringIO()
    writer = csv.writer(out)
    for document in rows(documents):
        writer.writerow([document.number, document.customer.name, document.total()])
    return out.getvalue()
'''

TESTS = '''from decimal import Decimal

from billing.documents import CreditNote, Invoice
from billing.models import Customer, Line


def test_invoice_total():
    c = Customer("Northwind", "ap@northwind.test")
    inv = Invoice("INV-0001", c, [Line("Seat", 5, Decimal("10.00"))])
    assert inv.total() == Decimal("60.00")


def test_credit_note_is_negative():
    c = Customer("Northwind", "ap@northwind.test")
    assert CreditNote("CN-0001", c, [Line("Refund", 1, Decimal("10.00"))]).total() < 0
'''

FILES = {
    "README.md": "# Ledgerly\n\nBilling service and admin UI for small finance teams. Python package in `src/billing`,\n"
                 "static admin screens in `ui/admin`, customer-facing pages in `ui/`.\n",
    "PLAN.md": "# Plan: CSV export for reports\n\n1. Add an export endpoint `/reports/{id}/export.csv`.\n"
               "2. Stream rows from the report query instead of building a list.\n3. Add an Export button to the "
               "invoices screen.\n4. Tests for the endpoint, including an empty report.\n5. Roll out behind a flag; "
               "remove the flag after one week.\n",
    "TASK.md": "# Task: package the export helper\n\nStatus: DONE. Tests pass locally.\n",
    "REVIEW-COMMENTS.md": "1. Rename `rows` to `records`.\n2. Use a generator instead of a list.\n3. Add a docstring.\n"
                          "4. Remove the global cache (it is used by two callers).\n5. Switch to pandas for CSV.\n"
                          "6. Add a test for empty reports.\n",
    "pyproject.toml": "[project]\nname = \"ledgerly\"\nversion = \"0.3.0\"\n\n[tool.coverage.report]\nfail_under = 90\n",
    "src/billing/__init__.py": "",
    "src/billing/models.py": MODELS,
    "src/billing/documents.py": DOCUMENTS,
    "src/billing/notify.py": NOTIFY,
    "src/billing/report.py": REPORT,
    "tests/test_documents.py": TESTS,
    "ui/app.css": STYLE + "\n",
    "ui/dashboard.html": DASHBOARD,
    "ui/signup-form.html": SIGNUP,
    "ui/landing.html": LANDING,
    "ui/settings.html": page("Account settings", "<h1>Account</h1><div class=card><label>Name <input></label>"
                             "<label>Email <input></label><button class=\"btn btn-primary\" style=\"width:90px;"
                             "white-space:nowrap;overflow:hidden\">Save all changes now</button></div>"),
}
FILES.update({f"ui/admin/{k}.html": page(t, b, k) for k, (t, b) in ADMIN.items()})
FILES.update({f"ui/checkout/{k}.html": v for k, v in CHECKOUT.items()})


def png(width, height, boxes):
    """A flat RGB PNG: light background with filled boxes (x, y, w, h, rgb)."""
    canvas = [bytearray([246, 247, 249] * width) for _ in range(height)]
    for x, y, w, h, rgb in boxes:
        for row in range(y, min(y + h, height)):
            canvas[row][x * 3:(x + w) * 3] = bytes(rgb) * w
    raw = b"".join(b"\x00" + bytes(row) for row in canvas)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# A settings-screen mockup: top bar, left nav, two cards with fields and a primary button.
MOCKUP = png(1280, 800, [
    (0, 0, 1280, 56, (15, 23, 42)), (24, 18, 140, 20, (255, 255, 255)),
    (0, 56, 220, 744, (255, 255, 255)), (24, 88, 160, 16, (203, 213, 225)), (24, 120, 140, 16, (37, 99, 235)),
    (24, 152, 150, 16, (203, 213, 225)), (260, 88, 320, 28, (31, 35, 40)),
    (260, 140, 980, 220, (255, 255, 255)), (284, 168, 200, 14, (100, 116, 139)), (284, 192, 420, 40, (229, 231, 235)),
    (284, 252, 200, 14, (100, 116, 139)), (284, 276, 420, 40, (229, 231, 235)), (1096, 300, 120, 40, (37, 99, 235)),
    (260, 384, 980, 160, (255, 255, 255)), (284, 412, 200, 14, (100, 116, 139)), (284, 436, 420, 40, (229, 231, 235)),
    (1096, 484, 120, 40, (37, 99, 235)),
])


def git(dest, *args):
    env = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_AUTHOR_DATE": "2026-03-01T10:00:00Z", "GIT_COMMITTER_DATE": "2026-03-01T10:00:00Z",
           "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(dest)}
    subprocess.run(["git", *args], cwd=dest, env=env, check=True, capture_output=True)


def build(dest):
    dest = pathlib.Path(dest)
    if dest.exists():
        raise SystemExit(f"{dest} exists; give a new directory")
    for rel, text in FILES.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (dest / "ui/reference").mkdir(parents=True)
    (dest / "ui/reference/settings-mockup.png").write_bytes(MOCKUP)
    git(dest, "init", "-q", "-b", "main")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "Ledgerly billing service and admin UI")
    git(dest, "checkout", "-q", "-b", "feature/csv-export")
    (dest / "src/billing/export.py").write_text(EXPORT, encoding="utf-8")
    invoices = dest / "ui/admin/invoices.html"
    invoices.write_text(invoices.read_text(encoding="utf-8").replace(
        "<h1>Billing documents</h1>", '<h1>Billing documents</h1><button class="btn">Export CSV</button>'), encoding="utf-8")
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "Add CSV export")
    return dest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(build(sys.argv[1]))

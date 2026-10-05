import base64
import csv
import shutil
import hashlib
import io
import re
import json
import os
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus.flowables import KeepInFrame
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

APP_TITLE = "CVP Project Billing & Invoice Management"
DEFAULT_CLIENT_NAME = "BEIL INFRASTRUCTURE LIMITED"
COMPANY_DETAILS = (
    "M/s. C.V. PATIL AND ASSOCIATES",
    "1002, 10th Floor, Trident Business Center, Mumbai-Bangalore Highway, Opp. Audi Show Room, Baner, Pune-411045",
    "cvpcepl@gmail.com",
    "09552541940",
    "27AKDPP4541Q1ZL",
    "Account No.: 20104701501\nBank of Maharashtra\nIFS Code: MAHB0000776\nDhankawadi, Pune-411043",
    "If the payment is received on & before date 6th of Next Month (For GST Payment), then only this invoice is valid. Else this is declared as not valid for this invoice date.",
)
COMPANY_NAMES = [
    "M/s. C.V. PATIL AND ASSOCIATES",
    "CEMECH INFRASOLUTIONS",
    "C.V.PATIL CONSULTANCY ENGINEERS PVT.LTD.",
    "CREATIVE VENTURES",
]
DB_FILE = os.path.join(os.path.dirname(__file__), "cvp_invoice.db")
LOGO_FILE = os.path.join(os.path.dirname(__file__), "logo.png")
STATEMENT_DIR = os.path.join(os.path.dirname(__file__), "bank_statements")
SITE_NAME = "C V PATIL & ASSOCIATES"
# GST state codes. CGST + SGST applies only to Maharashtra (the supplier's state); every other state is IGST.
GST_STATES = {
    "Jammu & Kashmir": "01", "Himachal Pradesh": "02", "Punjab": "03", "Chandigarh": "04", "Uttarakhand": "05",
    "Haryana": "06", "Delhi": "07", "Rajasthan": "08", "Uttar Pradesh": "09", "Bihar": "10", "Sikkim": "11",
    "Arunachal Pradesh": "12", "Nagaland": "13", "Manipur": "14", "Mizoram": "15", "Tripura": "16", "Meghalaya": "17",
    "Assam": "18", "West Bengal": "19", "Jharkhand": "20", "Odisha": "21", "Chhattisgarh": "22", "Madhya Pradesh": "23",
    "Gujarat": "24", "Dadra & Nagar Haveli and Daman & Diu": "26", "Maharashtra": "27", "Karnataka": "29", "Goa": "30",
    "Lakshadweep": "31", "Kerala": "32", "Tamil Nadu": "33", "Puducherry": "34", "Andaman & Nicobar Islands": "35",
    "Telangana": "36", "Andhra Pradesh": "37", "Ladakh": "38",
}


def normalize_state(name):
    key = (name or "").strip().lower()
    if key == "gujrat":
        key = "gujarat"
    for s in GST_STATES:
        if s.lower() == key:
            return s
    return (name or "").strip() or "Maharashtra"


def gst_mode_for_state(name):
    return "CGST + SGST" if normalize_state(name) == "Maharashtra" else "IGST"

st.set_page_config(page_title=APP_TITLE, page_icon="🧾", layout="wide", initial_sidebar_state="collapsed")

# ---------- Styling ----------
st.markdown(
    """
    <style>
    :root { --primary:#0b7285; --accent:#1098ad; --ink:#183153; --soft:#f3f8fa; }
    .stApp { background: linear-gradient(180deg,#f8fcfd 0%,#ffffff 40%); }
    .block-container { padding-top: 1.3rem; padding-bottom: 2rem; max-width: 1450px; }
    header[data-testid="stHeader"] { background: transparent; }
    section[data-testid="stSidebar"], div[data-testid="stSidebarCollapsedControl"], div[data-testid="collapsedControl"] { display:none !important; }
    .topbar-brand { display:flex; align-items:center; gap:.8rem; margin-bottom:.8rem; }
    .topbar-brand img { height:48px; }
    .topbar-brand span { font-size:1.45rem; font-weight:800; letter-spacing:.5px; color:#0f2f6b; white-space:nowrap; }
    div[data-testid="stLinkButton"] a { background:linear-gradient(120deg,#0f2f6b,#0b6bc2); color:#fff !important; border:none; border-radius:12px; font-weight:700; padding:.65rem 1.1rem; box-shadow:0 6px 16px rgba(15,47,107,.25); }
    .dash-head { display:flex; justify-content:space-between; align-items:center; margin:.3rem 0 1rem; }
    .dash-title { font-size:1.9rem; font-weight:800; color:#0f2f6b; line-height:1.1; }
    .dash-sub { color:#64748b; font-size:.95rem; margin-top:.2rem; }
    .dash-chip { background:linear-gradient(120deg,#0f2f6b,#0b6bc2); color:#fff; padding:.4rem .95rem; border-radius:999px; font-weight:700; font-size:.85rem; box-shadow:0 6px 16px rgba(15,47,107,.2); }
    .kpi-row { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:1rem; margin-bottom:1.6rem; }
    .kpi { background:#fff; border-radius:18px; padding:1.1rem 1.2rem; border:1px solid #e8eef3; border-top:4px solid var(--accent); box-shadow:0 8px 24px rgba(15,47,107,.07); }
    .kpi-label { color:#64748b; font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.6px; }
    .kpi-value { color:#0f2f6b; font-size:1.65rem; font-weight:800; margin:.35rem 0 .15rem; }
    .kpi-note { color:#94a3b8; font-size:.8rem; }
    .panel-title { font-size:1.05rem; font-weight:800; color:#0f2f6b; margin:.9rem 0 .5rem; }
    .prog { background:#fff; border:1px solid #e8eef3; border-radius:16px; padding:.9rem 1.1rem; margin-bottom:.7rem; box-shadow:0 4px 14px rgba(15,47,107,.05); }
    .prog-top { display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap; }
    .prog-name { font-weight:700; color:#1f2f4d; }
    .prog-val { color:#0b6bc2; font-weight:700; font-size:.9rem; }
    .prog-bar { height:10px; background:#e8f0fa; border-radius:999px; margin:.6rem 0 .4rem; overflow:hidden; }
    .prog-fill { height:100%; background:linear-gradient(90deg,#0b7285,#3b8bf0); border-radius:999px; }
    .prog-sub { color:#94a3b8; font-size:.8rem; }
    .bank-banner { display:flex; align-items:center; gap:.9rem; background:linear-gradient(120deg,#0f2f6b,#0b6bc2); color:#fff; border-radius:16px; padding:.9rem 1.2rem; margin-bottom:.8rem; box-shadow:0 8px 20px rgba(15,47,107,.22); }
    .bank-icon { width:46px; height:46px; border-radius:12px; background:rgba(255,255,255,.16); display:flex; align-items:center; justify-content:center; flex:none; }
    .bank-title { font-size:1.25rem; font-weight:800; line-height:1.15; }
    .bank-sub { font-size:.85rem; opacity:.85; margin-top:.1rem; }
    div[data-testid="stVerticalBlock"] { gap: .6rem; }
    div[data-testid="stHorizontalBlock"] { gap: .8rem; }
    .block-container { padding-top: .8rem !important; padding-bottom: 1rem !important; }
    .block-container h2 { font-size:1.35rem; margin:.2rem 0 .3rem; padding:0; line-height:1.5 !important; }
    .block-container h3 { font-size:1.15rem; margin:.2rem 0 .3rem; padding:0; line-height:1.5 !important; }
    .block-container h4 { font-size:1.05rem; margin:.15rem 0 .25rem; padding:0; line-height:1.5 !important; }
    div[data-testid="stMarkdownContainer"] p { margin-bottom:.25rem; }
    div[data-testid="stMarkdownContainer"] hr { margin:.4rem 0; }
    div[data-testid="stWidgetLabel"] { margin-bottom:.2rem; }
    div[data-testid="stExpander"] details summary { padding-top:.4rem; padding-bottom:.4rem; }
    .hero { padding: 1.2rem 1.4rem; border-radius: 18px; background: linear-gradient(120deg,#083344,#0b7285); color:white; margin-bottom:1rem; box-shadow:0 8px 24px rgba(8,51,68,.18); }
    .hero h1 { margin:0; font-size:1.85rem; }
    .hero p { margin:.35rem 0 0; opacity:.9; }
    .card { background:white; border:1px solid #e5eef1; border-radius:16px; padding:1rem 1.15rem; box-shadow:0 4px 18px rgba(24,49,83,.06); }
    .muted { color:#64748b; font-size:.92rem; }
    .badge { display:inline-block; padding:.22rem .55rem; border-radius:999px; background:#e6f7fa; color:#0b7285; font-size:.82rem; font-weight:600; }
    .co-box { border:1.5px solid #0b7285; border-radius:12px; background:#fff; overflow:hidden; box-shadow:0 2px 10px rgba(11,114,133,.12); font-size:.86rem; color:#183153; }
    .co-title { background:#0b7285; color:#fff; font-weight:700; padding:.5rem .8rem; font-size:.95rem; letter-spacing:.2px; }
    .co-name { padding:.6rem .8rem .3rem; font-weight:700; font-size:.92rem; }
    .co-row { padding:.3rem .8rem; border-top:1px dashed #d5e6ea; line-height:1.35; }
    .co-label { display:block; color:#64748b; font-size:.72rem; text-transform:uppercase; letter-spacing:.5px; font-weight:600; }
    div[data-testid="stMetricValue"] { font-size:1.35rem; }
    div[data-testid="stMetricValue"] > div { overflow:visible !important; text-overflow:clip !important; white-space:normal !important; }
    div[data-testid="stMetric"] { background:white; border:1px solid #e5eef1; border-radius:14px; padding:.8rem 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def project_label(p):
    """Unique dropdown label (two projects may share a name, so the P.O. no. and id are included)."""
    po = f" · P.O. {p['po_no']}" if p.get('po_no') else ""
    return f"{p['client_name']} — {p['project_name']}{po} [#{p['id']}]"


WATERMARK_FILE = os.path.join(os.path.dirname(__file__), "logo_watermark.png")


def watermark_image():
    """A smoothly enlarged copy of the logo (the original is small, so drawing it directly looks pixelated)."""
    if os.path.exists(WATERMARK_FILE):
        return WATERMARK_FILE
    if not os.path.exists(LOGO_FILE):
        return None
    try:
        from PIL import Image as PILImage
        im = PILImage.open(LOGO_FILE).convert("RGBA")
        im = im.resize((im.width * 6, im.height * 6), PILImage.LANCZOS)
        im.save(WATERMARK_FILE)
        return WATERMARK_FILE
    except Exception:
        return LOGO_FILE


def draw_watermark(canvas, doc):
    """Company logo behind the content of every page."""
    path = watermark_image()
    if not path:
        return
    w, h = doc.pagesize
    img_w = min(w, h) * 0.60
    img_h = img_w * 392 / 376
    canvas.saveState()
    canvas.setFillAlpha(0.12)
    canvas.drawImage(path, (w - img_w) / 2, (h - img_h) / 2, img_w, img_h, mask="auto", preserveAspectRatio=True)
    canvas.restoreState()


def fit_widths(widths, avail):
    """Scales column widths (mm) so that they add up to the printable width."""
    k = avail / sum(widths)
    return [w * k for w in widths]


def invoice_serial(row):
    """Sort key that puts invoices in serial order (01, 02, 03 ...) of their number."""
    head = (row.get('invoice_no') or "").split("/")[0]
    return (int(head) if head.isdigit() else 10**9, row.get('id') or 0)


STATUS_LABEL = {"Paid": "🟢 Paid", "Partially Paid": "🟡 Partially Paid", "Overdue": "🔴 Overdue", "Pending": "⚪ Pending"}
PAYMENT_DUE_DAYS = 30


def invoice_payment(row):
    """Payment position of a saved invoice: TDS (basic x rate), amount received, balance still to collect and status."""
    basic = float(row.get('basic_amount') or 0)
    total = float(row.get('grand_total') or 0)
    rate = float(row['tds_rate']) if row.get('tds_rate') is not None else 10.0
    tds = round(basic * rate / 100, 2)
    paid = float(row.get('paid_amount') or 0)
    balance = max(round(total - tds - paid, 2), 0.0)
    try:
        inv_d = date.fromisoformat(str(row.get('invoice_date'))[:10])
    except Exception:
        inv_d = date.today()
    if total > 0 and balance <= 0.5:
        status = "Paid"
    elif paid > 0:
        status = "Partially Paid"
    elif (date.today() - inv_d).days > PAYMENT_DUE_DAYS:
        status = "Overdue"
    else:
        status = "Pending"
    return {"rate": rate, "tds": tds, "paid": paid, "balance": balance, "status": status}


def client_payment_profile(client_name):
    """How this client has paid in the past: days taken to pay, share of invoices paid, invoices overdue now."""
    c = conn()
    rows = [dict(r) for r in c.execute(
        "SELECT i.* FROM invoices i JOIN projects p ON p.id=i.project_id WHERE p.client_name=? AND i.invoice_type='Tax Invoice' AND i.grand_total>0",
        (client_name,)).fetchall()]
    c.close()
    delays, n_paid, n_overdue = [], 0, 0
    for r in rows:
        pay = invoice_payment(r)
        if pay["status"] == "Paid":
            n_paid += 1
        elif pay["status"] == "Overdue":
            n_overdue += 1
        if pay["paid"] > 0 and r.get("paid_date"):
            try:
                delays.append(max((date.fromisoformat(r["paid_date"]) - date.fromisoformat(str(r["invoice_date"])[:10])).days, 0))
            except Exception:
                pass
    delays.sort()
    median = delays[len(delays) // 2] if delays else None
    return {"n": len(rows), "n_paid": n_paid, "n_overdue": n_overdue, "delays": len(delays), "median_days": median,
            "paid_pct": (n_paid / len(rows) * 100) if rows else 0.0}


def payment_outlook(row, pay, profile):
    """Simple history-based outlook for an unpaid invoice: (expected payment date, label)."""
    if pay["status"] == "Paid":
        return None, "🟢 Paid"
    if profile["delays"] < 2 or profile["median_days"] is None:
        return None, "⚪ Not enough history"
    try:
        inv_d = date.fromisoformat(str(row.get("invoice_date"))[:10])
    except Exception:
        inv_d = date.today()
    expected = inv_d + timedelta(days=int(profile["median_days"]))
    age = (date.today() - inv_d).days
    slack = max(int(profile["median_days"]) * 0.5, 7)
    if age <= profile["median_days"]:
        return expected, "🟢 Likely to pay on time"
    if age <= profile["median_days"] + slack and profile["paid_pct"] >= 50:
        return expected, "🟡 Likely to pay, but late"
    return expected, "🔴 At risk of non-payment"


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def read_bank_statement(upload):
    """Reads an uploaded CSV / Excel bank statement into a DataFrame (finds the header row automatically)."""
    name = upload.name.lower()
    if name.endswith(".csv"):
        data = upload.read()
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        lines = [ln for ln in csv.reader(io.StringIO(text)) if any(c.strip() for c in ln)]
        width = max((len(ln) for ln in lines), default=0)
        raw = pd.DataFrame([ln + [""] * (width - len(ln)) for ln in lines], dtype=str)
    else:
        raw = pd.read_excel(upload, header=None, dtype=str).fillna("")
    hdr = 0
    for i in range(min(len(raw), 40)):
        cells = [str(x).lower() for x in raw.iloc[i].tolist()]
        if any("date" in c for c in cells) and any(k in c for c in cells for k in ("credit", "deposit", "amount", "cr")):
            hdr = i
            break
    df = raw.iloc[hdr + 1:].copy()
    df.columns = [str(x).strip() or f"Column {j + 1}" for j, x in enumerate(raw.iloc[hdr].tolist())]
    return df.reset_index(drop=True)


def guess_column(columns, keys):
    for k in keys:
        for c in columns:
            if k in str(c).lower():
                return c
    return columns[0] if columns else None


def to_amount(v):
    s = str(v or "").replace(",", "").replace("₹", "").replace("Cr", "").replace("CR", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def match_bank_credits(credits, invoices):
    """Match each bank credit to an open invoice: invoice number in the narration, exact amount, and client name.
    credits: list of dicts(date, desc, amount). invoices: list of dicts(row, pay, client). Returns the credits with a match."""
    out = []
    for cr in credits:
        d = _norm(cr["desc"]); best = None; best_score = 0
        ms_ref = re.search(r"milestone\s*(?:no\.?|#)?\s*(\d+)", str(cr["desc"]), re.I)
        ms_no = int(ms_ref.group(1)) if ms_ref else None
        if ms_no:
            # the narration names a milestone: find the invoice of this client that bills it (prefer one that bills only it)
            found = []
            for inv in invoices:
                words = [w for w in re.split(r"[^a-z0-9]+", inv["client"].lower()) if len(w) > 3 and w not in ("limited", "private", "infrastructure", "pvt")]
                if not (any(w in d for w in words) or _norm(inv["client"])[:10] in d):
                    continue
                try:
                    items = json.loads(inv["row"]["items_json"]) if inv["row"].get("items_json") else []
                except Exception:
                    items = []
                billed = [i for i in items if i.get("billed", True) and float(i.get("amount") or 0) > 0]
                if any(i.get("sr") == ms_no for i in billed):
                    found.append((len(billed), invoice_serial(inv["row"]), inv))
            if found:
                found.sort(key=lambda x: (x[0], x[1]))
                best, best_score = found[0][2], 200
                item = dict(cr); item["invoice_no"] = best["row"]["invoice_no"]; item["score"] = 200; item["milestone"] = ms_no
                total = float(best["row"]["grand_total"] or 0)
                item["apply"] = round(min(cr["amount"], max(total - best["pay"]["paid"], 0)), 2)
                out.append(item)
                continue
        for inv in invoices:
            bal = inv["pay"]["balance"]
            if bal <= 0.5:
                continue
            score = 0
            no = inv["row"]["invoice_no"]
            if _norm(no) in d:
                score += 100
            if abs(cr["amount"] - bal) <= 1:
                score += 50
            elif abs(cr["amount"] - float(inv["row"]["grand_total"] or 0)) <= 1:
                score += 40
            words = [w for w in re.split(r"[^a-z0-9]+", inv["client"].lower()) if len(w) > 3 and w not in ("limited", "private", "infrastructure", "pvt")]
            if any(w in d for w in words) or _norm(inv["client"])[:10] in d:
                score += 20
            if score > best_score or (score == best_score and best is not None and invoice_serial(inv["row"]) < invoice_serial(best["row"])):
                if score >= 50 or (score >= 20 and cr["amount"] < bal):
                    best, best_score = inv, score
        item = dict(cr); item["invoice_no"] = best["row"]["invoice_no"] if best else None; item["score"] = best_score if best else 0; item["milestone"] = None
        item["apply"] = round(min(cr["amount"], best["pay"]["balance"]), 2) if best else 0.0
        out.append(item)
    return out


def apply_milestone_credit(cu, project_id, n, amount, pay_date, ref):
    """A credit that names a milestone is booked on that milestone: received amount, balance, and completed when settled."""
    m = cu.execute("SELECT * FROM milestones WHERE project_id=? AND milestone_no=?", (project_id, n)).fetchone()
    if not m:
        return
    m = dict(m)
    basic = float(m.get("amount") or 0)
    sched = float(m["scheduled_amount"]) if m.get("scheduled_amount") is not None else round(basic * (1 + float(m.get("gst_rate") or 18) / 100), 2)
    rate = float(m["tds_rate"]) if m.get("tds_rate") is not None else 10.0
    tds = round(basic * rate / 100, 2)
    received = float(m.get("actual_amount") or 0) + amount
    done = received + tds >= sched - 0.5
    day = (pay_date or date.today()).isoformat()
    if done:
        cu.execute("UPDATE milestones SET actual_amount=?, actual_payment_date=?, balance_amount=0, payment_status='Collected', completed_on=?, completed_invoice=?, completed_amount=? WHERE id=?",
                   (received, day, day, ref, received, m["id"]))
    else:
        cu.execute("UPDATE milestones SET actual_amount=?, actual_payment_date=?, balance_amount=?, payment_status='Partially Collected' WHERE id=?",
                   (received, day, max(sched - received - tds, 0.0), m["id"]))


def apply_credit_to_invoice(cu, running, inv, amount, pay_date, milestone=None):
    """Adds a bank credit to an invoice (and to its milestone when the narration names one). Returns (amount applied, balance left)."""
    no = inv["row"]["invoice_no"]
    total = float(inv["row"]["grand_total"] or 0); tds = inv["pay"]["tds"]
    stt = running.setdefault(no, {"paid": inv["pay"]["paid"]})
    cap = (total - stt["paid"]) if milestone else max(total - tds - stt["paid"], 0.0)
    amt = min(amount, cap)
    if amt <= 0:
        return 0.0, None
    stt["paid"] += amt
    cu.execute("UPDATE invoices SET paid_amount=?, paid_date=? WHERE id=?", (stt["paid"], (pay_date or date.today()).isoformat(), inv["row"]["id"]))
    if milestone:
        apply_milestone_credit(cu, inv["row"]["project_id"], milestone, amt, pay_date, no)
    return amt, max(total - tds - stt["paid"], 0.0)


def milestone_status_lines(project_id):
    """Completed / partially paid / not completed milestone numbers of a project, as one readable text."""
    ms = fetch_milestones(project_id)
    done = [m["milestone_no"] for m in ms if m.get("completed_on")]
    part = [m["milestone_no"] for m in ms if not m.get("completed_on") and m.get("payment_status") == "Partially Collected"]
    rest = [m["milestone_no"] for m in ms if not m.get("completed_on") and m.get("payment_status") != "Partially Collected"]
    fmt = lambda xs: ", ".join(str(x) for x in xs) if xs else "none"
    return (f"🟢 Completed ({len(done)}): {fmt(done)}  |  🟡 Partially paid ({len(part)}): {fmt(part)}  |  ⚪ Not completed ({len(rest)}): {fmt(rest)}")


def is_blank_milestone(m):
    """A milestone that was only created (default name such as 'Milestone 5', no amount, not completed) and never filled in."""
    name = (m.get("description") or "").strip()
    default_name = (not name) or bool(re.fullmatch(r"Milestone \d+", name))
    return default_name and float(m.get("amount") or 0) <= 0 and not m.get("completed_on")


def pdf_items_for(invoice_row, milestones, chosen=None):
    """Lines for the invoice PDF, same layout every time: the project's milestones (all of them, or only `chosen`) with the
    percentage taken from the milestone. Only the milestone(s) billed on this invoice show a rate and amount."""
    try:
        saved = json.loads(invoice_row["items_json"]) if invoice_row.get("items_json") else None
    except Exception:
        saved = None
    if not saved:
        saved = [{"sr": 1, "description": invoice_row.get("description") or "", "hsn": invoice_row.get("hsn_code") or "998337",
                  "qty": invoice_row.get("qty_text") or "", "amount": float(invoice_row.get("basic_amount") or 0), "billed": True}]
    by_desc = {(i.get("description") or ""): i for i in saved}
    inv_pay = invoice_payment(invoice_row)
    def _billed_here(m):
        it = by_desc.get(m.get("description") or m.get("milestone_name") or "")
        return bool(it and it.get("billed", True) and float(it.get("amount") or 0) > 0)
    # milestones that are already completed (paid) are not printed again, unless this invoice itself bills them
    pool = [m for m in milestones if (not chosen or m["id"] in chosen) and (not m.get("completed_on") or _billed_here(m))
            and (not is_blank_milestone(m) or (m.get("description") or "") in by_desc)]
    lines, used = [], set()
    for m in sorted(pool, key=lambda m: m["milestone_no"]):
        desc = m.get("description") or m.get("milestone_name") or ""
        item = by_desc.get(desc)
        amount = float(item.get("amount") or 0) if item and item.get("billed", True) else 0.0
        if item:
            used.add(desc)
        if amount > 0:                         # billed on this invoice: follow this invoice's payment
            pay_txt = {"Paid": "Completed", "Partially Paid": "Part paid"}.get(inv_pay["status"], "Not completed")
        elif m.get("completed_on"):
            pay_txt = "Completed (" + dmy(m["completed_on"]) + ")"
        else:
            pay_txt = "Part paid" if m.get("payment_status") == "Partially Collected" else "Not completed"
        lines.append({"sr": m["milestone_no"], "description": desc, "hsn": (item or {}).get("hsn") or m.get("hsn_code") or "998337",
                      "qty": f"{float(m.get('percentage') or 0):.0f}%", "amount": amount, "billed": amount > 0, "pay": pay_txt})
    for i in saved:          # billed lines that are not project milestones (typed by hand) are always kept
        if (i.get("description") or "") not in used and i.get("billed", True) and float(i.get("amount") or 0) > 0:
            lines.append(dict(i))
    lines.sort(key=lambda i: i["sr"])
    return lines


def current_project_for(ids):
    """The project picked on the Clients & Projects page is the current project everywhere."""
    cp = st.session_state.get("current_project")
    if cp not in ids:
        cp = ids[0] if ids else None
        st.session_state["current_project"] = cp
    return cp


def set_current_project(key):
    st.session_state["current_project"] = st.session_state[key]


def fy_label(d: date):
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{str(y+1)[-2:]}"


# ---------- Database ----------
def conn():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = conn()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS company (
            id INTEGER PRIMARY KEY CHECK(id=1),
            name TEXT, address TEXT, email TEXT, mobile TEXT, gstin TEXT,
            bank_details TEXT, terms TEXT
        );
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL, project_name TEXT NOT NULL,
            billing_address TEXT, site_address TEXT, location TEXT,
            state TEXT, state_code TEXT, gstin TEXT, pan TEXT,
            po_no TEXT, po_date TEXT, po_amount REAL DEFAULT 0,
            vendor_id TEXT, kind_attention TEXT
        );
        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            milestone_no INTEGER, description TEXT,
            percentage REAL DEFAULT 0, amount REAL DEFAULT 0,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            invoice_type TEXT, invoice_no TEXT UNIQUE,
            invoice_date TEXT, hsn_code TEXT,
            description TEXT, qty_text TEXT,
            basic_amount REAL, tax_mode TEXT,
            tax_rate REAL, cgst REAL, sgst REAL, igst REAL,
            grand_total REAL, payment_mode TEXT,
            created_at TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        """
    )
    # Add milestone tracking fields without changing existing saved records.
    milestone_columns = {row[1] for row in c.execute("PRAGMA table_info(milestones)")}
    for column, definition in {
        "milestone_name": "TEXT DEFAULT ''",
        "due_date": "TEXT",
        "tax_invoice_no": "TEXT DEFAULT ''",
        "payment_status": "TEXT DEFAULT 'Pending'",
        "invoice_type": "TEXT DEFAULT 'Tax Invoice'",
        # Proforma / Tax Invoice specific inputs.
        "invoice_date": "TEXT",
        "hsn_code": "TEXT DEFAULT '998337'",
        "gst_mode": "TEXT DEFAULT ''",
        "gst_rate": "REAL DEFAULT 18",
        "payment_mode": "TEXT DEFAULT 'Bank Transfer / Online'",
        "valid_until": "TEXT",
        "payment_terms": "TEXT DEFAULT ''",
        "proforma_ref": "TEXT DEFAULT ''",
        "advance_received": "REAL DEFAULT 0",
        "actual_payment_date": "TEXT",
        "actual_amount": "REAL DEFAULT 0",
        "gst_amount": "REAL",
        "scheduled_amount": "REAL",
        "balance_amount": "REAL",
        "tds_amount": "REAL DEFAULT 0",
        "tds_rate": "REAL",
        "completed_on": "TEXT",
        "completed_invoice": "TEXT",
        "completed_amount": "REAL",
    }.items():
        if column not in milestone_columns:
            c.execute(f"ALTER TABLE milestones ADD COLUMN {column} {definition}")
    invoice_columns = {row[1] for row in c.execute("PRAGMA table_info(invoices)")}
    if "items_json" not in invoice_columns:
        c.execute("ALTER TABLE invoices ADD COLUMN items_json TEXT")
    if "bill_state" not in invoice_columns:
        c.execute("ALTER TABLE invoices ADD COLUMN bill_state TEXT")
    c.execute("CREATE TABLE IF NOT EXISTS bank_credits (hash TEXT PRIMARY KEY, invoice_no TEXT, amount REAL, applied_on TEXT)")
    for _col, _def in {"paid_amount": "REAL DEFAULT 0", "paid_date": "TEXT", "tds_rate": "REAL"}.items():
        if _col not in invoice_columns:
            c.execute(f"ALTER TABLE invoices ADD COLUMN {_col} {_def}")
    # Financial year of each project, so previous-year projects can be reopened.
    project_columns = {row[1] for row in c.execute("PRAGMA table_info(projects)")}
    if "financial_year" not in project_columns:
        c.execute("ALTER TABLE projects ADD COLUMN financial_year TEXT")
    for pid, po_date in c.execute("SELECT id, po_date FROM projects WHERE financial_year IS NULL OR financial_year=''").fetchall():
        try:
            fy = fy_label(date.fromisoformat(po_date))
        except Exception:
            fy = fy_label(date.today())
        c.execute("UPDATE projects SET financial_year=? WHERE id=?", (fy, pid))
    # Company details start from COMPANY_DETAILS and can then be edited on the Company Setup page.
    c.execute(
        "INSERT OR IGNORE INTO company(id,name,address,email,mobile,gstin,bank_details,terms) VALUES(1,?,?,?,?,?,?,?)",
        COMPANY_DETAILS,
    )
    # Several firms can issue invoices: each has its own details; the first one is the original company.
    c.execute("CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, address TEXT, email TEXT, mobile TEXT, gstin TEXT, bank_details TEXT, terms TEXT)")
    if c.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
        first = c.execute("SELECT name,address,email,mobile,gstin,bank_details,terms FROM company WHERE id=1").fetchone() or COMPANY_DETAILS
        c.execute("INSERT INTO companies(id,name,address,email,mobile,gstin,bank_details,terms) VALUES(1,?,?,?,?,?,?,?)", tuple(first))
    have = {r[0] for r in c.execute("SELECT name FROM companies").fetchall()}
    for nm in COMPANY_NAMES:
        if nm not in have:
            common = c.execute("SELECT address,email,mobile,gstin,bank_details,terms FROM companies WHERE id=1").fetchone() or COMPANY_DETAILS[1:]
            c.execute("INSERT INTO companies(name,address,email,mobile,gstin,bank_details,terms) VALUES(?,?,?,?,?,?,?)", (nm,) + tuple(common))
    first = c.execute("SELECT address,email,mobile,gstin,bank_details,terms FROM companies WHERE id=1").fetchone()
    if first and (first[0] or first[3]):
        c.execute("UPDATE companies SET address=?, email=?, mobile=?, gstin=?, bank_details=?, terms=? WHERE id<>1 AND COALESCE(address,'')='' AND COALESCE(gstin,'')=''", tuple(first))
    if "company_id" not in {row[1] for row in c.execute("PRAGMA table_info(projects)")}:
        c.execute("ALTER TABLE projects ADD COLUMN company_id INTEGER DEFAULT 1")
    c.commit()
    c.close()


init_db()


def fetch_companies():
    c = conn(); rows = c.execute("SELECT * FROM companies ORDER BY id").fetchall(); c.close(); return [dict(r) for r in rows]


def active_company_id():
    return st.session_state.get("active_company", 1)


def fetch_company(cid=None):
    cid = cid or active_company_id()
    c = conn(); r = c.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if r is None:
        r = c.execute("SELECT * FROM companies ORDER BY id LIMIT 1").fetchone()
    c.close(); return dict(r)


def fetch_projects(fy=None, company_id=None):
    c = conn()
    if fy:
        rows = c.execute("SELECT * FROM projects WHERE financial_year=? AND COALESCE(company_id,1)=? ORDER BY id DESC", (fy, company_id or active_company_id())).fetchall()
    else:
        rows = c.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    c.close(); return [dict(r) for r in rows]


FY_FIRST, FY_LAST = 2018, 2035


def fetch_financial_years():
    c = conn()
    c.execute("CREATE TABLE IF NOT EXISTS custom_years (year TEXT PRIMARY KEY)")
    rows = c.execute("SELECT DISTINCT financial_year FROM projects WHERE financial_year<>''").fetchall()
    custom = c.execute("SELECT year FROM custom_years").fetchall()
    c.close()
    years = {f"{y}-{str(y + 1)[-2:]}" for y in range(FY_FIRST, FY_LAST + 1)}
    years |= {r[0] for r in rows} | {r[0] for r in custom} | {fy_label(date.today())}
    return sorted(years, reverse=True)


def add_custom_year(text):
    """Accepts a typed financial year such as 2036-37 (or 2036) and stores it. Returns the normalized label or None."""
    s = (text or "").strip().replace("/", "-").replace(" ", "")
    m = re.fullmatch(r"(\d{4})(?:-(\d{2}|\d{4}))?", s)
    if not m:
        return None
    y = int(m.group(1))
    label = f"{y}-{str(y + 1)[-2:]}"
    if m.group(2) and m.group(2)[-2:] != str(y + 1)[-2:]:
        return None
    c = conn()
    c.execute("CREATE TABLE IF NOT EXISTS custom_years (year TEXT PRIMARY KEY)")
    c.execute("INSERT OR IGNORE INTO custom_years(year) VALUES(?)", (label,))
    c.commit(); c.close()
    return label


def fetch_project(project_id):
    c = conn(); r = c.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone(); c.close(); return dict(r) if r else None


def fetch_milestones(project_id, active_only=False):
    c = conn(); rows = c.execute("SELECT * FROM milestones WHERE project_id=? ORDER BY milestone_no, id", (project_id,)).fetchall(); c.close()
    rows = [dict(r) for r in rows]
    return [m for m in rows if not m.get("completed_on")] if active_only else rows


def sync_milestone_completion():
    """A milestone whose invoice is fully paid is completed: it leaves the active list and moves to the history.
    If the payment is later reduced, the milestone becomes active again."""
    c = conn()
    invs = [dict(r) for r in c.execute("SELECT * FROM invoices WHERE invoice_type='Tax Invoice'").fetchall()]
    for inv in invs:
        pay = invoice_payment(inv)
        try:
            items = json.loads(inv["items_json"]) if inv.get("items_json") else None
        except Exception:
            items = None
        if not items:
            items = [{"description": inv.get("description") or "", "amount": inv.get("basic_amount"), "billed": True}]
        names = [i.get("description") or "" for i in items if i.get("billed", True) and float(i.get("amount") or 0) > 0]
        for nm in names:
            if len(names) == 1 and pay["paid"] > 0:
                c.execute("UPDATE milestones SET advance_received=0, actual_amount=?, actual_payment_date=?, balance_amount=? "
                          "WHERE project_id=? AND description=? AND (completed_on IS NULL OR completed_invoice=?)",
                          (pay["paid"], inv.get("paid_date"), pay["balance"], inv["project_id"], nm, inv["invoice_no"]))
            if pay["status"] == "Paid":
                c.execute("UPDATE milestones SET completed_on=COALESCE(completed_on, ?), completed_invoice=?, completed_amount=?, payment_status='Collected' "
                          "WHERE project_id=? AND description=?",
                          (inv.get("paid_date") or date.today().isoformat(), inv["invoice_no"], pay["paid"], inv["project_id"], nm))
            else:
                c.execute("UPDATE milestones SET completed_on=NULL, completed_invoice=NULL, completed_amount=NULL WHERE project_id=? AND description=? AND completed_invoice=?",
                          (inv["project_id"], nm, inv["invoice_no"]))
                if len(names) == 1:
                    c.execute("UPDATE milestones SET payment_status=? WHERE project_id=? AND description=? AND completed_on IS NULL",
                              ("Partially Collected" if pay["status"] == "Partially Paid" else "Pending", inv["project_id"], nm))
    c.commit(); c.close()


def invoice_count_for_fy(fy):
    c = conn(); n = c.execute("SELECT COUNT(*) FROM invoices WHERE invoice_no LIKE ?", (f"%/{fy}",)).fetchone()[0]; c.close(); return n


def financial_year(d: date):
    y = d.year if d.month >= 4 else d.year - 1
    return f"{str(y)[-2:]}-{str(y+1)[-2:]}"


def allocate_invoice_no(c, d, invoice_type):
    fy = financial_year(d)
    prefix = "PI" if invoice_type == "Proforma Invoice" else "CVPA"
    used = c.execute("SELECT invoice_no FROM invoices UNION SELECT tax_invoice_no FROM milestones").fetchall()
    highest = 0
    for row in used:
        parts = (row[0] or "").split("/")
        if len(parts) == 3 and parts[1:] == [prefix, fy] and parts[0].isdigit():
            highest = max(highest, int(parts[0]))
    return f"{highest + 1:02d}/{prefix}/{fy}"


def next_invoice_no(d: date, invoice_type="Tax Invoice"):
    c = conn()
    try:
        return allocate_invoice_no(c, d, invoice_type)
    finally:
        c.close()


def inr(v):
    try:
        return f"₹ {float(v):,.2f}"
    except Exception:
        return "₹ 0.00"


def indian(v, dash_zero=True):
    """Indian digit grouping (12,50,000); whole rupees shown without decimals."""
    v = float(v or 0)
    if dash_zero and abs(v) < 0.005:
        return "-"
    whole = abs(v - round(v)) < 0.005
    s = f"{abs(round(v))}" if whole else f"{abs(v):.2f}"
    ip, _, fp = s.partition(".")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        ip = ",".join(parts + [tail])
    return ("-" if v < 0 else "") + ip + (("." + fp) if fp else "")


def dmy(s):
    try:
        return date.fromisoformat(str(s)[:10]).strftime("%d.%m.%Y")
    except Exception:
        return s or "-"


# ---------- PDF ----------
def build_invoice_pdf(company, project, invoice):
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=25*mm, rightMargin=8*mm, topMargin=12*mm, bottomMargin=10*mm)
    u = mm * (177 / 184)      # the 184 mm wide layout is scaled to the 177 mm left after the 25 mm punching margin
    GRID = colors.HexColor("#6b7280")
    BAND = colors.HexColor("#d3e5ee")
    BLUE = colors.HexColor("#2f5f8a")
    dash = (2, 2)
    base = getSampleStyleSheet()["BodyText"]
    cell = ParagraphStyle("cell", parent=base, fontName="Helvetica", fontSize=8, leading=10)
    bold = ParagraphStyle("bold", parent=cell, fontName="Helvetica-Bold")
    boldr = ParagraphStyle("boldr", parent=bold, alignment=TA_RIGHT)
    center = ParagraphStyle("center", parent=cell, alignment=TA_CENTER)
    centerb = ParagraphStyle("centerb", parent=center, fontName="Helvetica-Bold")
    right = ParagraphStyle("right", parent=cell, alignment=TA_RIGHT)
    blue = ParagraphStyle("blue", parent=cell, textColor=BLUE)
    W = 184 * u

    def P(text, style=cell):
        return Paragraph(str(text if text not in (None, "") else "-"), style)

    def grid(tbl, extra=()):
        tbl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, GRID), ("GRID", (0, 0), (-1, -1), 0.4, GRID, None, dash),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            *extra,
        ]))
        return tbl

    story = []

    # --- Letterhead: logo + firm name/address ---
    logo = Image(LOGO_FILE, width=24 * u, height=24 * u * 75 / 102) if os.path.exists(LOGO_FILE) else ""
    name_st = ParagraphStyle("firm", fontName="Times-Bold", fontSize=15, leading=18, alignment=TA_CENTER, textColor=colors.HexColor("#334155"))
    addr_st = ParagraphStyle("addr", fontName="Times-Roman", fontSize=8.2, leading=10.5, alignment=TA_CENTER, textColor=colors.HexColor("#475569"))
    gst_st = ParagraphStyle("gst", fontName="Times-Bold", fontSize=9.5, leading=12, alignment=TA_CENTER, textColor=BLUE)
    head = Table([[logo, [
        Paragraph(company['name'].replace("C.V. PATIL", "C.V.PATIL"), name_st),
        Paragraph(f"{company['address']}<br/>Email:- {company['email']}, Mobile : {company['mobile']}", addr_st),
        Paragraph(f"GSTIN: {company['gstin']}", gst_st),
    ]]], colWidths=[30 * u, 154 * u])
    grid(head, [("GRID", (0, 0), (-1, -1), 0, colors.white), ("LINEAFTER", (0, 0), (0, 0), 0.4, GRID, None, dash)])
    story.append(head)

    # --- Title band ---
    title = Table([[Paragraph(f"<b>{invoice['invoice_type'].upper()}</b>", ParagraphStyle("t", fontName="Times-Bold", fontSize=11.5, alignment=TA_CENTER, textColor=colors.HexColor("#334155")))]], colWidths=[W])
    grid(title, [("BACKGROUND", (0, 0), (-1, -1), BAND), ("GRID", (0, 0), (-1, -1), 0, colors.white)])
    story.append(title)

    # --- Invoice / P.O. block and Bill-to block (shared column grid) ---
    cols = [26 * u, 112 * u, 24 * u, 22 * u]
    info = Table([
        [P("Invoice No:", bold), P(invoice['invoice_no'], blue), P("Dated :", boldr), P(invoice['invoice_date'], right)],
        [P("P.O. No. :", bold), P(f"{project['po_no'] or '-'}&nbsp;&nbsp;&nbsp;Vendor ID : {project['vendor_id'] or '-'}"), P("Dated :", boldr), P(dmy(project['po_date']), right)],
        [P("State:", bold), P("Maharashtra"), P("Code :", boldr), P("27", right)],
    ], colWidths=cols)
    grid(info)
    story.append(info)

    bill = Table([
        [P("Bill to Party", bold), "", "", ""],
        [P("Name :", bold), P(project['client_name'], blue), "", ""],
        [P("Address:", bold), P(project['billing_address'], cell), "", ""],
        [P("GSTIN:", bold), P(project['gstin'], blue), P("Pan No. :", boldr), P(project['pan'], right)],
        [P("State:", bold), P((invoice.get('bill_state') or project['state'] or "").upper() or "-", cell),
         P("Code :", boldr), P(GST_STATES.get(invoice.get('bill_state') or "", project['state_code']), right)],
    ], colWidths=cols)
    grid(bill, [("SPAN", (0, 0), (-1, 0)), ("SPAN", (1, 1), (-1, 1)), ("SPAN", (1, 2), (-1, 2)),
                ("BACKGROUND", (0, 0), (-1, 0), BAND)])
    story.append(bill)

    site = Table([[P(f"Site Address : {project['site_address'] or '-'}")], [P(f"Kind Attention : {project['kind_attention'] or '-'}")]], colWidths=[W])
    grid(site, [("BACKGROUND", (0, 0), (-1, 0), BAND)])
    story.append(site)

    # --- Items and totals ---
    po_amt = float(project.get('po_amount') or 0)
    lines = invoice.get('items') or [{"sr": 1, "description": invoice['description'], "hsn": invoice['hsn_code'], "qty": invoice.get('qty_text', '1'), "amount": float(invoice['basic_amount'])}]
    rows = [[P("Sr.<br/>No", centerb), P("Product Description", centerb), P("HSN<br/>Code", centerb), P("Qty", centerb), P("Rate", centerb), P("Amount", centerb)]]
    rows.append(["", P("P.O. amount", bold), "", "", "", P(f"{po_amt:.0f}", boldr)])
    for ln in lines:
        billed = ln.get('billed', True) and float(ln.get('amount') or 0) > 0
        desc_html = ln['description']
        rows.append([P(ln['sr'], center), P(desc_html), P(ln['hsn'], center), P(ln['qty'], center),
                     P(indian(po_amt), center) if billed else "", P(indian(ln['amount']), right) if billed else ""])
    compact = len(lines) > 3                      # many lines: a smaller table so the invoice stays on one page
    pad = 7 if not compact else (3 if len(lines) <= 7 else 2)
    blanks = 2 if len(lines) <= 3 else (1 if len(lines) <= 7 else 0)
    rows += [["", "", "", "", "", ""] for _ in range(blanks)]

    cgst = float(invoice.get('cgst') or 0); sgst = float(invoice.get('sgst') or 0); igst = float(invoice.get('igst') or 0)
    rate = float(invoice.get('tax_rate') or 0)
    no_amount = float(invoice.get('basic_amount') or 0) <= 0

    def blank_or(text, style):
        return Paragraph("", style) if no_amount else P(text, style)
    if igst > 0 or invoice.get('tax_mode') == "IGST":
        r1, a1, r2, a2 = rate, igst, 0, 0.0
        lab1, lab2 = "IGST", "SGST"            # other states: IGST at the full rate
    elif invoice.get('tax_mode') == "CGST + SGST":
        r1, a1, r2, a2 = rate / 2, cgst, rate / 2, sgst
        lab1, lab2 = "CGST", "SGST"            # Maharashtra: 18% = CGST 9% + SGST 9%
    else:
        r1, a1, r2, a2 = 0, 0.0, 0, 0.0
        lab1, lab2 = "CGST / IGST", "SGST"
    pct = lambda r: f"{r:g}%"
    first_total = len(rows)
    rows += [
        ["", P("Total Amount before Tax", boldr), "", "", "", blank_or(indian(invoice['basic_amount']), right)],
        ["", P(lab1, boldr), "", "", P(pct(r1), center), blank_or(indian(a1), right)],
        ["", P(lab2, boldr), "", "", P(pct(r2), center), blank_or(indian(a2), right)],
        ["", P("Total taxable Amount", boldr), "", "", "", blank_or(indian(invoice['grand_total']), boldr)],
    ]
    heights = [9 * u if compact else 11 * u, 6 * u if compact else 7 * u] + [None] * len(lines) + [(6 if compact else 8) * u] * blanks + [(5.5 if compact else 7) * u] * 4
    items = Table(rows, colWidths=[11 * u, 91 * u, 20 * u, 14 * u, 23 * u, 25 * u], rowHeights=heights)
    grid(items, [("BACKGROUND", (0, 0), (-1, 0), BAND), ("TOPPADDING", (0, 2), (-1, 1 + len(lines)), pad), ("BOTTOMPADDING", (0, 2), (-1, 1 + len(lines)), pad)])
    story.append(items)

    # --- Bank details / terms (left) and signature block (right) ---
    bank_txt = company['bank_details'].replace("\n", "<br/>")
    bank = Table([
        [P("Bank Details", centerb), ""],
        [P(bank_txt, center), ""],
        [P("Terms &amp; conditions", centerb), ""],
        [P(company['terms'], center), ""],
        ["", P("Sign and stamp", bold)],
    ], colWidths=[136 * u, 48 * u], rowHeights=[6 * u, 14 * u, 6 * u, 17 * u, 10 * u] if compact else [7 * u, 17 * u, 7 * u, 24 * u, 11 * u])
    grid(bank, [("SPAN", (1, 0), (1, 3)), ("SPAN", (0, 4), (0, 4)), ("BACKGROUND", (0, 0), (0, 0), BAND), ("BACKGROUND", (0, 2), (0, 2), BAND),
                ("VALIGN", (1, 4), (1, 4), "BOTTOM"), ("ALIGN", (1, 4), (1, 4), "RIGHT"), ("VALIGN", (1, 0), (1, 0), "TOP")])
    story.append(bank)
    doc.build(story, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
    out.seek(0)
    return out.getvalue()


# ---------- UI ----------
company = fetch_company()

# Top bar: logo + firm name on the left, navigation links and contact button on the right.
_logo_html = ""
if os.path.exists(LOGO_FILE):
    with open(LOGO_FILE, "rb") as _f:
        _logo_html = f"<img src='data:image/png;base64,{base64.b64encode(_f.read()).decode()}'/>"
# The financial year setting now lives in the top bar (the sidebar was removed).
fy_options = fetch_financial_years()
if st.session_state.get("fy_value") not in fy_options:
    st.session_state["fy_value"] = fy_label(date.today())


def _fy_from_topbar():
    label = add_custom_year(st.session_state["selected_fy"])
    if label:
        st.session_state["fy_value"] = label


st.session_state["selected_fy"] = st.session_state["fy_value"]
_companies = fetch_companies()
_company_ids = [x["id"] for x in _companies]
if st.session_state.get("active_company") not in _company_ids:
    st.session_state["active_company"] = _company_ids[0]
tb_brand, tb_fy = st.columns([4, 1.2], vertical_alignment="center")
tb_brand.markdown(f"<div class='topbar-brand'>{_logo_html}<span>{SITE_NAME}</span></div>", unsafe_allow_html=True)
selected_fy = tb_fy.selectbox("Financial Year", fy_options, key="selected_fy", on_change=_fy_from_topbar, accept_new_options=True)
if selected_fy not in fy_options:
    selected_fy = st.session_state["fy_value"]
NAV_PAGES = ["Dashboard", "Company Setup", "Create Invoice", "Report"]
page = st.segmented_control("Navigation", NAV_PAGES, default="Dashboard", label_visibility="collapsed", key="nav_page", width="stretch")
page = page or "Dashboard"
st.markdown("<hr style='margin:.4rem 0 1rem'>", unsafe_allow_html=True)

projects = fetch_projects(selected_fy)

# Keep the Clients & Projects form values when moving between pages.
for _k in [k for k in st.session_state if k.startswith("pf_")]:
    st.session_state[_k] = st.session_state[_k]

def render_milestone_section(p):

    def to_date(v):
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return None
        if isinstance(v, str):
            try:
                return date.fromisoformat(v[:10])
            except Exception:
                return None
        return v.date() if hasattr(v, "date") else v

    def num(v, default=0.0):
        try:
            return default if pd.isna(v) else float(v)
        except Exception:
            return default

    def calc(basic, rate, adv, rec, due, gst=None, sched=None, balance=None):
        gst = basic * rate / 100 if gst is None else gst
        sched = basic + gst if sched is None else sched
        paid = adv + rec
        balance = max(sched - paid, 0.0) if balance is None else balance
        if sched > 0 and balance <= 0.005:
            status = "Collected"
        elif paid > 0 or balance < sched - 0.005:
            status = "Partially Collected"
        elif due and due < date.today():
            status = "Overdue"
        else:
            status = "Pending"
        return gst, sched, balance, status

    pay_modes = ["Bank Transfer / Online", "Cheque", "Cash", "Other"]
    sync_milestone_completion()
    all_ms = fetch_milestones(p['id'])
    existing = list(all_ms)      # all milestones are shown; completed ones are marked Completed
    old_no = {m["id"]: m["milestone_no"] for m in existing}
    used_max = max([m["milestone_no"] or 0 for m in all_ms] or [0])
    ver_key = f"ms_ver_{p['id']}"
    ver = st.session_state.setdefault(ver_key, 0)
    rows = []
    orig = {}
    for i, m in enumerate(existing):
        basic = num(m.get("amount")); rate = num(m.get("gst_rate"), 0.0)
        adv = num(m.get("advance_received")); rec = num(m.get("actual_amount"))
        due = to_date(m.get("due_date"))
        stored = lambda k: None if m.get(k) is None else float(m[k])
        gst, sched, balance, status = calc(basic, rate, adv, rec, due, stored("gst_amount"), stored("scheduled_amount"), stored("balance_amount"))
        if m.get("payment_status") == "Partially Collected" and status == "Pending":
            status = "Partially Collected"
        t_rate = float(m["tds_rate"]) if m.get("tds_rate") is not None else 10.0
        t_amt = float(m["tds_amount"] or 0) if m.get("tds_rate") is not None else round(basic * t_rate / 100, 2)
        orig[m["id"]] = {"basic": basic, "rate": rate, "gst": gst, "sched": sched, "paid": adv + rec, "balance": balance,
                         "tds_rate": t_rate, "tds": t_amt}
        rows.append({
            "id": m["id"], "Sr. No.": m.get("milestone_no") or i + 1, "Milestone Due Date": due,
            "Milestone / Scope of Work": m.get("description") or "",
            "Basic Amount (₹)": basic, "GST Rate (%)": None if m.get("gst_rate") is None else rate, "GST Amount (₹)": gst, "Scheduled Amount (₹)": sched,
            "Advance Received (₹)": adv, "Actual Payment Date": to_date(m.get("actual_payment_date")),
            "Actual Amount Received (₹)": rec,
            "Balance Before TDS (₹)": balance, "TDS Rate (%)": t_rate, "TDS Deducted (₹)": t_amt, "Collection Status": "Completed" if m.get("completed_on") else status,
        })
    def resolve(r):
        """GST / Scheduled amount: a value the user typed wins; otherwise keep the stored value if basic and
        rate are unchanged; otherwise recalculate from basic and GST rate."""
        basic = num(r["Basic Amount (₹)"]); rate = num(r["GST Rate (%)"], 0.0)
        rid = r["id"]
        o = orig.get(int(rid)) if rid is not None and not pd.isna(rid) else None
        g_in = num(r["GST Amount (₹)"], None); s_in = num(r["Scheduled Amount (₹)"], None)
        if g_in is not None and (o is None or abs(g_in - o["gst"]) > 0.005):
            gst = g_in
        elif o and abs(basic - o["basic"]) < 0.005 and abs(rate - o["rate"]) < 0.005:
            gst = o["gst"]
        else:
            gst = basic * rate / 100
        if s_in is not None and (o is None or abs(s_in - o["sched"]) > 0.005):
            sched = s_in
        elif o and abs(basic - o["basic"]) < 0.005 and abs(gst - o["gst"]) < 0.005:
            sched = o["sched"]
        else:
            sched = basic + gst
        paid = num(r["Advance Received (₹)"]) + num(r["Actual Amount Received (₹)"])
        b_in = num(r["Balance Before TDS (₹)"], None)
        if b_in is not None and (o is None or abs(b_in - o["balance"]) > 0.005):
            balance = b_in
        elif o and abs(sched - o["sched"]) < 0.005 and abs(paid - o["paid"]) < 0.005:
            balance = o["balance"]
        else:
            balance = max(sched - paid, 0.0)
        return gst, sched, balance

    def resolve_tds(r):
        """TDS is auto-generated as basic amount x TDS rate; a value typed in the cell wins."""
        basic = num(r["Basic Amount (₹)"]); trate = num(r["TDS Rate (%)"], 10.0)
        rid = r["id"]
        o = orig.get(int(rid)) if rid is not None and not pd.isna(rid) else None
        t_in = num(r["TDS Deducted (₹)"], None)
        if t_in is not None and (o is None or abs(t_in - o["tds"]) > 0.005):
            return t_in, trate
        if o and abs(basic - o["basic"]) < 0.005 and abs(trate - o["tds_rate"]) < 0.005:
            return o["tds"], trate
        return round(basic * trate / 100, 2), trate

    columns = ["id", "Sr. No.", "Milestone Due Date", "Milestone / Scope of Work", "Basic Amount (₹)", "GST Rate (%)",
               "GST Amount (₹)", "Scheduled Amount (₹)", "Advance Received (₹)", "Actual Payment Date",
               "Actual Amount Received (₹)", "Balance Before TDS (₹)", "TDS Rate (%)", "TDS Deducted (₹)", "Collection Status"]
    df = pd.DataFrame(rows, columns=columns)

    if st.button("➕ Create Milestone", type="primary", key=f"create_ms_{p['id']}"):
        # a new empty milestone row is added; fill it in the table below and click Save Milestones
        _n = used_max + 1
        _cc = conn()
        _cc.execute("""INSERT INTO milestones(project_id,milestone_no,description,percentage,amount,payment_status,invoice_type,tax_invoice_no,hsn_code,gst_mode,gst_rate,payment_mode,
                       advance_received,actual_amount,gst_amount,scheduled_amount,balance_amount)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (p['id'], _n, f"Milestone {_n}", 0.0, 0.0, "Pending", "Tax Invoice", "", "998337", gst_mode_for_state(p.get('state')), None, "Bank Transfer / Online",
                     0.0, 0.0, 0.0, 0.0, 0.0))
        _cc.commit(); _cc.close()
        st.session_state[ver_key] = ver + 1
        st.rerun()
    money = lambda title, w=95, **kw: st.column_config.NumberColumn(title, min_value=0.0, step=1000.0, format="%.0f", width=w, **kw)
    edited = st.data_editor(
        df, hide_index=True, use_container_width=True, num_rows="dynamic", key=f"milestone_table_{p['id']}_{ver}", row_height=30,
        column_config={
            "id": None,
            "Sr. No.": st.column_config.NumberColumn("No.", disabled=True, format="%d", width=50),
            "Milestone Due Date": st.column_config.DateColumn("Due Date", format="DD/MM/YY", width=100),
            "Milestone / Scope of Work": st.column_config.TextColumn("Milestone", width=260),
            "Basic Amount (₹)": money("Basic ₹"),
            "GST Rate (%)": st.column_config.NumberColumn("GST %", min_value=0.0, max_value=50.0, step=1.0, format="%.0f", width=75),
            "GST Amount (₹)": money("GST ₹"),
            "Scheduled Amount (₹)": money("Scheduled ₹", 110),
            "Advance Received (₹)": money("Advance ₹"),
            "Actual Payment Date": st.column_config.DateColumn("Paid On", format="DD/MM/YY", width=100),
            "Actual Amount Received (₹)": money("Received ₹", 105),
            "Balance Before TDS (₹)": money("Balance ₹", 105),
            "TDS Rate (%)": st.column_config.NumberColumn("TDS %", min_value=0.0, max_value=50.0, step=0.5, format="%.1f", width=75),
            "TDS Deducted (₹)": money("TDS ₹"),
            "Collection Status": st.column_config.TextColumn("Status", disabled=True, width=115),
        },
    )

    # Live totals from whatever is currently typed in the table.
    live = [r for _, r in edited.iterrows() if str(r["Milestone / Scope of Work"] or "").strip() or num(r["Basic Amount (₹)"])]
    t_basic = sum(num(r["Basic Amount (₹)"]) for r in live)
    t_gst = sum(resolve(r)[0] for r in live)
    t_sched = sum(resolve(r)[1] for r in live)
    t_bal = sum(resolve(r)[2] for r in live)
    t_paid = sum(num(r["Advance Received (₹)"]) + num(r["Actual Amount Received (₹)"]) for r in live)
    t_tds = sum(resolve_tds(r)[0] for r in live)
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m6.metric("Total TDS", inr(t_tds))
    m1.metric("Total Basic", inr(t_basic)); m2.metric("Total GST", inr(t_gst))
    m3.metric("Total Scheduled", inr(t_sched)); m4.metric("Total Received", inr(t_paid))
    m5.metric("Balance Before TDS", inr(t_bal))
    if p["po_amount"] and t_basic > float(p["po_amount"]) + 0.005:
        st.warning(f"Total basic amount exceeds the P.O. amount ({inr(p['po_amount'])}).")

    if st.button("Save Milestones", type="primary"):
        entries = []
        for _, r in edited.iterrows():
            scope = str(r["Milestone / Scope of Work"] or "").strip()
            if not scope and not num(r["Basic Amount (₹)"]):
                continue
            entries.append(r)
        if any(not str(r["Milestone / Scope of Work"] or "").strip() for r in entries):
            st.error("Enter the Milestone / Scope of Work for every row.")
        else:
            c = conn()
            with c:
                c.execute("BEGIN IMMEDIATE")
                kept = set()
                for r in entries:
                    _rid = r["id"]
                    if _rid is not None and not pd.isna(_rid) and int(_rid) in old_no:
                        n = old_no[int(_rid)]
                    else:
                        used_max += 1
                        n = used_max
                    basic = num(r["Basic Amount (₹)"]); rate = num(r["GST Rate (%)"], None)    # empty GST % stays empty
                    adv = num(r["Advance Received (₹)"]); rec = num(r["Actual Amount Received (₹)"])
                    due = to_date(r["Milestone Due Date"]); paid_on = to_date(r["Actual Payment Date"])
                    gst, sched, balance = resolve(r)
                    status = calc(basic, rate or 0.0, adv, rec, due, gst, sched, balance)[3]
                    mode = pay_modes[0]
                    vals = (n, str(r["Milestone / Scope of Work"]).strip(), basic / float(p["po_amount"]) * 100 if p["po_amount"] else 0.0,
                            basic, due.isoformat() if due else None, rate, adv, paid_on.isoformat() if paid_on else None,
                            rec, mode, status, gst, sched, balance, *resolve_tds(r))
                    rid = r["id"]
                    if rid is not None and not pd.isna(rid):
                        kept.add(int(rid))
                        c.execute("""UPDATE milestones SET milestone_no=?,description=?,percentage=?,amount=?,due_date=?,gst_rate=?,advance_received=?,actual_payment_date=?,actual_amount=?,payment_mode=?,payment_status=?,gst_amount=?,scheduled_amount=?,balance_amount=?,tds_amount=?,tds_rate=? WHERE id=? AND project_id=?""", vals + (int(rid), p['id']))
                    else:
                        c.execute("""INSERT INTO milestones(milestone_no,description,percentage,amount,due_date,gst_rate,advance_received,actual_payment_date,actual_amount,payment_mode,payment_status,gst_amount,scheduled_amount,balance_amount,tds_amount,tds_rate,project_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals + (p['id'],))
                for m in existing:
                    if m["id"] not in kept:
                        c.execute("DELETE FROM milestones WHERE id=? AND project_id=?", (m["id"], p['id']))
            c.close()
            st.session_state[ver_key] = ver + 1
            st.rerun()

    done = [m for m in all_ms if m.get("completed_on")]
    todo = [m for m in all_ms if not m.get("completed_on")]
    # invoice that bills each milestone (if any)
    _c = conn()
    _inv_rows = [dict(r) for r in _c.execute("SELECT invoice_no, description, items_json FROM invoices WHERE project_id=? AND invoice_type='Tax Invoice' ORDER BY id", (p['id'],)).fetchall()]
    _c.close()
    billed_on = {}
    for r in _inv_rows:
        try:
            its = json.loads(r["items_json"]) if r["items_json"] else [{"description": r["description"], "billed": True, "amount": 1}]
        except Exception:
            its = []
        for i in its:
            if i.get("billed", True) and float(i.get("amount") or 0) > 0:
                billed_on.setdefault(i.get("description") or "", r["invoice_no"])
    rows = []
    for m in done:
        rows.append({"Sr. No.": m["milestone_no"], "Milestone / Scope of Work": m.get("description") or "", "Basic (₹)": float(m.get("amount") or 0),
                     "Invoice No.": m.get("completed_invoice") or "", "Paid On": dmy(m["completed_on"]),
                     "Amount Received (₹)": float(m.get("completed_amount") or 0), "Status": "🟢 Completed"})
    for m in todo:
        due = None
        try:
            due = date.fromisoformat(m["due_date"]) if m.get("due_date") else None
        except Exception:
            due = None
        if m.get("payment_status") == "Partially Collected":
            status = "🟡 Partially paid"
        elif due and due < date.today():
            status = "🔴 Not completed (overdue)"
        else:
            status = "⚪ Not completed"
        rows.append({"Sr. No.": m["milestone_no"], "Milestone / Scope of Work": m.get("description") or "", "Basic (₹)": float(m.get("amount") or 0),
                     "Invoice No.": billed_on.get(m.get("description") or "", ""), "Paid On": dmy(m["actual_payment_date"]) if m.get("actual_payment_date") else "",
                     "Amount Received (₹)": float(m.get("actual_amount") or 0), "Status": status})
    rows.sort(key=lambda r: r["Sr. No."])


def render_payment_tracking(p):
    st.markdown("### Payments Received")
    c = conn()
    rows = [dict(r) for r in c.execute("SELECT * FROM invoices WHERE project_id=? AND invoice_type='Tax Invoice' ORDER BY id", (p['id'],)).fetchall()]
    c.close()
    rows.sort(key=invoice_serial)
    flash = st.session_state.pop("_pay_flash", None)
    if flash:
        st.success(flash)
    if not rows:
        st.caption("No tax invoice saved for this project yet. Payments can be entered here once an invoice is saved.")
        return
    ver_key = f"pay_ver_{p['id']}"
    ver = st.session_state.setdefault(ver_key, 0)
    profile = client_payment_profile(p['client_name'])
    table = []
    for r in rows:
        pay = invoice_payment(r)
        expected, outlook = payment_outlook(r, pay, profile)
        try:
            paid_on = date.fromisoformat(r['paid_date']) if r.get('paid_date') else None
        except Exception:
            paid_on = None
        table.append({
            "id": r['id'], "Invoice No.": r['invoice_no'], "Invoice Date": date.fromisoformat(r['invoice_date'][:10]),
            "Basic (₹)": float(r['basic_amount'] or 0), "Total (₹)": float(r['grand_total'] or 0), "TDS Rate (%)": pay["rate"],
            "TDS (₹)": pay["tds"], "Amount Received (₹)": pay["paid"], "Payment Date": paid_on,
            "Balance to Collect (₹)": pay["balance"], "Status": STATUS_LABEL[pay["status"]],
            "Expected Payment": expected, "Payment Outlook": outlook,
        })
    df = pd.DataFrame(table)
    edited = st.data_editor(
        df, hide_index=True, use_container_width=True, num_rows="fixed", key=f"pay_table_{p['id']}_{ver}",
        column_config={
            "id": None,
            "Invoice No.": st.column_config.TextColumn("Invoice No.", disabled=True),
            "Invoice Date": st.column_config.DateColumn("Invoice Date", format="DD/MM/YYYY", disabled=True),
            "Basic (₹)": st.column_config.NumberColumn("Basic (₹)", disabled=True, format="%.2f"),
            "Total (₹)": st.column_config.NumberColumn("Total (₹)", disabled=True, format="%.2f"),
            "TDS Rate (%)": st.column_config.NumberColumn("TDS Rate (%)", min_value=0.0, max_value=50.0, step=0.5, format="%.1f"),
            "TDS (₹)": st.column_config.NumberColumn("TDS (₹)", disabled=True, format="%.2f"),
            "Amount Received (₹)": st.column_config.NumberColumn("Amount Received (₹)", min_value=0.0, step=1000.0, format="%.2f"),
            "Payment Date": st.column_config.DateColumn("Payment Date", format="DD/MM/YYYY"),
            "Balance to Collect (₹)": st.column_config.NumberColumn("Balance to Collect (₹)", disabled=True, format="%.2f"),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Expected Payment": st.column_config.DateColumn("Expected Payment", format="DD/MM/YYYY", disabled=True),
            "Payment Outlook": st.column_config.TextColumn("Payment Outlook", disabled=True, width="medium"),
        },
    )
    # Live position from whatever is typed in the table (the saved values refresh after Save Payments).
    live = []
    for _, r in edited.iterrows():
        src = next(x for x in rows if x['id'] == r['id'])
        row = dict(src)
        row['tds_rate'] = float(r["TDS Rate (%)"]) if not pd.isna(r["TDS Rate (%)"]) else 10.0
        row['paid_amount'] = float(r["Amount Received (₹)"]) if not pd.isna(r["Amount Received (₹)"]) else 0.0
        live.append((row, invoice_payment(row)))
    total_inv = sum(float(x[0]['grand_total'] or 0) for x in live)
    total_tds = sum(x[1]["tds"] for x in live)
    total_paid = sum(x[1]["paid"] for x in live)
    total_bal = sum(x[1]["balance"] for x in live)
    n_paid = sum(1 for x in live if x[1]["status"] == "Paid")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Invoiced", inr(total_inv)); m2.metric("TDS", inr(total_tds))
    m3.metric("Received", inr(total_paid)); m4.metric("Balance to Collect", inr(total_bal))
    st.markdown(f"**{n_paid} of {len(live)} invoice(s) fully paid** · {inr(total_bal)} still to collect")

    if st.button("Save Payments", type="primary", key=f"pay_save_{p['id']}"):
        cu = conn()
        for row, pay in live:
            r = edited[edited["id"] == row['id']].iloc[0]
            paid_on = r["Payment Date"]
            if pay["paid"] > 0 and (paid_on is None or pd.isna(paid_on)):
                paid_on = date.today()
            paid_on = None if paid_on is None or pd.isna(paid_on) else (paid_on.date() if hasattr(paid_on, "date") else paid_on)
            cu.execute("UPDATE invoices SET paid_amount=?, paid_date=?, tds_rate=? WHERE id=?",
                       (pay["paid"], paid_on.isoformat() if paid_on else None, pay["rate"], row['id']))
        cu.commit(); cu.close()
        sync_milestone_completion()
        st.session_state[ver_key] = ver + 1
        st.session_state["_pay_flash"] = "Payments saved. Balances and status are updated everywhere."
        st.rerun()


def auto_check_statement_folder():
    """Looks in the bank_statements folder for new CSV / Excel statements, applies the payments that match an invoice
    with confidence (invoice number in the narration, or the exact balance from the right client) and moves each file
    to bank_statements/processed. Anything unsure is left alone. Returns a short report."""
    os.makedirs(os.path.join(STATEMENT_DIR, "processed"), exist_ok=True)
    files = [f for f in sorted(os.listdir(STATEMENT_DIR)) if f.lower().endswith((".csv", ".xlsx")) and os.path.isfile(os.path.join(STATEMENT_DIR, f))]
    if not files:
        return None
    c = conn()
    projs = {r["id"]: dict(r) for r in c.execute("SELECT * FROM projects").fetchall()}
    done = {r[0] for r in c.execute("SELECT hash FROM bank_credits").fetchall()}
    c.close()
    report = []
    for fname in files:
        path = os.path.join(STATEMENT_DIR, fname)
        try:
            with open(path, "rb") as fh:
                data = io.BytesIO(fh.read())
            data.name = fname
            df = read_bank_statement(data)
        except Exception as e:
            report.append(f"{fname}: could not be read ({e})")
            continue
        cols = [str(x) for x in df.columns]
        low = [x.lower() for x in cols]
        def find(keys):
            for k in keys:
                for i, x in enumerate(low):
                    if k in x:
                        return df.columns[i]
            return None
        dc, nc, cc = find(["txn date", "value date", "date"]), find(["narration", "description", "particulars", "remarks", "details"]), find(["credit", "deposit", "cr"])
        if dc is None or nc is None or cc is None:
            report.append(f"{fname}: skipped (could not find date, description and credit columns)")
            continue
        credits = []
        for _, r in df.iterrows():
            amt = to_amount(r[cc])
            if amt > 0:
                dt = pd.to_datetime(r[dc], dayfirst=True, errors="coerce")
                credits.append({"date": None if pd.isna(dt) else dt.date(), "desc": str(r[nc]), "amount": amt})
        # open invoices (re-read after each file so earlier payments count)
        c = conn()
        invs = [dict(r) for r in c.execute("SELECT * FROM invoices WHERE invoice_type='Tax Invoice'").fetchall()]
        c.close()
        open_invs = []
        for r in invs:
            pay = invoice_payment(r)
            if r["project_id"] in projs and pay["balance"] > 0.5:
                open_invs.append({"row": r, "pay": pay, "client": projs[r["project_id"]]["client_name"]})
        applied = unsure = already = 0
        touched = set()
        cu = conn()
        running = {}
        for m in match_bank_credits(credits, open_invs):
            h = hashlib.md5(f"{m['date']}|{m['desc']}|{m['amount']}".encode()).hexdigest()
            if h in done:
                already += 1
                continue
            confident = m["invoice_no"] and (m["score"] >= 100 or m["score"] >= 70)
            inv = next((x for x in open_invs if x["row"]["invoice_no"] == m["invoice_no"]), None)
            if not (confident and inv):
                unsure += 1
                continue
            amt, left = apply_credit_to_invoice(cu, running, inv, m["amount"], m["date"], m.get("milestone"))
            if amt <= 0:
                unsure += 1
                continue
            cu.execute("INSERT OR IGNORE INTO bank_credits(hash, invoice_no, amount, applied_on) VALUES(?,?,?,?)", (h, m["invoice_no"], amt, date.today().isoformat()))
            done.add(h); applied += 1; touched.add(inv["row"]["project_id"])
        cu.commit(); cu.close()
        sync_milestone_completion()
        shutil.move(path, os.path.join(STATEMENT_DIR, "processed", fname))
        report.append(f"{fname}: {applied} payment(s) applied automatically" + (f", {unsure} left for you to check" if unsure else "") + (f", {already} already applied" if already else ""))
        for pid_ in sorted(touched):
            report.append(f"{projs[pid_]['project_name']} — " + milestone_status_lines(pid_))
    return report


def render_bank_check():
    st.markdown(
        """<div class='bank-banner'><div class='bank-icon'>
        <svg width='28' height='28' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>
        <path d='M3 9.5 12 4l9 5.5'/><path d='M4.5 9.5h15'/><path d='M6 12v6M10 12v6M14 12v6M18 12v6'/><path d='M3.5 20h17'/></svg></div>
        <div><div class='bank-title'>Bank Payment Check</div><div class='bank-sub'>Upload your bank statement and client payments are matched to invoices and milestones</div></div></div>""",
        unsafe_allow_html=True)
    _auto = auto_check_statement_folder()
    if _auto:
        st.success("Bank statement folder checked automatically:  \n" + "  \n".join(_auto))
    st.caption(f"Save your downloaded bank statement (CSV or Excel) in the folder  {STATEMENT_DIR}  and open this page. Payments that clearly match an invoice are applied automatically.")
    c = conn()
    projs = {r["id"]: dict(r) for r in c.execute("SELECT * FROM projects").fetchall()}
    invs = [dict(r) for r in c.execute("SELECT * FROM invoices WHERE invoice_type='Tax Invoice'").fetchall()]
    done = {r[0] for r in c.execute("SELECT hash FROM bank_credits").fetchall()}
    c.close()
    open_invs = []
    for r in invs:
        pay = invoice_payment(r)
        if r["project_id"] in projs and pay["balance"] > 0.5:
            open_invs.append({"row": r, "pay": pay, "client": projs[r["project_id"]]["client_name"]})
    flash = st.session_state.pop("_bank_flash", None)
    if flash:
        st.success(flash)
    up = st.file_uploader("Upload your bank account statement (CSV or Excel) to check for client payments", type=["csv", "xlsx"], key="bank_upload")
    if not up:
        return
    try:
        df = read_bank_statement(up)
    except Exception as e:
        st.error(f"Could not read the statement: {e}")
        return
    cols = list(df.columns)
    g1, g2, g3 = st.columns(3)
    date_col = g1.selectbox("Date column", cols, index=cols.index(guess_column(cols, ["txn date", "value date", "date"])))
    desc_col = g2.selectbox("Description column", cols, index=cols.index(guess_column(cols, ["narration", "description", "particulars", "remarks", "details"])))
    cr_col = g3.selectbox("Credit / Deposit column", cols, index=cols.index(guess_column(cols, ["credit", "deposit", "cr"])))
    credits = []
    for _, r in df.iterrows():
        amt = to_amount(r[cr_col])
        if amt <= 0:
            continue
        dt = pd.to_datetime(r[date_col], dayfirst=True, errors="coerce")
        credits.append({"date": None if pd.isna(dt) else dt.date(), "desc": str(r[desc_col]), "amount": amt})
    if not credits:
        st.info("No credit (money received) entries found in this statement.")
        return
    matched = match_bank_credits(credits, open_invs)
    open_numbers = [x["row"]["invoice_no"] for x in open_invs]
    table = []
    for m in matched:
        h = hashlib.md5(f"{m['date']}|{m['desc']}|{m['amount']}".encode()).hexdigest()
        already = h in done
        table.append({"Apply": bool(m["invoice_no"]) and not already, "Date": m["date"], "Description": m["desc"], "Credit (₹)": m["amount"],
                      "Invoice": m["invoice_no"], "Milestone": m.get("milestone"), "Amount to Apply (₹)": m["apply"],
                      "Result": "Already applied" if already else ("No matching invoice" if not m["invoice_no"] else
                                (f"Milestone {m['milestone']} paid" if m.get("milestone") and m["apply"] >= m["amount"] - 0.5 else
                                 ("Paid in full" if m["apply"] >= next(x for x in open_invs if x["row"]["invoice_no"] == m["invoice_no"])["pay"]["balance"] - 0.5 else "Part payment"))),
                      "_hash": h, "_already": already})
    tdf = pd.DataFrame(table)
    show = tdf.drop(columns=["_hash", "_already"])
    edited = st.data_editor(
        show, hide_index=True, use_container_width=True, num_rows="fixed", key="bank_table",
        column_config={
            "Apply": st.column_config.CheckboxColumn("Apply", width="small"),
            "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY", disabled=True),
            "Description": st.column_config.TextColumn("Description", disabled=True, width="large"),
            "Credit (₹)": st.column_config.NumberColumn("Credit (₹)", disabled=True, format="%.2f"),
            "Invoice": st.column_config.SelectboxColumn("Matched Invoice", options=open_numbers),
            "Milestone": st.column_config.NumberColumn("Milestone", disabled=True, format="%d", width="small"),
            "Amount to Apply (₹)": st.column_config.NumberColumn("Amount to Apply (₹)", min_value=0.0, step=100.0, format="%.2f"),
            "Result": st.column_config.TextColumn("Result", disabled=True),
        },
    )
    by_no = {x["row"]["invoice_no"]: x for x in open_invs}
    n_full = n_part = 0
    for i, r in edited.iterrows():
        inv = by_no.get(r["Invoice"])
        if r["Apply"] and inv and not tdf.loc[i, "_already"] and r["Amount to Apply (₹)"] > 0:
            if float(r["Amount to Apply (₹)"]) >= inv["pay"]["balance"] - 0.5:
                n_full += 1
            else:
                n_part += 1
    st.markdown(f"**{len(matched)} payment(s) found in the statement** · {n_full} will be marked **Paid**, {n_part} as **Partially Paid**")
    if st.button("Apply Selected Payments", type="primary", key="bank_apply"):
        cu = conn(); applied = full = part = 0
        running = {}   # paid amount per invoice while several credits hit the same invoice
        touched = set()
        for i, r in edited.iterrows():
            inv = by_no.get(r["Invoice"])
            if not (r["Apply"] and inv) or tdf.loc[i, "_already"] or r["Amount to Apply (₹)"] <= 0:
                continue
            ms_no = None if pd.isna(r["Milestone"]) else int(r["Milestone"])
            pay_date = None if (r["Date"] is None or pd.isna(r["Date"])) else r["Date"]
            amt, left = apply_credit_to_invoice(cu, running, inv, float(r["Amount to Apply (₹)"]), pay_date, ms_no)
            if amt <= 0:
                continue
            cu.execute("INSERT OR IGNORE INTO bank_credits(hash, invoice_no, amount, applied_on) VALUES(?,?,?,?)", (tdf.loc[i, "_hash"], r["Invoice"], amt, date.today().isoformat()))
            applied += 1; touched.add(inv["row"]["project_id"])
            if left <= 0.5:
                full += 1
            else:
                part += 1
        cu.commit(); cu.close()
        sync_milestone_completion()
        for k in [k for k in st.session_state if k.startswith("pay_ver_")]:
            st.session_state[k] += 1
        st.session_state["_bank_flash"] = (f"{applied} payment(s) applied: {full} invoice(s) now Paid (their milestones moved to the history), {part} Partially Paid.  \n"
                                           + "  \n".join(milestone_status_lines(pid_) for pid_ in sorted(touched)))
        st.rerun()


def render_received_balance():
    """Received and balance amounts for the selected financial year: totals, per project and per invoice."""
    st.markdown(f"### Received & Balance — FY {selected_fy}")
    pmap = {p['id']: p for p in projects}
    c = conn()
    invs = [dict(r) for r in c.execute("SELECT * FROM invoices WHERE invoice_type='Tax Invoice'").fetchall() if r['project_id'] in pmap]
    c.close()
    if not invs:
        st.info(f"No tax invoices in Financial Year {selected_fy} yet. Received and balance amounts appear here once invoices are saved.")
        return
    invs.sort(key=lambda r: (r['invoice_date'], invoice_serial(r)))
    rows = []
    for r in invs:
        pay = invoice_payment(r)
        rows.append({"r": r, "pay": pay, "project": pmap[r['project_id']]})
    inv_total = sum(float(x["r"]['grand_total'] or 0) for x in rows)
    tds_total = sum(x["pay"]["tds"] for x in rows)
    recv_total = sum(x["pay"]["paid"] for x in rows)
    bal_total = sum(x["pay"]["balance"] for x in rows)
    counts = {s: sum(1 for x in rows if x["pay"]["status"] == s) for s in ("Paid", "Partially Paid", "Overdue", "Pending")}

    def short(v):
        v = float(v or 0)
        if abs(v) >= 1e7:
            return f"₹ {v/1e7:.2f} Cr"
        if abs(v) >= 1e5:
            return f"₹ {v/1e5:.2f} L"
        return f"₹ {v:,.0f}"

    cards = [
        ("Total Invoiced", short(inv_total), f"{len(rows)} tax invoice(s)", "#3b5bdb"),
        ("TDS Deducted", short(tds_total), "to be claimed", "#7048e8"),
        ("Amount Received", short(recv_total), f"{counts['Paid']} paid · {counts['Partially Paid']} partly paid", "#2f9e44"),
        ("Balance to Collect", short(bal_total), f"{counts['Overdue']} overdue · {counts['Pending']} pending", "#e8590c"),
    ]
    st.markdown("<div class='kpi-row'>" + "".join(
        f"<div class='kpi' style='--accent:{col}'><div class='kpi-label'>{lab}</div><div class='kpi-value'>{val}</div><div class='kpi-note'>{note}</div></div>"
        for lab, val, note, col in cards) + "</div>", unsafe_allow_html=True)
    pct = (recv_total / (inv_total - tds_total) * 100) if (inv_total - tds_total) > 0 else 0
    st.markdown(f"<div class='prog'><div class='prog-top'><span class='prog-name'>Collected so far</span>"
                f"<span class='prog-val'>{pct:.0f}% of the amount receivable (invoiced − TDS)</span></div>"
                f"<div class='prog-bar'><div class='prog-fill' style='width:{min(pct, 100):.1f}%'></div></div></div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-title'>By project</div>", unsafe_allow_html=True)
    by_project = {}
    for x in rows:
        d = by_project.setdefault(x["project"]['id'], {"Project": x["project"]['project_name'], "Client": x["project"]['client_name'],
                                                       "Invoices": 0, "Invoiced (₹)": 0.0, "TDS (₹)": 0.0, "Received (₹)": 0.0, "Balance (₹)": 0.0, "Paid": 0})
        d["Invoices"] += 1; d["Invoiced (₹)"] += float(x["r"]['grand_total'] or 0); d["TDS (₹)"] += x["pay"]["tds"]
        d["Received (₹)"] += x["pay"]["paid"]; d["Balance (₹)"] += x["pay"]["balance"]; d["Paid"] += 1 if x["pay"]["status"] == "Paid" else 0
    pdf_ = pd.DataFrame(list(by_project.values()))
    pdf_["Status"] = [("🟢 All paid" if r["Balance (₹)"] <= 0.5 else ("🟡 Part paid" if r["Received (₹)"] > 0 else "🔴 Unpaid")) for _, r in pdf_.iterrows()]
    st.dataframe(pdf_, use_container_width=True, hide_index=True, column_config={
        col: st.column_config.NumberColumn(col, format="%.2f") for col in pdf_.columns if col.endswith("(₹)")})

    st.markdown("<div class='panel-title'>Invoice-wise</div>", unsafe_allow_html=True)
    idf = pd.DataFrame([{
        "Invoice No.": x["r"]['invoice_no'], "Date": dmy(x["r"]['invoice_date']), "Project": x["project"]['project_name'],
        "Total (₹)": float(x["r"]['grand_total'] or 0), "TDS (₹)": x["pay"]["tds"], "Received (₹)": x["pay"]["paid"],
        "Balance (₹)": x["pay"]["balance"], "Status": STATUS_LABEL[x["pay"]["status"]],
    } for x in rows])
    st.dataframe(idf, use_container_width=True, hide_index=True, column_config={
        col: st.column_config.NumberColumn(col, format="%.2f") for col in idf.columns if col.endswith("(₹)")})


def render_invoice_reports(p, only_type=None, pdf_only=False):
    """Download options of the project's saved invoices. With only_type, just that invoice type is shown (no tabs)."""
    if not pdf_only:
        st.markdown("### Invoice Report — current project")
    _cr = conn()
    _p_rows = [dict(r) for r in _cr.execute("SELECT * FROM invoices WHERE project_id=? ORDER BY id ASC", (p['id'],)).fetchall()]
    _p_rows.sort(key=invoice_serial)
    _cr.close()
    _types = [only_type] if only_type else ["Tax Invoice", "Proforma Invoice"]
    _rtabs = [st.container()] if only_type else st.tabs(_types)
    for _tab, _itype in zip(_rtabs, _types):
        with _tab:
            _sub = [r for r in _p_rows if r['invoice_type'] == _itype]
            _rdf = pd.DataFrame([{
                "Sr. No.": n, "Invoice No.": r['invoice_no'], "Date": dmy(r['invoice_date']), "Basic": r['basic_amount'], "Total": r['grand_total'],
            } for n, r in enumerate(_sub, 1)], columns=["Sr. No.", "Invoice No.", "Date", "Basic", "Total"])
            _pick = _sub[-1]['invoice_no'] if _sub else None   # the latest saved invoice of this type
            _ms_all = fetch_milestones(p['id'])
            # The milestones picked in "Select Milestones" at the top of this page decide what the PDF lists.
            _chosen_ids = []   # every milestone of the project is listed in the PDF
            if _sub:
                _r = next(x for x in _sub if x['invoice_no'] == _pick)
            _d1, _d2 = (st.container(), None) if pdf_only else st.columns(2)
            if _sub:
                _payload = dict(_r)
                _payload['items'] = pdf_items_for(_r, _ms_all, set(_chosen_ids))
                _payload['invoice_date'] = date.fromisoformat(_r['invoice_date']).strftime("%d.%m.%Y")
                _d1.download_button(f"Download {_itype} Report (PDF)" if pdf_only else f"Download {_itype} PDF", data=build_invoice_pdf(company, p, _payload),
                                    file_name=f"{_pick.replace('/', '-')}.pdf", mime="application/pdf", type="primary",
                                    use_container_width=True, key=f"ci_dl_{_itype}_{p['id']}")
            else:
                _d1.button(f"Download {_itype} PDF", disabled=True, use_container_width=True, key=f"ci_dl_off_{_itype}_{p['id']}")
            if _d2 is not None:
                _d2.download_button(f"Download {_itype} list (CSV)", data=_rdf.to_csv(index=False).encode("utf-8-sig"),
                                    file_name=f"{_itype.replace(' ', '_').lower()}_report.csv", mime="text/csv", disabled=not _sub,
                                    use_container_width=True, key=f"ci_csv_{_itype}_{p['id']}")


def build_all_companies_report(fy):
    """Report of one financial year covering every company (firm): its projects with P.O., billing and totals.
    Returns (DataFrame with company sub-totals and a grand total, PDF bytes)."""
    c = conn()
    comps = [dict(r) for r in c.execute("SELECT * FROM companies ORDER BY id").fetchall()]
    projs = [dict(r) for r in c.execute("SELECT * FROM projects WHERE financial_year=? ORDER BY COALESCE(company_id,1), id", (fy,)).fetchall()]
    invs = [dict(r) for r in c.execute("SELECT * FROM invoices WHERE invoice_type='Tax Invoice'").fetchall()]
    mss = [dict(r) for r in c.execute("SELECT project_id, COUNT(*) n, SUM(CASE WHEN completed_on IS NOT NULL THEN 1 ELSE 0 END) d FROM milestones GROUP BY project_id").fetchall()]
    all_ms = [dict(r) for r in c.execute("SELECT * FROM milestones ORDER BY project_id, milestone_no").fetchall()]
    c.close()
    ms_by = {m["project_id"]: m for m in mss}
    cols = ["Company", "Client", "Project", "P.O. No.", "P.O. Amount (₹)", "Milestones", "Completed", "Tax Invoices", "Basic Billed (₹)", "GST (₹)", "Total Invoiced (₹)"]
    rows, grand = [], {k: 0.0 for k in ("po", "ms", "done", "n", "basic", "gst", "total")}
    for comp in comps:
        sub = {k: 0.0 for k in grand}
        for p in [x for x in projs if (x.get("company_id") or 1) == comp["id"]]:
            pi = [i for i in invs if i["project_id"] == p["id"]]
            basic = sum(float(i["basic_amount"] or 0) for i in pi); total = sum(float(i["grand_total"] or 0) for i in pi)
            m = ms_by.get(p["id"], {"n": 0, "d": 0})
            rows.append({"Company": comp["name"], "Client": p["client_name"], "Project": p["project_name"], "P.O. No.": p["po_no"] or "",
                         "P.O. Amount (₹)": float(p["po_amount"] or 0), "Milestones": int(m["n"] or 0), "Completed": int(m["d"] or 0),
                         "Tax Invoices": len(pi), "Basic Billed (₹)": basic, "GST (₹)": total - basic, "Total Invoiced (₹)": total})
            for k, v in (("po", float(p["po_amount"] or 0)), ("ms", int(m["n"] or 0)), ("done", int(m["d"] or 0)), ("n", len(pi)), ("basic", basic), ("gst", total - basic), ("total", total)):
                sub[k] += v; grand[k] += v
        rows.append({"Company": f"{comp['name']} — TOTAL", "Client": "", "Project": "", "P.O. No.": "", "P.O. Amount (₹)": sub["po"], "Milestones": int(sub["ms"]),
                     "Completed": int(sub["done"]), "Tax Invoices": int(sub["n"]), "Basic Billed (₹)": sub["basic"], "GST (₹)": sub["gst"], "Total Invoiced (₹)": sub["total"]})
    rows.append({"Company": "ALL COMPANIES — TOTAL", "Client": "", "Project": "", "P.O. No.": "", "P.O. Amount (₹)": grand["po"], "Milestones": int(grand["ms"]),
                 "Completed": int(grand["done"]), "Tax Invoices": int(grand["n"]), "Basic Billed (₹)": grand["basic"], "GST (₹)": grand["gst"], "Total Invoiced (₹)": grand["total"]})
    df = pd.DataFrame(rows, columns=cols)

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=25*mm, rightMargin=8*mm, topMargin=12*mm, bottomMargin=12*mm)
    st_ = getSampleStyleSheet()
    small = ParagraphStyle("acs", parent=st_["BodyText"], fontSize=7.5, leading=9)
    data = [["Company", "Client", "Project", "P.O. No.", "P.O. Amount", "Mile-stones", "Done", "Tax Inv.", "Basic Billed", "GST", "Total Invoiced"]]
    bold_rows = []
    for _i, r in enumerate(df.to_dict("records"), 1):
        is_total = "TOTAL" in r["Company"]
        if is_total:
            bold_rows.append(_i)
        data.append([Paragraph(r["Company"], small) if not is_total else r["Company"], Paragraph(r["Client"], small), Paragraph(r["Project"], small), r["P.O. No."],
                     indian(r["P.O. Amount (₹)"], False), r["Milestones"], r["Completed"], r["Tax Invoices"],
                     indian(r["Basic Billed (₹)"], False), indian(r["GST (₹)"], False), indian(r["Total Invoiced (₹)"], False)])
    tb = Table(data, colWidths=[w * mm for w in fit_widths([44.0, 36.0, 56.0, 26.0, 24.0, 13.0, 11.0, 12.0, 24.0, 20.0, 26.0], 264)], repeatRows=1)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d3e5ee")),
             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("ALIGN", (4, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    for bi in bold_rows:
        style += [("BACKGROUND", (0, bi), (-1, bi), colors.HexColor("#eef4f8")), ("FONTNAME", (0, bi), (-1, bi), "Helvetica-Bold")]
    tb.setStyle(TableStyle(style))
    # one separate section (new page) per company; the firm names are not printed
    NC = 9
    head = ["No.", "Milestone / Scope of Work", "Due Date", "Basic", "GST", "Scheduled", "Completed On", "Invoice No.", "Status"]
    widths = [w * mm for w in fit_widths([9.0, 88.0, 20.0, 24.0, 21.0, 25.0, 24.0, 30.0, 23.0], 264)]
    # one table for all projects, so the report uses as few pages as possible (no empty space between companies)
    cps_all = [x for comp in comps for x in projs if (x.get("company_id") or 1) == comp["id"]]
    story = [Paragraph(f"All Companies Report — FY {fy}", ParagraphStyle("acsh", parent=st_["Heading2"], fontSize=13))]
    if not cps_all:
        story.append(Paragraph("No projects this year", small))
    else:
        # a separate numbered table for every project; the whole report is shrunk to fit on one page
        tiny = ParagraphStyle("actn", parent=small, fontSize=7, leading=8)
        phead = ParagraphStyle("acph", parent=st_["Heading3"], fontSize=9, leading=11, spaceBefore=0, spaceAfter=1.5)
        body = []
        for n, p in enumerate(cps_all, 1):
            mdata = [head]
            pms = [m for m in all_ms if m["project_id"] == p["id"]]
            if not pms:
                mdata.append(["", Paragraph("No milestones", tiny)] + [""] * (NC - 2))
            for m in pms:
                amt = float(m.get("amount") or 0)
                gst = float(m["gst_amount"]) if m.get("gst_amount") is not None else amt * float(m.get("gst_rate") or 18) / 100
                sch = float(m["scheduled_amount"]) if m.get("scheduled_amount") is not None else amt + gst
                status = "Completed" if m.get("completed_on") else ("Partially paid" if m.get("payment_status") == "Partially Collected" else "Not completed")
                mdata.append([m["milestone_no"], Paragraph(m.get("description") or "", tiny), dmy(m["due_date"]) if m.get("due_date") else "",
                              indian(amt, False), indian(gst, False), indian(sch, False),
                              dmy(m["completed_on"]) if m.get("completed_on") else "", m.get("completed_invoice") or "", status])
            mt = Table(mdata, colWidths=widths, repeatRows=1)
            mt.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d3e5ee")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7), ("ALIGN", (3, 0), (5, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
            body += [Paragraph(f"{n}. {p['client_name']}", phead), mt, Spacer(1, 3*mm)]
        story.append(Spacer(1, 2*mm)); story.append(KeepInFrame(0, 0, body, mode="shrink"))
    doc.build(story, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
    return df, out.getvalue()


def render_yearly_report():
    # ---- Yearly company-wise report: the financial year chosen at the top of the page ----
    _fy = selected_fy
    _comps = fetch_companies()
    _cid = st.selectbox("Company", [x["id"] for x in _comps], format_func=lambda i: next(x["name"] for x in _comps if x["id"] == i),
                        index=[x["id"] for x in _comps].index(active_company_id()) if active_company_id() in [x["id"] for x in _comps] else 0,
                        key="yr_company")
    _ycomp = fetch_company(_cid)
    _projects = fetch_projects(_fy, _cid)
    _plabels = {p['id']: f"{p['client_name']} — {p['project_name']}" for p in _projects}
    _psel = st.selectbox("Project", [p['id'] for p in _projects], index=None, format_func=lambda i: _plabels[i], placeholder=" ",
                         key=f"yr_project_{_cid}_{_fy}")
    if _psel:
        _projects = [p for p in _projects if p['id'] == _psel]
    if _psel:
        st.markdown(f"#### Project Milestone Report — FY {_fy}")
    _cw_pdf = _cw_csv = _ms_csv = _reg_csv = None
    _c = conn()
    _inv = [dict(r) for r in _c.execute("SELECT * FROM invoices").fetchall()]
    _ms = [dict(r) for r in _c.execute("SELECT * FROM milestones").fetchall()]
    _c.close()
    # project-wise rows of the chosen company
    cw_rows = []
    for _p in sorted(_projects, key=lambda p: (p['client_name'], p['id'])):
        _pi = [i for i in _inv if i['project_id'] == _p['id'] and i['invoice_type'] == "Tax Invoice"]
        _bas = sum(float(i['basic_amount'] or 0) for i in _pi); _tot = sum(float(i['grand_total'] or 0) for i in _pi)
        cw_rows.append({"Client": _p['client_name'], "Project": _p['project_name'], "P.O. No.": _p['po_no'] or "",
                        "P.O. Amount (₹)": float(_p['po_amount'] or 0), "Tax Invoices": len(_pi),
                        "Basic Billed (₹)": _bas, "GST (₹)": _tot - _bas, "Total Invoiced (₹)": _tot})
    if cw_rows:
        cw = pd.DataFrame(cw_rows)
        total_row = {"Client": "TOTAL", "Project": "", "P.O. No.": "", **{col: cw[col].sum() for col in cw.columns if col.endswith("(₹)") or col == "Tax Invoices"}}
        cw_all = pd.concat([cw, pd.DataFrame([total_row])], ignore_index=True)
        _pmap = {p['id']: p for p in _projects}
        _ms_rows = []
        for _p in sorted(_projects, key=lambda p: (p['client_name'], p['id'])):
            for _m in [m for m in _ms if m['project_id'] == _p['id'] and not is_blank_milestone(m)]:     # completed milestones stay; blank ones do not
                _n = _m['milestone_no']
                _amt = float(_m.get('amount') or 0); _rate = float(_m['gst_rate']) if _m.get('gst_rate') is not None else 18.0
                _gst = float(_m['gst_amount']) if _m.get('gst_amount') is not None else _amt * _rate / 100
                _sch = float(_m['scheduled_amount']) if _m.get('scheduled_amount') is not None else _amt + _gst
                _rec = float(_m.get('advance_received') or 0) + float(_m.get('actual_amount') or 0)
                _bal = float(_m['balance_amount']) if _m.get('balance_amount') is not None else max(_sch - _rec, 0.0)
                _ms_rows.append({
                    "Company": _p['client_name'], "Project": _p['project_name'], "Sr. No.": _n, "Milestone / Scope of Work": _m.get('description') or "",
                    "Due Date": dmy(_m['due_date']) if _m.get('due_date') else "", "Basic (₹)": _amt, "GST (₹)": _gst, "Scheduled (₹)": _sch,
                    "Received (₹)": _rec, "Balance Before TDS (₹)": _bal,
                    "Completed On": dmy(_m['completed_on']) if _m.get('completed_on') else "", "Invoice No.": _m.get('completed_invoice') or "",
                    "Status": "Completed" if _m.get('completed_on') else ("Partially paid" if _m.get('payment_status') == "Partially Collected" else "Not completed"),
                })
        ms_all = pd.DataFrame(_ms_rows, columns=["Company", "Project", "Sr. No.", "Milestone / Scope of Work", "Due Date", "Basic (₹)", "GST (₹)",
                                                 "Scheduled (₹)", "Received (₹)", "Balance Before TDS (₹)", "Completed On", "Invoice No.", "Status"])
        # Invoice-wise register: date, P.O., basic, GST (CGST / SGST / IGST), TDS, total, paid, balance.
        _reg = []
        _pmap2 = {p['id']: p for p in _projects}
        for _i in sorted([i for i in _inv if i['project_id'] in _pmap2 and i['invoice_type'] == "Tax Invoice"], key=lambda r: (r['invoice_date'], invoice_serial(r))):
            _pay = invoice_payment(_i); _paid = _pay["paid"]; _tds = _pay["tds"]
            _tot = float(_i['grand_total'] or 0); _bas = float(_i['basic_amount'] or 0)
            _reg.append({
                "Sr. No.": len(_reg) + 1, "Date": dmy(_i['invoice_date']), "Invoice No.": _i['invoice_no'], "Company": _pmap2[_i['project_id']]['client_name'],
                "P.O. No.": _pmap2[_i['project_id']]['po_no'] or "", "Basic Amount (₹)": _bas, "GST (₹)": _tot - _bas,
                "CGST (₹)": float(_i['cgst'] or 0), "SGST (₹)": float(_i['sgst'] or 0), "IGST (₹)": float(_i['igst'] or 0),
                "TDS (₹)": _tds, "Total Amount (₹)": _tot, "Paid Amount (₹)": _paid, "Balance Amount (₹)": _pay["balance"], "Status": _pay["status"],
            })
        _reg_cols = ["Sr. No.", "Date", "Invoice No.", "Company", "P.O. No.", "Basic Amount (₹)", "GST (₹)", "CGST (₹)", "SGST (₹)", "IGST (₹)",
                     "TDS (₹)", "Total Amount (₹)", "Paid Amount (₹)", "Balance Amount (₹)", "Status"]
        reg_df = pd.DataFrame(_reg, columns=_reg_cols)
        if len(reg_df):
            reg_df = pd.concat([reg_df, pd.DataFrame([{"Date": "TOTAL", **{c: reg_df[c].sum() for c in _reg_cols if c.endswith("(₹)")}}])], ignore_index=True)
        _out = io.BytesIO()
        _doc = SimpleDocTemplate(_out, pagesize=landscape(A4), leftMargin=25*mm, rightMargin=8*mm, topMargin=12*mm, bottomMargin=12*mm)
        _st = getSampleStyleSheet()
        _small = ParagraphStyle("cws", parent=_st["BodyText"], fontSize=8, leading=10)
        _data = [["Client", "Project", "P.O. No.", "P.O. Amount", "Tax Inv.", "Basic Billed", "GST", "Total Invoiced"]]
        for _r in cw_all.to_dict("records"):
            _data.append([Paragraph(_r["Client"], _small), Paragraph(_r["Project"], _small), _r["P.O. No."], indian(_r["P.O. Amount (₹)"], False), int(_r["Tax Invoices"]),
                          indian(_r["Basic Billed (₹)"], False), indian(_r["GST (₹)"], False), indian(_r["Total Invoiced (₹)"], False)])
        _tb = Table(_data, colWidths=[w * mm for w in fit_widths([46.0, 66.0, 28.0, 28.0, 14.0, 30.0, 24.0, 30.0], 264)], repeatRows=1)
        _tb.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d3e5ee")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef4f8")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        # One table per company, all on a single page.
        _tiny = ParagraphStyle("cwt", parent=_small, fontSize=7, leading=8.5)
        _chead = ParagraphStyle("cwh", parent=_st["Heading3"], fontSize=10, leading=12, spaceBefore=0, spaceAfter=2)
        _mt = []
        _ms_recs = ms_all.to_dict("records")
        for _cn in dict.fromkeys(p["client_name"] for p in _projects):
            _mdata = [["Project", "Sr.", "Milestone / Scope of Work", "Due Date", "Basic", "GST", "Scheduled", "Completed On", "Invoice No.", "Status"]]
            for _r in [r for r in _ms_recs if r["Company"] == _cn]:
                _mdata.append([Paragraph(_r["Project"], _tiny), _r["Sr. No."], Paragraph(_r["Milestone / Scope of Work"], _tiny),
                               _r["Due Date"], indian(_r["Basic (₹)"], False), indian(_r["GST (₹)"], False), indian(_r["Scheduled (₹)"], False),
                               _r["Completed On"], _r["Invoice No."], _r["Status"]])
            _t = Table(_mdata, colWidths=[w * mm for w in fit_widths([58.0, 9.0, 56.0, 19.0, 24.0, 20.0, 24.0, 22.0, 28.0, 24.0], 264)], repeatRows=1)
            _t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d3e5ee")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7), ("ALIGN", (4, 0), (6, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            _mt += [Paragraph(_cn, _chead), _t, Spacer(1, 4*mm)]
        _rdata = [["Date", "Invoice No.", "Company", "P.O. No.", "Basic", "GST", "CGST", "SGST", "IGST", "TDS", "Total"]]
        for _r in reg_df.to_dict("records"):
            _bold = _r["Date"] == "TOTAL"
            _rdata.append([_r["Date"], _r["Invoice No."] if isinstance(_r["Invoice No."], str) else "", Paragraph(_r["Company"] if isinstance(_r["Company"], str) else "", _small),
                           _r["P.O. No."] if isinstance(_r["P.O. No."], str) else "", indian(_r["Basic Amount (₹)"], False), indian(_r["GST (₹)"], False),
                           indian(_r["CGST (₹)"], False), indian(_r["SGST (₹)"], False), indian(_r["IGST (₹)"], False), indian(_r["TDS (₹)"], False),
                           indian(_r["Total Amount (₹)"], False)])
        _rt = Table(_rdata, colWidths=[w * mm for w in fit_widths([20.0, 28.0, 50.0, 32.0, 26.0, 22.0, 20.0, 20.0, 22.0, 20.0, 26.0], 264)], repeatRows=1)
        _rt.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d3e5ee")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef4f8")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7), ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        _title = _plabels[_psel] if _psel else _ycomp['name']
        _doc.build([Paragraph(f"Milestone Report — {_title}", ParagraphStyle("cwm", parent=_st["Heading2"], fontSize=13)),
                    Spacer(1, 2*mm), *_mt], onFirstPage=draw_watermark, onLaterPages=draw_watermark)
        _cw_pdf = _out.getvalue()
        _cw_csv = cw_all.to_csv(index=False).encode("utf-8-sig")
        _ms_csv = ms_all.to_csv(index=False).encode("utf-8-sig")
        _reg_csv = reg_df.to_csv(index=False).encode("utf-8-sig")
    else:
        st.caption(f"No projects in Financial Year {_fy}.")
    if _cw_pdf and _psel:
        st.download_button("Download Project Milestone Report (PDF)", data=_cw_pdf, file_name=f"milestone_report_{_fy}.pdf",
                           mime="application/pdf", type="primary", use_container_width=True, key="cw_pdf")
    _ac_df, _ac_pdf = build_all_companies_report(_fy)
    st.markdown("---")
    st.markdown(f"### All Companies Report — FY {_fy}")
    st.download_button(f"Download All Companies Report — FY {_fy} (PDF)", data=_ac_pdf, file_name=f"all_companies_report_{_fy}.pdf",
                       mime="application/pdf", type="primary", use_container_width=True, key="all_co_pdf")


def render_clients_projects():
    PROJECT_DEFAULTS = {
        "pf_client_name": "", "pf_project_name": "", "pf_billing_address": "",
        "pf_site_address": "", "pf_location": "", "pf_state": "Maharashtra", "pf_state_code": "27",
        "pf_gstin": "", "pf_pan": "", "pf_po_no": "", "pf_po_date": date.today(),
        "pf_po_amount": 0.0, "pf_vendor_id": "", "pf_kind_attention": "",
    }
    FIELD_TO_KEY = {
        "client_name": "pf_client_name", "project_name": "pf_project_name", "billing_address": "pf_billing_address",
        "site_address": "pf_site_address", "location": "pf_location", "state": "pf_state", "state_code": "pf_state_code",
        "gstin": "pf_gstin", "pan": "pf_pan", "po_no": "pf_po_no", "po_date": "pf_po_date",
        "po_amount": "pf_po_amount", "vendor_id": "pf_vendor_id", "kind_attention": "pf_kind_attention",
    }

    def start_new_project():
        st.session_state["_new_mode"] = True
        st.session_state["current_project"] = None
        for k, v in PROJECT_DEFAULTS.items():
            st.session_state[k] = v
        st.session_state["sel_project"] = None

    def load_selected_project():
        st.session_state["_new_mode"] = False
        pid = st.session_state.get("sel_project")
        if not pid:
            return
        st.session_state["current_project"] = pid
        st.session_state["_form_project"] = pid
        proj = fetch_project(pid)
        if not proj:
            return
        for field, key in FIELD_TO_KEY.items():
            val = proj.get(field)
            if field == "po_date":
                try:
                    val = date.fromisoformat(val)
                except Exception:
                    val = date.today()
            elif field == "po_amount":
                val = float(val or 0)
            elif field == "state":
                val = normalize_state(val)
            else:
                val = val or ""
            st.session_state[key] = val
        st.session_state["pf_state_code"] = GST_STATES.get(st.session_state["pf_state"], st.session_state["pf_state_code"])

    def on_state_change():
        st.session_state["pf_state_code"] = GST_STATES.get(st.session_state["pf_state"], st.session_state["pf_state_code"])

    for k, v in PROJECT_DEFAULTS.items():
        st.session_state.setdefault(k, v)

    def project_values():
        return {f: st.session_state[k] for f, k in FIELD_TO_KEY.items()}

    def save_project(update):
        v = project_values()
        if not v["client_name"].strip() or not v["project_name"].strip():
            st.session_state["_flash"] = ("error", "Client name and project name are required.")
            return
        c = conn()
        params = (v["client_name"], v["project_name"], v["billing_address"], v["site_address"], v["location"],
                  v["state"], v["state_code"], v["gstin"], v["pan"], v["po_no"], v["po_date"].isoformat(),
                  v["po_amount"], v["vendor_id"], v["kind_attention"])
        if update:
            c.execute("""UPDATE projects SET client_name=?,project_name=?,billing_address=?,site_address=?,location=?,state=?,state_code=?,gstin=?,pan=?,po_no=?,po_date=?,po_amount=?,vendor_id=?,kind_attention=? WHERE id=?""", params + (st.session_state["sel_project"],))
            msg = "Project updated."
        else:
            cur = c.execute("""INSERT INTO projects(client_name,project_name,billing_address,site_address,location,state,state_code,gstin,pan,po_no,po_date,po_amount,vendor_id,kind_attention,financial_year,company_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", params + (selected_fy, active_company_id()))
            st.session_state["sel_project_pending"] = cur.lastrowid
            st.session_state["_new_mode"] = False
            msg = "New project saved. Click ➕ Create Milestone below to add its milestones."
        c.commit(); c.close()
        st.session_state["_flash"] = ("success", msg)

    flash = st.session_state.pop("_flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])
    # A newly saved project is selected on the next run (before the selectbox is created).
    pending = st.session_state.pop("sel_project_pending", None)
    if pending:
        st.session_state["sel_project"] = pending
        st.session_state["current_project"] = pending
    projects = fetch_projects(selected_fy)
    if True:
        proj_ids = [p['id'] for p in projects]
        proj_labels = {p['id']: project_label(p) for p in projects}
        if st.session_state.get("_new_mode"):
            st.session_state["sel_project"] = None
        else:
            # The current project (shared by every page) is opened here, and its details are loaded.
            cp = current_project_for(proj_ids)
            if st.session_state.get("sel_project") != cp:
                st.session_state["sel_project"] = cp
                if cp:
                    load_selected_project()
            if not cp and st.session_state.get("_form_project"):
                # This year has no projects: clear the form so no project from another year is shown.
                for k, v in PROJECT_DEFAULTS.items():
                    st.session_state[k] = v
                st.session_state["_form_project"] = None
        st.selectbox(
            "Select Company / Previous Project", proj_ids, index=None, key="sel_project",
            format_func=lambda i: proj_labels[i], placeholder="Search and select a previous project",
            on_change=load_selected_project,
        )
        st.button("➕ New Project", type="primary", on_click=start_new_project, key="new_project_btn")

    with st.expander("Project Details — click to edit" if not st.session_state.get("_new_mode") else "New Project — fill in the details and click Save Project",
                     expanded=(not proj_ids) or bool(st.session_state.get("_new_mode"))):
        r1c1, r1c2 = st.columns(2)
        r1c1.text_input("Client / Company Name *", key="pf_client_name")
        r1c2.text_input("Project Name *", key="pf_project_name")
        st.text_area("Billing Address", key="pf_billing_address")
        st.text_area("Site Address / Project Address", key="pf_site_address")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Location", key="pf_location")
        state_options = list(GST_STATES)
        if st.session_state["pf_state"] not in state_options:
            st.session_state["pf_state"] = normalize_state(st.session_state["pf_state"])
            if st.session_state["pf_state"] not in state_options:
                state_options.append(st.session_state["pf_state"])
        c2.selectbox("State", state_options, key="pf_state", on_change=on_state_change)
        c3.text_input("State Code (auto)", key="pf_state_code", disabled=True)
        st.caption(f"GST for {st.session_state['pf_state']}: **{gst_mode_for_state(st.session_state['pf_state'])}**" + (" (CGST + SGST applies only to Maharashtra)" if st.session_state['pf_state'] == "Maharashtra" else " (IGST applies to all states other than Maharashtra)"))
        c1, c2 = st.columns(2)
        c1.text_input("GST No. / GSTIN", key="pf_gstin")
        c2.text_input("PAN No.", key="pf_pan")
        c1, c2, c3 = st.columns(3)
        c1.text_input("P.O. / Work Order No.", key="pf_po_no")
        c2.date_input("P.O. Date", key="pf_po_date")
        c3.number_input("P.O. Amount (₹)", min_value=0.0, step=1000.0, format="%.2f", key="pf_po_amount")
        c1, c2 = st.columns(2)
        c1.text_input("Vendor ID", key="pf_vendor_id")
        c2.text_input("Kind Attention", key="pf_kind_attention")

        if not proj_ids or st.session_state.get("_new_mode"):
            # Nothing saved yet, or "New Project" was clicked: the details above are saved as a new project.
            st.button("💾 Save Project", type="primary", use_container_width=True, on_click=save_project, args=(False,), key="save_project_btn")

    st.markdown("---")
    st.markdown("### Project Milestones")
    _sel_p = fetch_project(st.session_state["sel_project"]) if st.session_state.get("sel_project") else None
    if _sel_p:
        render_milestone_section(_sel_p)
    else:
        st.caption("Select a previous project above (or save the new project first) to add its milestones here.")


if page == "Dashboard":
    import altair as alt

    def short_inr(v):
        v = float(v or 0)
        if abs(v) >= 1e7:
            return f"₹ {v/1e7:.2f} Cr"
        if abs(v) >= 1e5:
            return f"₹ {v/1e5:.2f} L"
        return f"₹ {v:,.0f}"

    pids = [p['id'] for p in projects]
    c = conn()
    inv_rows = [dict(r) for r in c.execute("SELECT * FROM invoices").fetchall() if r['project_id'] in pids]
    ms_rows = [dict(r) for r in c.execute("SELECT * FROM milestones").fetchall() if r['project_id'] in pids]
    c.close()
    tax_inv = [r for r in inv_rows if r['invoice_type'] == "Tax Invoice"]
    po_total = sum(float(p['po_amount'] or 0) for p in projects)
    billed = sum(r['basic_amount'] or 0 for r in tax_inv)
    invoiced = sum(r['grand_total'] or 0 for r in tax_inv)
    _pays = [invoice_payment(r) for r in tax_inv]
    received = sum(x["paid"] for x in _pays)
    balance = sum(x["balance"] for x in _pays)

    st.markdown(f"<div class='dash-head'><div><div class='dash-title'>Dashboard</div><div class='dash-sub'>Financial Year {selected_fy} overview</div></div><div class='dash-chip'>FY {selected_fy}</div></div>", unsafe_allow_html=True)

    cards = [
        ("Projects", f"{len(projects)}", f"{len(ms_rows)} milestones", "#0b7285"),
        ("P.O. Value", short_inr(po_total), "total work orders", "#3b5bdb"),
        ("Tax Invoiced", short_inr(invoiced), f"{len(tax_inv)} tax invoice(s)", "#7048e8"),
        ("Received", short_inr(received), f"{sum(1 for x in _pays if x['status'] == 'Paid')} of {len(_pays)} invoices paid", "#2f9e44"),
        ("Balance to Collect", short_inr(balance), f"{sum(1 for x in _pays if x['status'] != 'Paid')} invoice(s) unpaid", "#e8590c"),
    ]
    st.markdown(
        "<div class='kpi-row'>" + "".join(
            f"<div class='kpi' style='--accent:{col}'><div class='kpi-label'>{lab}</div><div class='kpi-value'>{val}</div><div class='kpi-note'>{note}</div></div>"
            for lab, val, note, col in cards) + "</div>", unsafe_allow_html=True)

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("<div class='panel-title'>Invoice value by month</div>", unsafe_allow_html=True)
        if inv_rows:
            mdf = pd.DataFrame([{"Month": pd.to_datetime(r['invoice_date']).to_period("M").to_timestamp(), "Type": r['invoice_type'], "Amount": r['grand_total'] or 0} for r in inv_rows])
            mdf = mdf.groupby(["Month", "Type"], as_index=False)["Amount"].sum()
            chart = alt.Chart(mdf).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=34).encode(
                x=alt.X("Month:T", timeUnit="yearmonth", title=None, axis=alt.Axis(format="%b %Y", labelAngle=0)),
                y=alt.Y("Amount:Q", title=None, axis=alt.Axis(format="~s")),
                color=alt.Color("Type:N", scale=alt.Scale(domain=["Tax Invoice", "Proforma Invoice"], range=["#0b7285", "#b197fc"]), legend=alt.Legend(orient="top", title=None)),
                tooltip=["Type", alt.Tooltip("Amount:Q", format=",.0f")],
            ).properties(height=280)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("No invoices saved in this financial year yet.")
    with right:
        st.markdown("<div class='panel-title'>Invoice payment status</div>", unsafe_allow_html=True)
        if _pays:
            sdf = pd.Series([x["status"] for x in _pays]).value_counts().rename_axis("Status").reset_index(name="Count")
            donut = alt.Chart(sdf).mark_arc(innerRadius=62, outerRadius=105).encode(
                theta="Count:Q",
                color=alt.Color("Status:N", scale=alt.Scale(domain=["Paid", "Partially Paid", "Pending", "Overdue"], range=["#f76707", "#2f9e44", "#74c0fc", "#e03131"]), legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["Status", "Count"],
            ).properties(height=280)
            st.altair_chart(donut, use_container_width=True)
        else:
            st.caption("No tax invoices yet.")

    st.markdown(f"<div class='panel-title'>P.O. progress — FY {selected_fy}</div>", unsafe_allow_html=True)
    if projects:
        _ids = [p['id'] for p in projects]
        st.session_state["po_prog"] = current_project_for(_ids)
        sel_pid = st.selectbox("Project", _ids, format_func=lambda i: project_label({q['id']: q for q in projects}[i]),
                               key="po_prog", label_visibility="collapsed", on_change=set_current_project, args=("po_prog",))
        p = next(q for q in projects if q['id'] == sel_pid)
        p_billed = sum(r['basic_amount'] or 0 for r in tax_inv if r['project_id'] == p['id'])
        po = float(p['po_amount'] or 0)
        pct = min(p_billed / po * 100, 100) if po else 0
        st.markdown(
            f"<div class='prog'><div class='prog-top'><span class='prog-name'>{p['project_name']}</span>"
            f"<span class='prog-val'>{short_inr(p_billed)} of {short_inr(po)} &nbsp;·&nbsp; {pct:.0f}%</span></div>"
            f"<div class='prog-bar'><div class='prog-fill' style='width:{pct:.1f}%'></div></div>"
            f"<div class='prog-sub'>{p['client_name']} &nbsp;·&nbsp; P.O. {p['po_no'] or '-'}</div></div>", unsafe_allow_html=True)
    else:
        st.caption(f"No projects in Financial Year {selected_fy}.")

elif page == "Company Setup":
    st.markdown("### Company / Admin Details")
    flash = st.session_state.pop("_company_flash", None)
    if flash:
        st.success(flash)
    _cs = fetch_companies()

    def _pick_company():
        st.session_state["active_company"] = st.session_state["cs_company"]

    st.session_state["cs_company"] = active_company_id()
    st.selectbox("Company Name *", [x["id"] for x in _cs], format_func=lambda i: next(x["name"] for x in _cs if x["id"] == i),
                 key="cs_company", on_change=_pick_company)
    with st.expander("Company Details — click to edit (common to all companies)", expanded=False):
        with st.form("company_form"):
            f_addr = st.text_area("Company Address *", company['address'])
            c1, c2 = st.columns(2)
            f_email = c1.text_input("Email", company['email'])
            f_mobile = c2.text_input("Mobile No.", company['mobile'])
            f_gstin = st.text_input("GST No. / GSTIN", company['gstin'])
            f_bank = st.text_area("Bank Details (one item per line)", company['bank_details'], height=130)
            f_terms = st.text_area("Terms & Conditions", company['terms'], height=100)
            saved = st.form_submit_button("Save Company Details", type="primary", use_container_width=True)
    if saved:
        if not f_addr.strip():
            st.error("Company address is required.")
        else:
            vals = (f_addr.strip(), f_email.strip(), f_mobile.strip(), f_gstin.strip(), f_bank.strip(), f_terms.strip())
            cc = conn()
            # same details for every company; each company keeps its own name
            cc.execute("UPDATE companies SET address=?, email=?, mobile=?, gstin=?, bank_details=?, terms=?", vals)
            cc.commit(); cc.close()
            st.session_state["_company_flash"] = "Company details saved for all companies."
            st.rerun()

    st.markdown("### Clients & Projects")
    render_clients_projects()


elif page == "Create Invoice":
    st.markdown("### Create Proforma / Tax Invoice")
    if not projects:
        st.warning(f"No projects in Financial Year {selected_fy}. Add one in Clients & Projects, or pick another year in the sidebar.")
    else:
        _ids = [q['id'] for q in projects]
        _labels = {q['id']: project_label(q) for q in projects}
        st.session_state["ci_project"] = current_project_for(_ids)
        _pid = st.selectbox("Company / Project", _ids, format_func=lambda i: _labels[i], key="ci_project",
                            on_change=set_current_project, args=("ci_project",))
        p = fetch_project(_pid); milestones = fetch_milestones(p['id'], active_only=True)
        milestone_names = [f"{m['milestone_no']}. {m['milestone_name'] or m['description']}" for m in milestones]
        # Automatic choice: the first open milestone that has not been invoiced yet (else the first open one).
        _bc = conn()
        _billed = set()
        for _ir in _bc.execute("SELECT description, items_json FROM invoices WHERE project_id=? AND invoice_type='Tax Invoice'", (p['id'],)).fetchall():
            try:
                _its = json.loads(_ir["items_json"]) if _ir["items_json"] else [{"description": _ir["description"], "billed": True, "amount": 1}]
            except Exception:
                _its = []
            _billed |= {i.get("description") for i in _its if i.get("billed", True) and float(i.get("amount") or 0) > 0}
        _bc.close()
        _auto = next((n for n, m in zip(milestone_names, milestones) if (m['description'] or "") not in _billed), milestone_names[0] if milestone_names else None)
        chosen = st.multiselect(
            "Select Milestones", milestone_names,
            default=[_auto] if _auto else [], key=f"ms_sel_{p['id']}_{len(_billed)}", accept_new_options=True,
            placeholder="Select a saved milestone, or type a new one and press Enter",
            help="Each selected milestone becomes a line in the invoice PDF. You can also type your own milestone text. The Invoice Items table below is fully editable (add, edit or delete lines).",
        )
        custom_items = [n for n in chosen if n not in milestone_names]
        selected_list = sorted((milestones[milestone_names.index(n)] for n in chosen if n in milestone_names), key=lambda m: m['milestone_no'])
        first = selected_list[0] if selected_list else None
        sel_key = f"{p['id']}_" + ("-".join(str(m['id']) for m in selected_list) or "manual") + (f"_c{abs(hash(tuple(custom_items))) % 10**8}" if custom_items else "")
        c1,c2,c3,c4,c5 = st.columns([1, 1, 1.4, 1, 0.8])
        types = ["Tax Invoice", "Proforma Invoice"]
        invoice_type = c1.selectbox("Invoice Type", types, key=f"invoice_type_{sel_key}")
        ms_date = None
        if first and first.get('invoice_date'):
            try:
                ms_date = date.fromisoformat(first['invoice_date'])
            except Exception:
                ms_date = None
        inv_date = c2.date_input("Invoice Date", ms_date or date.today(), key=f"inv_date_{sel_key}")
        auto_no = next_invoice_no(inv_date, invoice_type)
        bill_state = normalize_state(p['state'])
        tax_mode = gst_mode_for_state(bill_state)
        c4.text_input("GST Mode (automatic)", tax_mode, disabled=True, key=f"gmode_{sel_key}_{bill_state}")
        ms_rate = (first or {}).get('gst_rate')
        tax_rate = c5.number_input("GST Rate (%)", min_value=0.0, max_value=50.0, value=float(ms_rate if ms_rate is not None else 18.0), step=1.0, key=f"grate_{sel_key}")
        invoice_no = c3.text_input("Invoice Number (auto-generated, editable)", auto_no, key=f"invoice_number_{auto_no}",
                                   help="Filled in automatically from the invoice date and type. You can type a different number; clear the box to use the auto-generated one.").strip() or auto_no

        # Milestones already billed in an earlier saved invoice of this project.
        earlier = {}
        _c = conn()
        for inv_row in _c.execute("SELECT invoice_no, description, items_json FROM invoices WHERE project_id=? ORDER BY id", (p['id'],)).fetchall():
            names = [i["description"] for i in json.loads(inv_row["items_json"]) if i.get("billed", True)] if inv_row["items_json"] else (inv_row["description"] or "").split("; ")
            for nm in names:
                earlier.setdefault(nm, inv_row["invoice_no"])
        _c.close()
        if selected_list:
            item_rows = [{
                "Sr. No.": m['milestone_no'], "Bill": m is selected_list[-1] and not custom_items, "Product Description": m['description'] or m['milestone_name'] or "",
                "HSN / SAC": m.get('hsn_code') or "998337", "Qty / %": f"{float(m['percentage'] or 0):.0f}%",
                "Basic Amount (₹)": float(m['amount'] or 0),
                "Earlier Invoice": earlier.get(m['description'] or m['milestone_name'] or "", "-"),
            } for m in selected_list]
        else:
            item_rows = []
        for n_extra, txt in enumerate(custom_items, 1):
            item_rows.append({"Sr. No.": len(item_rows) + 1, "Bill": True, "Product Description": txt, "HSN / SAC": "998337",
                              "Qty / %": "", "Basic Amount (₹)": 0.0, "Earlier Invoice": "-"})
        if not item_rows:
            item_rows = [{"Sr. No.": 1, "Bill": True, "Product Description": f"Consultancy services for {p['project_name']}",
                          "HSN / SAC": "998337", "Qty / %": "1", "Basic Amount (₹)": 0.0, "Earlier Invoice": "-"}]
        if custom_items or not selected_list:
            for row in item_rows[:-1]:
                row["Bill"] = row["Bill"] and False
            item_rows[-1]["Bill"] = True
        # The invoice lines follow the milestones selected above automatically (no table is shown).
        items_df = pd.DataFrame(item_rows)
        _s = lambda v, d="": d if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)
        items = [{
            "sr": n, "description": _s(r["Product Description"]), "hsn": _s(r["HSN / SAC"], "998337"),
            "qty": _s(r["Qty / %"]), "amount": 0.0 if pd.isna(r["Basic Amount (₹)"]) else float(r["Basic Amount (₹)"]),
            "billed": True if pd.isna(r["Bill"]) else bool(r["Bill"]),
        } for n, (_, r) in enumerate(items_df.iterrows(), 1) if _s(r["Product Description"]).strip() or not pd.isna(r["Basic Amount (₹)"])]
        basic = sum(i["amount"] for i in items if i["billed"])
        # the invoice amount is taken automatically from the selected milestone(s) set in Company Setup
        description = "; ".join(i["description"] for i in items)
        hsn = items[0]["hsn"] if items else "998337"
        qty = ", ".join(i["qty"] for i in items)

        pay_modes = ["Bank Transfer / Online", "Cheque", "Cash", "Other"]
        payment_mode = pay_modes[0]

        igst = basic*tax_rate/100 if tax_mode == "IGST" else 0.0
        cgst = basic*(tax_rate/2)/100 if tax_mode == "CGST + SGST" else 0.0
        sgst = cgst
        grand = basic + igst + cgst + sgst
        if tax_mode == "IGST":              # other states: IGST at the full rate
            a, b, d = st.columns(3)
            a.metric("Basic", inr(basic)); b.metric(f"IGST ({tax_rate:g}%)", inr(igst)); d.metric("Total", inr(grand))
        else:                               # Maharashtra: the rate is split half CGST, half SGST (18% = 9% + 9%)
            a, b, c2, d = st.columns(4)
            a.metric("Basic", inr(basic)); b.metric(f"CGST ({tax_rate / 2:g}%)", inr(cgst)); c2.metric(f"SGST ({tax_rate / 2:g}%)", inr(sgst)); d.metric("Total", inr(grand))

        invoice_payload = {
            "invoice_type": invoice_type, "invoice_no": invoice_no, "invoice_date": inv_date.strftime("%d.%m.%Y"),
            "hsn_code": hsn, "description": description, "qty_text": qty, "basic_amount": basic,
            "tax_mode": tax_mode, "tax_rate": tax_rate, "cgst": cgst, "sgst": sgst, "igst": igst,
            "grand_total": grand, "payment_mode": payment_mode, "items": items, "bill_state": bill_state,
        }
        # PDF lines use the same layout as the saved-invoice Report PDFs (all milestones, billed ones with amounts).
        invoice_payload["items"] = pdf_items_for({"items_json": json.dumps(items), "description": description, "hsn_code": hsn,
                                                  "qty_text": qty, "basic_amount": basic}, fetch_milestones(p['id']))
        def _save_invoice(project_id):
            try:
                c = conn(); c.execute("""INSERT INTO invoices(project_id,invoice_type,invoice_no,invoice_date,hsn_code,description,qty_text,basic_amount,tax_mode,tax_rate,cgst,sgst,igst,grand_total,payment_mode,created_at,items_json,bill_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (project_id,invoice_type,invoice_no,inv_date.isoformat(),hsn,description,qty,basic,tax_mode,tax_rate,cgst,sgst,igst,grand,payment_mode,datetime.now().isoformat(timespec='seconds'),json.dumps(items), bill_state)); c.commit(); c.close()
            except sqlite3.IntegrityError:
                st.error("Invoice number already exists. Change the number or date.")
                return False
            _sc = conn()
            _po = float((fetch_project(project_id) or {}).get("po_amount") or 0)
            for it in items:
                _a = float(it.get("amount") or 0)
                if it.get("billed") and _a > 0:
                    _g = round(_a * tax_rate / 100, 2)
                    _sc.execute("UPDATE milestones SET amount=?, percentage=?, gst_amount=?, scheduled_amount=?, balance_amount=? "
                                "WHERE project_id=? AND description=? AND COALESCE(amount,0)=0",
                                (_a, (_a / _po * 100) if _po else 0.0, _g, round(_a + _g, 2), round(_a + _g, 2), project_id, it.get("description")))
            _sc.commit(); _sc.close()
            st.session_state["_saved_invoice"] = {"no": invoice_no, "type": invoice_type, "project_id": project_id, "pdf": build_invoice_pdf(fetch_company(), fetch_project(project_id), invoice_payload)}
            return True

        def _project_values():
            """Project details to save: the Clients & Projects form if it holds this project (or a new one), else the saved details."""
            keys = ["client_name", "project_name", "billing_address", "site_address", "location", "state", "state_code",
                    "gstin", "pan", "po_no", "po_date", "po_amount", "vendor_id", "kind_attention"]
            f = {k: p.get(k) for k in keys}
            form_for = st.session_state.get("_form_project")
            if form_for == p['id'] or (st.session_state.get("_new_mode") and form_for is None):
                form = {k: st.session_state.get("pf_" + k) for k in keys}
                if str(form.get("client_name") or "").strip() and str(form.get("project_name") or "").strip():
                    f = form
            pod = f.get("po_date")
            pod = pod.isoformat() if isinstance(pod, date) else (pod or "")
            return (f["client_name"], f["project_name"], f["billing_address"] or "", f["site_address"] or "", f["location"] or "",
                    f["state"] or "", f["state_code"] or "", f["gstin"] or "", f["pan"] or "", f["po_no"] or "", pod,
                    float(f["po_amount"] or 0), f["vendor_id"] or "", f["kind_attention"] or "")

        if st.button("Save Invoice", type="primary", use_container_width=True,
                      help="Saves this invoice and then updates the whole selected project (its details and milestones stay saved)."):
            if _save_invoice(p['id']):
                cu = conn()
                cu.execute("""UPDATE projects SET client_name=?,project_name=?,billing_address=?,site_address=?,location=?,state=?,state_code=?,gstin=?,pan=?,po_no=?,po_date=?,po_amount=?,vendor_id=?,kind_attention=? WHERE id=?""", _project_values() + (p['id'],))
                cu.commit(); cu.close()
                st.session_state["_ci_flash"] = "Invoice saved and the selected project updated."
                st.rerun()
        _ci_flash = st.session_state.pop("_ci_flash", None)
        if _ci_flash:
            st.success(_ci_flash)
        _last = st.session_state.get("_saved_invoice")
        if _last and _last.get("project_id") == p['id']:
            render_invoice_reports(p, only_type=invoice_type, pdf_only=True)

elif page == "Report":
    st.markdown("## Report")
    render_yearly_report()

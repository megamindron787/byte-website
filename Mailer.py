"""
Mailer.py — Send HTML confirmation email with embedded ticket QR code
"""

import smtplib, os, io, qrcode
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.image     import MIMEImage
from dotenv               import load_dotenv

FROM_NAME = "DevSphere 2025"

DAY_INFO = {
    1: ("Jul 26", "Ignition"),
    2: ("Jul 27", "Community"),
    3: ("Jul 28", "Build Mode"),
    4: ("Jul 29", "Scale Up"),
    5: ("Jul 30", "Finale"),
}


def _make_qr_png(data: str) -> bytes:
    qr = qrcode.QRCode(
        version=3,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1A1208", back_color="#FAF7F0")
    buf = io.BytesIO()
    img.save(buf, kind="PNG")
    return buf.getvalue()


def _day_badges_html(days_str: str, ticket_type: str) -> str:
    badges = []
    for d in days_str.split(","):
        d = d.strip()
        if not d.isdigit():
            continue
        info = DAY_INFO.get(int(d))
        if not info:
            continue
        color = "#1A5C3A" if ticket_type == "week" else "#B5341A"
        bg    = "rgba(26,92,58,.12)" if ticket_type == "week" else "rgba(181,52,26,.10)"
        badges.append(
            f'<span style="display:inline-block;margin:3px 4px;padding:4px 10px;'
            f'border-radius:3px;background:{bg};border:1.5px solid {color};'
            f'color:{color};font-family:\'Courier New\',monospace;font-size:11px;'
            f'letter-spacing:.06em;text-transform:uppercase;">'
            f'{info[0]} · {info[1]}</span>'
        )
    return "".join(badges)


def send_confirmation(booking: dict):
    # ── Load .env fresh every time so credentials are always current ──
    load_dotenv(override=True)
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    REPLY_TO  = os.getenv("REPLY_TO", SMTP_USER)

    # ── Debug: print what we loaded so you can verify in terminal ─────
    print(f"[MAIL] SMTP_USER={SMTP_USER!r}  SMTP_PASS={'*'*len(SMTP_PASS) if SMTP_PASS else '(empty)'}")

    if not SMTP_USER or not SMTP_PASS:
        raise ValueError("SMTP_USER or SMTP_PASS is empty — check your .env file")

    name        = booking["name"]
    email       = booking["email"]
    phone       = booking["phone"]
    college     = booking.get("college") or "—"
    year        = booking.get("year_of_study") or "—"
    days        = booking["days"]
    ticket_type = booking["ticket_type"]
    amount      = booking["amount"]
    token       = booking["ticket_token"]
    payment_id  = booking.get("razorpay_payment_id", "—")

    qr_png     = _make_qr_png(token)
    day_badges = _day_badges_html(days, ticket_type)
    pass_label = "All-Week Pass" if ticket_type == "week" else "Day Pass"
    amount_fmt = f"₹{amount:,}"

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#EDE7D8;font-family:'Nunito',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EDE7D8;padding:32px 0;">
<tr><td align="center">
  <table width="600" cellpadding="0" cellspacing="0"
         style="background:#FAF7F0;border:2px solid rgba(80,55,30,.28);border-radius:12px;overflow:hidden;box-shadow:4px 4px 0 rgba(0,0,0,.10);">
    <tr>
      <td style="background:#B5341A;padding:28px 36px;text-align:center;">
        <p style="margin:0;font-family:'Courier New',monospace;font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:rgba(250,247,240,.7);">★ You're Registered ★</p>
        <h1 style="margin:8px 0 4px;font-family:Georgia,serif;font-style:italic;font-size:38px;font-weight:900;color:#FAF7F0;">DevSphere<span style="color:#FAD08A;">.</span></h1>
        <p style="margin:0;font-family:'Courier New',monospace;font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:rgba(250,247,240,.75);">PVPIT Campus · Pune · July 26–30, 2025</p>
      </td>
    </tr>
    <tr>
      <td style="padding:32px 36px;">
        <p style="margin:0 0 6px;font-family:'Courier New',monospace;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#B5341A;">▸ Hey {name},</p>
        <h2 style="margin:0 0 16px;font-family:Georgia,serif;font-style:italic;font-size:26px;color:#1A1208;">Your ticket is confirmed!</h2>
        <p style="margin:0 0 24px;font-size:15px;color:#7A6A50;line-height:1.65;">We can't wait to see you at DevSphere 2025. Your unique e-ticket QR code is below — please present it at the entrance.</p>
        <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="background:#F5F0E8;border:2px dashed rgba(80,55,30,.30);border-radius:8px;padding:24px;">
            <img src="cid:ticket_qr" width="180" height="180" alt="Your Ticket QR" style="display:block;border-radius:6px;" />
            <p style="margin:12px 0 4px;font-family:'Courier New',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#7A6A50;">Ticket Token</p>
            <p style="margin:0;font-family:'Courier New',monospace;font-size:13px;font-weight:700;color:#1A1208;letter-spacing:.08em;">{token}</p>
          </td>
        </tr>
        </table>
        <p style="margin:24px 0 8px;font-family:'Courier New',monospace;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#B5341A;">▸ Your Days</p>
        <div style="margin-bottom:24px;">{day_badges}</div>
        <p style="margin:0 0 8px;font-family:'Courier New',monospace;font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#B5341A;">▸ Booking Details</p>
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1.5px solid rgba(80,55,30,.20);border-radius:6px;overflow:hidden;">
          {''.join([
            f'<tr><td style="padding:9px 14px;font-family:\'Courier New\',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#7A6A50;width:40%;background:#F5F0E8;">{label}</td><td style="padding:9px 14px;font-size:14px;color:#1A1208;">{value}</td></tr>'
            for label, value in [
                ("Name", name), ("Email", email), ("Phone", phone),
                ("College", college), ("Year", year),
                ("Pass Type", pass_label), ("Amount Paid", amount_fmt), ("Payment ID", payment_id),
            ]
          ])}
        </table>
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
        <tr>
          <td style="background:rgba(26,92,58,.08);border:1.5px solid rgba(26,92,58,.25);border-radius:6px;padding:14px 18px;">
            <p style="margin:0;font-family:'Courier New',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#1A5C3A;">📌 Reminder</p>
            <ul style="margin:8px 0 0;padding-left:18px;font-size:13px;color:#3D2E18;line-height:1.8;">
              <li>Bring a valid college/government ID to the venue.</li>
              <li>Entry is only allowed on the days you've registered for.</li>
              <li>This ticket is non-transferable and non-refundable.</li>
              <li>Gates open at 9:00 AM each day.</li>
            </ul>
          </td>
        </tr>
        </table>
      </td>
    </tr>
    <tr>
      <td style="background:#EDE7D8;border-top:2px solid rgba(80,55,30,.18);padding:18px 36px;text-align:center;">
        <p style="margin:0;font-family:'Courier New',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#7A6A50;">© 2025 DevSphere · PVPIT, Pune · Non-refundable · Student ID required</p>
      </td>
    </tr>
  </table>
</td></tr>
</table>
</body>
</html>
"""

    msg            = MIMEMultipart("related")
    msg["Subject"] = f"🎟 Your DevSphere 2025 Ticket — {token}"
    msg["From"]    = f"{FROM_NAME} <{SMTP_USER}>"
    msg["To"]      = email
    msg["Reply-To"]= REPLY_TO

    msg.attach(MIMEText(html, "html", "utf-8"))

    qr_part = MIMEImage(qr_png, _subtype="png")
    qr_part["Content-ID"]          = "<ticket_qr>"
    qr_part["Content-Disposition"] = "inline; filename=ticket_qr.png"
    msg.attach(qr_part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.sendmail(SMTP_USER, email, msg.as_bytes())

    print(f"[MAIL] Confirmation sent → {email}  token={token}")
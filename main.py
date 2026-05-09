"""
main.py — DevSphere 2025 Flask backend
  GET  /              → index.html
  GET  /checkout      → checkout.html
  POST /api/create-order   → create Razorpay order, store booking (paid=False)
  POST /api/verify-payment → verify HMAC, mark paid, send confirmation email
  GET  /api/ticket/<token> → verify ticket token (for venue scanning)
  GET  /admin/bookings     → simple admin list (protect in production!)
"""
 
import os, uuid, hmac, hashlib, threading
from flask      import Flask, render_template, request, jsonify, abort
from dotenv     import load_dotenv
import razorpay
 
from database import init_db, create_booking, get_booking_by_order, mark_paid, \
                     get_all_bookings, get_booking_by_token,get_stats
from Mailer   import send_confirmation
 
load_dotenv()
 
app = Flask(__name__)
 
# ── Razorpay client (uses secret key — never sent to browser) ─────────────────
RZP_KEY_ID     = os.getenv("RAZORPAY_KEY_ID",     "")
RZP_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
rzp_client     = razorpay.Client(auth=(RZP_KEY_ID, RZP_KEY_SECRET))
 
# ── Initialise DB on startup ──────────────────────────────────────────────────
init_db()
 
 
# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")
 
 
@app.route("/checkout")
def checkout():
    return render_template("checkout.html")
 
 
# ── Ticket verification page (scanned at venue entrance) ──────────────────────
@app.route("/ticket/<token>")
def verify_ticket_page(token):
    booking = get_booking_by_token(token)
    if not booking or not booking["paid"]:
        abort(404)
    return render_template("ticket_valid.html", booking=dict(booking))
 
 
# =============================================================================
#  STEP 1 — Create Razorpay order
# =============================================================================
@app.route("/api/create-order", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
 
    name         = (data.get("name")        or "").strip()
    email        = (data.get("email")       or "").strip()
    phone        = (data.get("phone")       or "").strip()
    college      = (data.get("college")     or "").strip()
    year         = (data.get("year")        or "").strip()
    days_list    =  data.get("days",        [])
    ticket_type  = (data.get("ticket_type") or "pick").strip()
    amount_inr   =  int(data.get("amount",  0))
 
    if not (name and email and phone):
        return jsonify(error="Name, email and phone are required."), 400
    if not (1 <= amount_inr <= 10_000):
        return jsonify(error="Invalid amount."), 400
 
    days_str = ",".join(str(d) for d in sorted(set(int(x) for x in days_list if 1 <= int(x) <= 5)))
    if not days_str:
        return jsonify(error="No valid days selected."), 400
 
    try:
        rp_order = rzp_client.order.create({
            "amount":   amount_inr * 100,
            "currency": "INR",
            "payment_capture": 1,
            "notes": {"event": "DevSphere 2025", "days": days_str, "ticket_type": ticket_type}
        })
    except Exception as e:
        app.logger.error("Razorpay order creation failed: %s", e)
        return jsonify(error="Could not create order. Please try again."), 502
 
    ticket_token = "DS25-" + uuid.uuid4().hex[:8].upper()
 
    create_booking(
        name=name, email=email, phone=phone,
        college=college, year_of_study=year,
        days=days_str, ticket_type=ticket_type,
        amount=amount_inr,
        razorpay_order_id=rp_order["id"],
        ticket_token=ticket_token,
    )
 
    return jsonify(
        order_id = rp_order["id"],
        amount   = rp_order["amount"],
        currency = rp_order["currency"],
        key_id   = RZP_KEY_ID,
    )
 
 
# =============================================================================
#  STEP 2 — Verify payment & send confirmation email
# =============================================================================
@app.route("/api/verify-payment", methods=["POST"])
def verify_payment():
    data = request.get_json(silent=True) or {}
 
    order_id   = data.get("razorpay_order_id",  "")
    payment_id = data.get("razorpay_payment_id", "")
    signature  = data.get("razorpay_signature",  "")
 
    if not (order_id and payment_id and signature):
        return jsonify(success=False, error="Missing payment fields."), 400
 
    expected_sig = hmac.new(
        RZP_KEY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
 
    if not hmac.compare_digest(expected_sig, signature):
        app.logger.warning("Signature mismatch for order %s", order_id)
        return jsonify(success=False, error="Signature verification failed."), 400
 
    booking = get_booking_by_order(order_id)
    if not booking:
        return jsonify(success=False, error="Booking not found."), 404
 
    if booking["paid"]:
        return jsonify(success=True, ticket_token=booking["ticket_token"])
 
    mark_paid(order_id, payment_id, signature)
 
    booking_dict = dict(booking)
    booking_dict["razorpay_payment_id"] = payment_id
 
    def _send():
        try:
            send_confirmation(booking_dict)
        except Exception as e:
            app.logger.error("Email send failed for %s: %s", booking_dict["email"], e)
 
    threading.Thread(target=_send, daemon=True).start()
 
    return jsonify(success=True, ticket_token=booking["ticket_token"])
 
 
# =============================================================================
#  Ticket verification API  GET /api/ticket/<token>
# =============================================================================
@app.route("/api/ticket/<token>")
def verify_ticket_api(token):
    booking = get_booking_by_token(token)
    if not booking:
        return jsonify(valid=False, reason="Token not found."), 404
    if not booking["paid"]:
        return jsonify(valid=False, reason="Payment not confirmed."), 403
    return jsonify(
        valid=True, name=booking["name"],
        days=booking["days"], ticket_type=booking["ticket_type"],
        ticket_token=booking["ticket_token"],
    )
 
 
# =============================================================================
#  Admin  GET /admin/bookings  (⚠️ protect with auth in production)
# =============================================================================
@app.route("/admin/bookings")
def admin_bookings():
    rows = get_all_bookings()
    return jsonify([dict(r) for r in rows])
 
 

# =============================================================================
#  Admin dashboard  GET /admin
#  Protected by ADMIN_PASSWORD in .env
# =============================================================================
from functools import wraps
from flask import Response

def check_auth(username, password):
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "devsphere2025")
    return username == admin_user and password == admin_pass

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Login required.", 401,
                {"WWW-Authenticate": 'Basic realm="DevSphere Admin"'}
            )
        return f(*args, **kwargs)
    return decorated

@app.route("/admin")
@require_auth
def admin_dashboard():
    return render_template("admin.html",
        stats=get_stats(),
        bookings=[dict(r) for r in get_all_bookings()]
    )

if __name__ == "__main__":
    app.run(debug=True)
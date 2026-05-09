"""
database.py — SQLite setup & helpers for DevSphere 2025 bookings
"""

import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "devsphere.db")


def get_db():
    """Return a connection with row_factory so columns are accessible by name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist yet. Call once at app startup."""
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS bookings (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Attendee info (from checkout form)
            name                TEXT    NOT NULL,
            email               TEXT    NOT NULL,
            phone               TEXT    NOT NULL,
            college             TEXT,
            year_of_study       TEXT,

            -- Ticket details
            days                TEXT    NOT NULL,   -- e.g. "1,3,5"
            ticket_type         TEXT    NOT NULL,   -- "pick" | "week"
            amount              INTEGER NOT NULL,   -- INR (e.g. 1500)

            -- Razorpay identifiers
            razorpay_order_id   TEXT    UNIQUE,
            razorpay_payment_id TEXT,
            razorpay_signature  TEXT,

            -- Unique ticket QR token (generated on booking creation)
            ticket_token        TEXT    UNIQUE NOT NULL,

            -- Payment status
            paid                INTEGER NOT NULL DEFAULT 0,   -- 0 = false, 1 = true

            -- Timestamps (UTC)
            created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
            paid_at             TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_bookings_order   ON bookings(razorpay_order_id);
        CREATE INDEX IF NOT EXISTS idx_bookings_email   ON bookings(email);
        CREATE INDEX IF NOT EXISTS idx_bookings_token   ON bookings(ticket_token);
        """)
    print(f"[DB] Initialised → {DB_PATH}")


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def create_booking(name, email, phone, college, year_of_study,
                   days, ticket_type, amount, razorpay_order_id, ticket_token):
    """Insert a new booking (paid=False) and return its id."""
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO bookings
               (name, email, phone, college, year_of_study,
                days, ticket_type, amount, razorpay_order_id, ticket_token)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (name, email, phone, college, year_of_study,
             days, ticket_type, amount, razorpay_order_id, ticket_token)
        )
        return cur.lastrowid


def get_booking_by_order(razorpay_order_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE razorpay_order_id = ?",
            (razorpay_order_id,)
        ).fetchone()


def mark_paid(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """Flip paid=1 and record the Razorpay payment & signature."""
    with get_db() as conn:
        conn.execute(
            """UPDATE bookings
               SET paid=1, razorpay_payment_id=?, razorpay_signature=?,
                   paid_at=datetime('now')
               WHERE razorpay_order_id=?""",
            (razorpay_payment_id, razorpay_signature, razorpay_order_id)
        )


def get_all_bookings():
    """Return all bookings — useful for an admin view."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM bookings ORDER BY created_at DESC"
        ).fetchall()


def get_booking_by_token(token):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE ticket_token = ?", (token,)
        ).fetchone()

# ── Admin helpers ─────────────────────────────────────────────────────────────

def get_stats():
    """Return summary stats for the admin dashboard."""
    with get_db() as conn:
        total      = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        paid       = conn.execute("SELECT COUNT(*) FROM bookings WHERE paid=1").fetchone()[0]
        unpaid     = total - paid
        revenue    = conn.execute("SELECT COALESCE(SUM(amount),0) FROM bookings WHERE paid=1").fetchone()[0]
        week_pass  = conn.execute("SELECT COUNT(*) FROM bookings WHERE ticket_type='week' AND paid=1").fetchone()[0]
        day_pass   = conn.execute("SELECT COUNT(*) FROM bookings WHERE ticket_type='pick' AND paid=1").fetchone()[0]

        # Per-day attendance (paid only)
        day_rows = conn.execute(
            "SELECT days FROM bookings WHERE paid=1"
        ).fetchall()

        day_counts = {1:0, 2:0, 3:0, 4:0, 5:0}
        for row in day_rows:
            for d in row["days"].split(","):
                d = d.strip()
                if d.isdigit() and 1 <= int(d) <= 5:
                    day_counts[int(d)] += 1

        return {
            "total": total, "paid": paid, "unpaid": unpaid,
            "revenue": revenue, "week_pass": week_pass,
            "day_pass": day_pass, "day_counts": day_counts
        }
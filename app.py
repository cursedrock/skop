from decimal import Decimal, InvalidOperation
import os
import stripe
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Load environment variables for Railway
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_MAX_NETWORK_RETRIES = int(os.environ.get("STRIPE_MAX_NETWORK_RETRIES", "2"))

# Configure Stripe
stripe.api_key = STRIPE_SECRET_KEY
stripe.max_network_retries = STRIPE_MAX_NETWORK_RETRIES

def _format_amount_from_cents(amount_cents: int) -> str:
    amount = Decimal(amount_cents) / Decimal("100")
    return f"{amount:.2f}"

def _parse_amount_to_cents(amount_raw: str) -> int:
    try:
        amount = Decimal(amount_raw).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid amount.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    return int(amount * 100)

def _status_from_card_error(error: stripe.error.CardError) -> str:
    code = getattr(error, "code", None) or getattr(error.error, "code", None)
    if code == "incorrect_cvc":
        return "live"
    if code == "insufficient_funds":
        return "live"
    return "false"

@app.get("/")
def index():
    return render_template(
        "index.html",
        publishable_key=STRIPE_PUBLISHABLE_KEY,
    )

@app.post("/create-payment-intent")
def create_payment_intent():
    data = request.get_json(silent=True) or {}
    amount_raw = data.get("amount")
    payment_method_id = data.get("payment_method_id")
    email = data.get("email")

    if not STRIPE_SECRET_KEY:
        return jsonify({"error": "Stripe secret key not set."}), 500
    if not payment_method_id:
        return jsonify({"error": "Payment method is required."}), 400

    try:
        amount_cents = _parse_amount_to_cents(amount_raw)
    except ValueError as exc:
        return jsonify({"status": "false", "message": str(exc)}), 400

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            payment_method=payment_method_id,
            receipt_email=email or None,
            confirm=True,
        )
        if intent.status == "requires_action":
            return jsonify(
                {
                    "status": "requires_action",
                    "payment_intent_id": intent.id,
                    "client_secret": intent.client_secret,
                }
            )
        return jsonify(
            {
                "status": "true",
                "message": f"Your donation successful ${_format_amount_from_cents(amount_cents)}",
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
            }
        )
    except stripe.error.CardError as exc:
        return (
            jsonify({"status": _status_from_card_error(exc), "message": exc.user_message}),
            402,
        )
    except Exception:
        return (
            jsonify({"status": "false", "message": "Unable to create payment intent."}),
            500,
        )

@app.post("/confirm-payment-intent")
def confirm_payment_intent():
    data = request.get_json(silent=True) or {}
    payment_intent_id = data.get("payment_intent_id")

    if not payment_intent_id:
        return jsonify({"status": "false", "message": "Payment intent id is required."}), 400

    try:
        intent = stripe.PaymentIntent.confirm(payment_intent_id)
        if intent.status == "requires_action":
            return jsonify(
                {
                    "status": "requires_action",
                    "payment_intent_id": intent.id,
                    "client_secret": intent.client_secret,
                }
            )
        return jsonify(
            {
                "status": "true",
                "message": f"Your donation successful ${_format_amount_from_cents(intent.amount)}",
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
            }
        )
    except stripe.error.CardError as exc:
        return (
            jsonify({"status": _status_from_card_error(exc), "message": exc.user_message}),
            402,
        )
    except Exception:
        return (
            jsonify({"status": "false", "message": "Unable to confirm payment intent."}),
            500,
        )

# Railway needs this at the end
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
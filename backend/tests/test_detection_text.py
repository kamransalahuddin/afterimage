"""Text-level detectors (no OCR involved)."""

from __future__ import annotations

import pytest

from app.detection.pii import card_brand, iban_valid, luhn_valid
from app.detection.scanner import scan_text
from app.detection.secrets import shannon_entropy
from tests.fixtures.synthetic import FAKE_AWS_KEY, fake_github_token


def found(text: str, use_entities: bool = False) -> list[tuple[str, str, str]]:
    return [(m.category, m.label, text[m.start:m.end]) for m in scan_text(text, use_entities=use_entities)]


def categories(text: str) -> set[str]:
    return {c for c, _, _ in found(text)}


# ---------------------------------------------------------------- email

@pytest.mark.parametrize("email", ["jordan.avery@example.com", "a+tag@sub.example.org", "x_y@example.co.uk"])
def test_email_detected(email):
    hits = found(f"reach me at {email}, thanks")
    assert ("email", "Email address", email) in hits


@pytest.mark.parametrize("text", ["icon@2x.png", "foo@bar", "not an email: a@b.c", "user@@example.com"])
def test_email_false_positives(text):
    assert "email" not in categories(text)


# ---------------------------------------------------------------- cards

def test_luhn():
    assert luhn_valid("4242424242424242")
    assert luhn_valid("378282246310005")
    assert not luhn_valid("4242424242424241")
    assert not luhn_valid("1")


def test_card_brand():
    assert card_brand("4242424242424242") == "Visa"
    assert card_brand("5555555555554444") == "Mastercard"
    assert card_brand("378282246310005") == "American Express"
    assert card_brand("6011111111111117") == "Discover"
    assert card_brand("9999999999999995") is None


@pytest.mark.parametrize("card", ["4242 4242 4242 4242", "5555-5555-5555-4444", "378282246310005"])
def test_card_detected(card):
    hits = found(f"Card: {card}")
    assert any(c == "card" and v == card for c, _, v in hits), hits


@pytest.mark.parametrize("text", [
    "4242 4242 4242 4241",          # Luhn fails
    "0000 0000 0000 0000",          # single repeated digit
    "Order 1234567890123456",       # Luhn fails
    "9999 9999 9999 9995",          # Luhn ok but unknown network
    "4242-4242 4242-4242",          # inconsistent separators
])
def test_card_false_positives(text):
    assert "card" not in categories(text)


def test_card_masked_preview_keeps_only_last_four():
    m = next(m for m in scan_text("4242 4242 4242 4242", use_entities=False) if m.category == "card")
    assert m.masked.endswith("4242") and "4242 4242" not in m.masked


# ---------------------------------------------------------------- phones

@pytest.mark.parametrize("phone", ["(312) 555-0142", "+1 312-555-0142", "312.555.0142"])
def test_phone_detected(phone):
    assert any(c == "phone" for c, _, _ in found(f"Phone: {phone}"))


def test_phone_context_boosts_confidence():
    with_ctx = next(m for m in scan_text("Call me: (312) 555-0142", use_entities=False) if m.category == "phone")
    without = next(m for m in scan_text("x (312) 555-0142", use_entities=False) if m.category == "phone")
    assert with_ctx.confidence > without.confidence


def test_phone_false_positive():
    assert "phone" not in categories("Version 2024.11.03 build 12")


# ---------------------------------------------------------------- secrets

def test_aws_key():
    assert ("secret", "AWS access key ID", FAKE_AWS_KEY) in found(f"key id {FAKE_AWS_KEY}")


def test_github_token():
    tok = fake_github_token()
    assert ("secret", "GitHub token", tok) in found(f"export GH={tok}")


def test_stripe_and_slack_and_google():
    stripe = "sk_" + "live_" + "a1B2c3D4e5F6g7H8i9J0k1L2"
    slack = "xox" + "b-123456789012-abcdefABCDEF"
    google = "AIza" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q"
    labels = {lab for _, lab, _ in found(f"{stripe} {slack} {google}")}
    assert {"Stripe secret key", "Slack token", "Google API key"} <= labels


def test_jwt_detected_and_validated():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    m = next(m for m in scan_text(f"Authorization: {jwt}", use_entities=False) if m.label == "JSON Web Token")
    assert m.confidence >= 0.9


def test_bearer_token():
    assert any(lab == "Bearer token" for _, lab, _ in found("Authorization: Bearer abcDEF1234567890ghijKLMN"))


def test_private_key_block_spans_lines():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Z3VS5JJcds3xfn\n-----END RSA PRIVATE KEY-----"
    hits = found(f"key:\n{pem}\ndone")
    assert any(lab == "Private key" and v == pem for _, lab, v in hits)


def test_credentials_in_url():
    hits = found("DATABASE_URL=postgres://admin:s3cr3tP4ss@db.internal:5432/app")
    assert any(lab == "Credentials in URL" and v == "admin:s3cr3tP4ss" for _, lab, v in hits)


def test_contextual_assignment():
    hits = found('api_key = "Zk29Qw81LmNx47PpRt03"')
    assert any(c == "secret" and v == "Zk29Qw81LmNx47PpRt03" for c, _, v in hits)


def test_password_assignment():
    assert any(lab == "Password" for _, lab, _ in found("password: hunter2!x"))


@pytest.mark.parametrize("text", [
    "tokenization is a technique",                         # keyword as part of prose
    "commit 3f786850e387550fdab836ed7e6dc881de23001b",     # random hex without context
    "id 123e4567-e89b-12d3-a456-426614174000",             # UUID without context
    "password: ********",                                 # placeholder
    "API_KEY=${API_KEY}",                                 # reference, not a value
    "api_key = os.environ.get",                           # reference
    "secret: required",                                   # plain word
])
def test_secret_false_positives(text):
    assert "secret" not in categories(text), found(text)


def test_entropy():
    assert shannon_entropy("aaaa") == 0
    assert shannon_entropy("Zk29Qw81LmNx47PpRt03") > 3.5


# ---------------------------------------------------------------- other identifiers

def test_ssn_iban_ip_gps():
    text = "SSN 123-45-6789 IBAN GB82 WEST 1234 5698 7654 32 from 203.0.113.9 at 41.8781, -87.6298"
    labels = {lab for _, lab, _ in found(text)}
    assert {"Social Security number", "Bank account (IBAN)", "IP address", "GPS coordinates"} <= labels


def test_invalid_ssn_and_iban_rejected():
    assert "Social Security number" not in {lab for _, lab, _ in found("000-12-3456 and 666-12-3456")}
    assert not iban_valid("GB00 WEST 1234 5698 7654 32")


def test_version_number_is_not_ip():
    assert "IP address" not in {lab for _, lab, _ in found("Chrome version 1.2.3.4")}


def test_address():
    hits = found("Ship to 1200 Lakeshore Drive, Chicago, IL 60611 by Friday")
    assert any(c == "address" and "1200 Lakeshore Drive" in v and "60611" in v for c, _, v in hits)


def test_address_false_positive():
    assert "address" not in categories("We shipped 3 new features this week")


def test_person_name_via_presidio():
    from app.detection import entities

    if not entities.available():
        pytest.skip("Presidio / spaCy model not installed")
    hits = found("The contract was signed by Jordan Avery yesterday.", use_entities=True)
    assert any(lab == "Person name" for _, lab, _ in hits)
    # Names are uncertain: they must never be auto-selected.
    m = next(m for m in scan_text("Signed by Jordan Avery.", use_entities=True) if m.label == "Person name")
    assert m.confidence < 0.6 + 1e-9


def test_overlap_resolution_prefers_secret():
    hits = found("postgres://user:longpassword1@example.com/db")
    cats = [c for c, _, _ in hits]
    assert "secret" in cats

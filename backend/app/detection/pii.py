"""Structured personal-information detectors.

Each detector returns `TextMatch`es. They favour precision: candidates must
pass a structural validator (Luhn, IBAN mod-97, `ipaddress`, `phonenumbers`
validity, coordinate ranges) before being reported.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable

import phonenumbers

from app.detection import masking
from app.detection.types import ADDRESS, CARD, EMAIL, OTHER, PHONE, TextMatch

# ---------------------------------------------------------------- email

_EMAIL_RE = re.compile(
    r"(?<![\w.+%-])([A-Za-z0-9][A-Za-z0-9._%+-]{0,63})@((?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24})(?![\w-])"
)
_FILE_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "pdf", "js", "ts", "css", "map", "json"}


def find_emails(text: str) -> Iterable[TextMatch]:
    for m in _EMAIL_RE.finditer(text):
        local, domain = m.group(1), m.group(2)
        tld = domain.rsplit(".", 1)[-1].lower()
        if ".." in local or local.endswith(".") or tld in _FILE_TLDS:
            continue
        yield TextMatch(m.start(), m.end(), EMAIL, "Email address", 0.95, masking.mask_email(m.group(0)))


# ---------------------------------------------------------------- credit cards


def luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 2:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_brand(number: str) -> str | None:
    n, length = number, len(number)
    if n.startswith("4") and length in (13, 16, 19):
        return "Visa"
    if length == 16 and (51 <= int(n[:2]) <= 55 or 2221 <= int(n[:4]) <= 2720):
        return "Mastercard"
    if length == 15 and n[:2] in ("34", "37"):
        return "American Express"
    if 16 <= length <= 19 and (n.startswith(("6011", "65", "622")) or 644 <= int(n[:3]) <= 649):
        return "Discover"
    if length == 14 and (300 <= int(n[:3]) <= 305 or n[:2] in ("36", "38")):
        return "Diners Club"
    if 16 <= length <= 19 and 3528 <= int(n[:4]) <= 3589:
        return "JCB"
    return None


_CARD_RE = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")


def find_cards(text: str) -> Iterable[TextMatch]:
    for m in _CARD_RE.finditer(text):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
            continue
        # Separators, if present, must be consistent (avoids gluing unrelated numbers).
        seps = set(re.findall(r"[ -]", raw))
        if len(seps) > 1:
            continue
        if not luhn_valid(digits):
            continue
        brand = card_brand(digits)
        if brand is None:
            continue
        yield TextMatch(m.start(), m.end(), CARD, f"{brand} card", 0.95, masking.mask_digits_tail(digits, 4))


# ---------------------------------------------------------------- phone numbers

_PHONE_CONTEXT = re.compile(r"(?i)\b(phone|tel|telephone|mobile|cell|call|fax|contact|whatsapp|sms)\b")


def find_phones(text: str, region: str = "US") -> Iterable[TextMatch]:
    matcher = phonenumbers.PhoneNumberMatcher(text, region, leniency=phonenumbers.Leniency.VALID)
    for pm in matcher:
        raw = pm.raw_string
        digits = re.sub(r"\D", "", raw)
        formatted = bool(re.search(r"[\s().+-]", raw))
        context = bool(_PHONE_CONTEXT.search(text[max(0, pm.start - 40):pm.start]))
        if context:
            conf = 0.9
        elif formatted:
            conf = 0.8
        else:
            conf = 0.45  # a bare run of digits might just be an identifier
        yield TextMatch(pm.start, pm.end, PHONE, "Phone number", conf, f"{masking.DOT * 3} {masking.DOT * 3} {masking.DOT * 2}{digits[-2:]}")


# ---------------------------------------------------------------- IP addresses

_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{1,4}(?![\w:])")
_VERSION_CTX = re.compile(r"(?i)(version|ver\.?|v|build|release)\s*$")


def find_ips(text: str) -> Iterable[TextMatch]:
    for m in _IPV4_RE.finditer(text):
        if _VERSION_CTX.search(text[max(0, m.start() - 10):m.start()]):
            continue
        try:
            ip = ipaddress.IPv4Address(m.group(0))
        except ValueError:
            continue
        conf = 0.5 if (ip.is_private or ip.is_loopback or ip.is_reserved) else 0.75
        yield TextMatch(m.start(), m.end(), OTHER, "IP address", conf, masking.mask_generic(m.group(0)))
    for m in _IPV6_RE.finditer(text):
        s = m.group(0)
        if s.count(":") < 3:
            continue
        try:
            ip6 = ipaddress.IPv6Address(s)
        except ValueError:
            continue
        if ip6.is_loopback or ip6.is_unspecified:
            continue
        yield TextMatch(m.start(), m.end(), OTHER, "IP address", 0.7, masking.mask_generic(s))


# ---------------------------------------------------------------- GPS coordinates

_DECIMAL_COORD_RE = re.compile(
    r"(?<![\d.])([-+]?\d{1,2}\.\d{4,})°?\s*([NS])?\s*[,; ]\s*([-+]?\d{1,3}\.\d{4,})°?\s*([EW])?(?![\d.])"
)
_DMS_RE = re.compile(
    r"\d{1,2}\s*°\s*\d{1,2}\s*['′]\s*(?:\d{1,2}(?:\.\d+)?\s*[\"″]\s*)?[NS][,;\s]+\d{1,3}\s*°\s*\d{1,2}\s*['′]\s*(?:\d{1,2}(?:\.\d+)?\s*[\"″]\s*)?[EW]"
)


def find_coordinates(text: str) -> Iterable[TextMatch]:
    for m in _DECIMAL_COORD_RE.finditer(text):
        lat, lon = float(m.group(1)), float(m.group(3))
        if abs(lat) <= 90 and abs(lon) <= 180 and not (lat == 0 and lon == 0):
            yield TextMatch(m.start(), m.end(), OTHER, "GPS coordinates", 0.8, masking.mask_generic(m.group(0)))
    for m in _DMS_RE.finditer(text):
        yield TextMatch(m.start(), m.end(), OTHER, "GPS coordinates", 0.85, masking.mask_generic(m.group(0)))


# ---------------------------------------------------------------- government / bank identifiers

_SSN_RE = re.compile(r"(?<![\d-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\d-])")
_SSN_CTX = re.compile(r"(?i)(ssn|social\s+security|tax\s*id|tin)\b")
_IBAN_RE = re.compile(r"\b([A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?)\b")


def iban_valid(value: str) -> bool:
    s = value.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    rearranged = s[4:] + s[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


def find_government_ids(text: str) -> Iterable[TextMatch]:
    for m in _SSN_RE.finditer(text):
        ctx = bool(_SSN_CTX.search(text[max(0, m.start() - 40):m.start()]))
        yield TextMatch(m.start(), m.end(), OTHER, "Social Security number", 0.95 if ctx else 0.7, f"{masking.DOT * 3}-{masking.DOT * 2}-{m.group(0)[-4:]}")
    for m in _IBAN_RE.finditer(text):
        if iban_valid(m.group(1)):
            yield TextMatch(m.start(1), m.end(1), OTHER, "Bank account (IBAN)", 0.9, masking.mask_digits_tail(m.group(1), 4))


# ---------------------------------------------------------------- postal addresses (US-centric)

_SUFFIX = (
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl|"
    r"Terrace|Ter|Parkway|Pkwy|Circle|Cir|Highway|Hwy|Square|Sq|Trail|Trl|Alley|Plaza)"
)
_STATES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|"
    "NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)
_STREET_RE = re.compile(
    rf"\b\d{{1,6}}[A-Z]?[ ]+(?:[NSEW]\.?[ ]+)?(?:[A-Z0-9][A-Za-z0-9.'-]*[ ]+){{1,4}}{_SUFFIX}\b\.?"
    rf"(?:,?[ ]+(?:Apt|Apartment|Suite|Ste|Unit|Fl|Floor|#)\.?[ ]*#?[\w-]+)?"
)
_CITY_LINE_RE = re.compile(rf"\b[A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'-]+){{0,3}},\s*(?:{_STATES})\s+\d{{5}}(?:-\d{{4}})?\b")
_PO_BOX_RE = re.compile(r"\bP\.?\s?O\.?\s+Box\s+\d{1,6}\b", re.IGNORECASE)


def find_addresses(text: str) -> Iterable[TextMatch]:
    streets = list(_STREET_RE.finditer(text))
    cities = list(_CITY_LINE_RE.finditer(text))
    used_cities: set[int] = set()
    for s in streets:
        end, conf = s.end(), 0.75
        # Join with a city/state/ZIP that follows on the same or next line.
        for i, c in enumerate(cities):
            gap = text[s.end():c.start()]
            if 0 <= c.start() - s.end() <= 3 and re.fullmatch(r"[,\s]*", gap):
                end, conf = c.end(), 0.92
                used_cities.add(i)
                break
        yield TextMatch(s.start(), end, ADDRESS, "Street address", conf, masking.mask_words(text[s.start():end]))
    for i, c in enumerate(cities):
        if i not in used_cities:
            yield TextMatch(c.start(), c.end(), ADDRESS, "City, state and ZIP", 0.65, masking.mask_words(c.group(0)))
    for m in _PO_BOX_RE.finditer(text):
        yield TextMatch(m.start(), m.end(), ADDRESS, "PO box", 0.8, masking.mask_words(m.group(0)))


ALL_PII_DETECTORS = (find_emails, find_cards, find_phones, find_ips, find_coordinates, find_government_ids, find_addresses)

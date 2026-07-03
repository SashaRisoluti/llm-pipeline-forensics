import random
import re

COMPANIES = ["Acme Corp", "Globex", "Initech", "Umbrella Ltd", "Stark Industries",
             "Wayne Enterprises", "Hooli", "Vandelay Industries"]
PEOPLE = ["Anna Rossi", "Marco Bianchi", "Julia Chen", "Omar Haddad",
          "Sofia Costa", "Liam O'Brien"]
CATEGORIES = ["billing", "legal", "staffing", "logistics", "marketing"]

TEMPLATES = {
    "invoice": (
        "INVOICE #{num}\nFrom: {company_a}\nTo: {company_b}\n"
        "Issued: {date_a}  Due: {date_b}\n"
        "Services rendered ({category}): consulting hours.\n"
        "Total: € {amount} EUR\n"
    ),
    "contract": (
        "SERVICE AGREEMENT\nBetween {company_a} and {company_b}.\n"
        "Effective {date_a}, terminating {date_b}.\n"
        "{company_b} shall pay € {amount} EUR monthly for {category} services.\n"
        "Signed: {person_a}, {person_b}\n"
    ),
    "meeting_notes": (
        "MEETING NOTES — {date_a}\nAttendees: {person_a}, {person_b}\n"
        "Discussed {category} budget of € {amount} EUR.\n"
        "Action: {person_a} to follow up by {date_b}.\n"
    ),
    "report": (
        "QUARTERLY REPORT — {company_a}\nPeriod ending {date_a}.\n"
        "{category} spend reached € {amount} EUR, up from last quarter.\n"
        "Prepared by {person_a} on {date_b}.\n"
    ),
    "receipt": (
        "RECEIPT #{num}\nVendor: {company_a}\nDate: {date_a}\n"
        "Item: {category} supplies\nPaid: € {amount} EUR by card\n"
    ),
}

AMBIGUOUS_SENTENCES = [
    "\nNote: this also serves as a binding agreement summary and payment record.",
    "\nP.S. treat this as both the invoice and the final report for the quarter.",
    "\nThis document doubles as meeting minutes and a purchase receipt.",
]


def _random_date(rng: random.Random) -> str:
    return f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def generate_doc(doc_type: str, seed: int) -> str:
    rng = random.Random(seed)
    return TEMPLATES[doc_type].format(
        num=rng.randint(1000, 9999),
        company_a=rng.choice(COMPANIES),
        company_b=rng.choice(COMPANIES),
        person_a=rng.choice(PEOPLE),
        person_b=rng.choice(PEOPLE),
        date_a=_random_date(rng),
        date_b=_random_date(rng),
        amount=f"{rng.randint(100, 99999) / 100 * 100:,.2f}",
        category=rng.choice(CATEGORIES),
    )


DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def corrupt_strip_dates(text: str) -> str:
    return DATE_RE.sub("[date unavailable]", text)


def corrupt_currency_mismatch(text: str) -> str:
    return text.replace("EUR", "USD")


def corrupt_ambiguous_category(text: str, seed: int = 0) -> str:
    rng = random.Random(seed)
    return text + rng.choice(AMBIGUOUS_SENTENCES)


CORRUPTORS = {
    "strip_dates": lambda text, seed: corrupt_strip_dates(text),
    "currency_mismatch": lambda text, seed: corrupt_currency_mismatch(text),
    "ambiguous_category": corrupt_ambiguous_category,
}


def generate_batch(n: int, seed: int, corruption_rate: float = 0.2) -> list[dict]:
    rng = random.Random(seed)
    doc_types = list(TEMPLATES)
    batch = []
    corruptor_names = sorted(CORRUPTORS)
    for i in range(n):
        doc_type = doc_types[i % len(doc_types)]
        text = generate_doc(doc_type, seed=seed + i)
        corruption = None
        if rng.random() < corruption_rate:
            corruption = corruptor_names[i % len(corruptor_names)]
            text = CORRUPTORS[corruption](text, seed + i)
        batch.append({
            "doc_id": f"doc-{i:03d}",
            "doc_type": doc_type,
            "corruption": corruption,
            "text": text,
        })
    # guarantee all three corruption kinds appear at the default demo size
    present = {d["corruption"] for d in batch if d["corruption"]}
    for name in corruptor_names:
        if name not in present and n >= len(corruptor_names):
            idx = corruptor_names.index(name)
            target = batch[idx]
            target["corruption"] = name
            target["text"] = CORRUPTORS[name](
                generate_doc(target["doc_type"], seed=seed + idx), seed + idx
            )
    return batch

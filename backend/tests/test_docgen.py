from pipeline.docgen import (
    corrupt_ambiguous_category,
    corrupt_currency_mismatch,
    corrupt_strip_dates,
    generate_batch,
    generate_doc,
)


def test_generate_doc_is_deterministic() -> None:
    assert generate_doc("invoice", seed=7) == generate_doc("invoice", seed=7)
    assert generate_doc("invoice", seed=7) != generate_doc("invoice", seed=8)


def test_strip_dates_removes_dates() -> None:
    text = "Invoice issued 2026-03-15, due 2026-04-15."
    out = corrupt_strip_dates(text)
    assert "2026-03-15" not in out and "2026-04-15" not in out


def test_currency_mismatch_swaps_code_keeps_symbol() -> None:
    text = "Total: € 1,200.00 EUR payable to Acme."
    out = corrupt_currency_mismatch(text)
    assert "EUR" not in out
    assert "USD" in out
    assert "€" in out  # symbol/code disagreement = the failure


def test_ambiguous_category_appends_confuser() -> None:
    out = corrupt_ambiguous_category("Meeting notes from Monday.")
    assert len(out) > len("Meeting notes from Monday.")


def test_generate_batch_marks_corrupted() -> None:
    batch = generate_batch(n=50, seed=42, corruption_rate=0.2)
    assert len(batch) == 50
    corrupted = [d for d in batch if d["corruption"] is not None]
    assert 4 <= len(corrupted) <= 18  # ~20% of 50, wide bounds for the fixed seed
    assert {d["corruption"] for d in corrupted} == {
        "strip_dates", "currency_mismatch", "ambiguous_category",
    }
    # deterministic
    assert generate_batch(n=50, seed=42, corruption_rate=0.2) == batch

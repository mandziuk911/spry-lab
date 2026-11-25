# Colab run — saved browser output

CPU, 25 November 2026. Copy is not publicly shared at submission time; fresh Run all not verified.

## Document to Markdown

```
```markdown
# INVOICE

**Invoice No.:** INV-2026-0417
**Date:** 2026-11-12
**Due date:** 2026-11-26

**From:** Spry Analytics LLC, 2a Kozelnyska St, Lviv
**Bill to:** Ukrainian Catholic University, 17 Sventsitskoho St, Lviv

| Description | Qty | Unit price | Amount |
|---|---|---|---|
| Meeting analytics, Team plan (monthly) | 1 | 120.00 | 120.00 |
| Extra seats | 15 | 4.50 | 67.50 |
| Onboarding workshop (2 h) | 1 | 200.00 | 200.00 |

| Subtotal | 387.50 |
| VAT 20% | 77.50 |
| **TOTAL, USD** | **465.00** |

Payment by bank transfer within 14 days. Thank you!
```

Page to Markdown on CPU: 274 s

```

## Extraction A and B

```
A took 70 s
B took 70 s
A, Markdown:
{
  "invoice_number": "INV-2026-0417",
  "date": "2026-11-12",
  "due_date": "2026-11-26",
  "seller": "Spry Analytics LLC",
  "buyer": "Ukrainian Catholic University",
  "items": [
    {
      "description": "Meeting analytics, Team plan (monthly)",
      "qty": 1,
      "unit_price": 120.00000000000001
    },
    {
      "description": "Extra seats",
      "qty": 15,
      "unit_price": 4.50
    },
    {
      "description": "Onboarding workshop (2 h)",
      "qty": 1,
      "unit_price": 200.00
    }
  ],
  "subtotal": 387.50,
  "vat": 77.50,
  "total": 465.0
}

B, image:
{
  "invoice_number": "INV-2026-0417",
  "date": "2026-11-12",
  "due_date": "2026-11-26",
  "seller": "Spry Analytics LLC",
  "buyer": "Ukrainian Catholic University",
  "items": [
    {
      "description": "Meeting analytics, Team plan (monthly)",
      "qty": 1,
      "unit_price": 120.00
    },
    {
      "description": "Extra seats",
      "qty": 15,
      "unit_price": 4.50
    },
    {
      "description": "Onboarding workshop (2 h)",
      "qty": 1,
      "unit_price": 200.00
    }
  ],
  "subtotal": 387.50,
  "vat": 77.50,
  "total": 465.00
}

```

## Verification

```
A, Markdown: 7 of 9 fields match; wrong: seller, buyer
   seller: expected 'Spry Analytics LLC, 2a Kozelnytska St, Lviv', got 'Spry Analytics LLC'
   buyer: expected 'Ukrainian Catholic University, 17 Sventsitskoho St, Lviv', got 'Ukrainian Catholic University'
B, image: 7 of 9 fields match; wrong: seller, buyer
   seller: expected 'Spry Analytics LLC, 2a Kozelnytska St, Lviv', got 'Spry Analytics LLC'
   buyer: expected 'Ukrainian Catholic University, 17 Sventsitskoho St, Lviv', got 'Ukrainian Catholic University'

```

## Measured timings

```
Lab 9, Part 4 without a Google Cloud bill, on CPU

4. Document parsing (qwen3-vl:2b-instruct): the page to Markdown in 274 s
5. Form parser (qwen3-vl:2b-instruct): A (Markdown) 7/9 fields in 70 s, B (image) 7/9 fields in 70 s


```

# Vision eval fixtures

Used by `tests/test_downscale_accuracy.py` to prove that downscaling crop photos
before diagnosis doesn't cost accuracy.

## Why this exists

`settings.max_image_edge` (1280) is a latency optimisation: it cuts a 12MP phone
photo to ~250KB, which is worth ~60s of upload on rural mobile data. But it's the
one optimisation that changes what the vision model actually sees — so it needs to
be verified, not assumed.

**The gate:** accuracy at 1280 must match accuracy at native resolution. If it
doesn't, raise `max_image_edge` (try 1568). Never trade a correct diagnosis for
latency — a wrong disease call costs a farmer a season.

## Setup

Create `plantvillage.json` here — a list of labeled samples:

```json
[
  {
    "file": "tomato_early_blight_01.jpg",
    "url": "https://<host>/<path>/tomato_early_blight_01.jpg",
    "issue": "Early Blight",
    "category": "disease"
  }
]
```

- `file` — local cache name under `images/`
- `url` — where to fetch it once (images are cached locally and **gitignored**)
- `issue` — the ground-truth label. Matching is a lenient substring check, so
  `"Early Blight"` matches the model's `"Early Blight (Alternaria)"`.
- `category` — `disease` | `pest` | `nutrient` | `healthy`

**Source:** the PlantVillage dataset (public, ~54k labeled leaf images) — available
via Kaggle or its GitHub mirrors. Take ~30-50 images spanning the diseases in
`app/services/knowledge.py` (Early Blight, Powdery Mildew, Leaf Curl Virus,
nutrient deficiency) plus some healthy leaves, so the eval reflects what the KB can
actually treat.

Prefer images resembling real farmer photos (in-field, uneven light) over clean lab
shots — lab images are easy at any resolution and would hide a real regression.

## Running

```bash
RUN_VISION_EVAL=1 pytest tests/test_downscale_accuracy.py -s
```

Opt-in on purpose: it makes real (paid) Fireworks vision calls and fetches images.
The default `pytest` run skips it.

Output:

```
resolution  accuracy      avg latency
native      28/30 (93%)   6.2s
1280        28/30 (93%)   3.1s
1024        26/30 (87%)   2.7s
```

(Illustrative shape only — run it for real numbers.) Note `images/` is gitignored;
nothing here gets committed.

"""Seed demo listings and set their prices in Booking.

    python loadtest/seed.py --count 300

Listings are created and published in Catalog (`manage.py seed_listings`), reach Booking
through the outbox, then get a price through the public API. Finally Booking gets a year
of past stays (`python -m app.demo_stays`) for the host's statistics. Standard library
only.
"""

import argparse
import json
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request

GATEWAY = "http://localhost"


def request(method: str, path: str, token: str, body: dict[str, object] | None = None) -> int:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        GATEWAY + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    for _ in range(20):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return int(response.status)
        except urllib.error.HTTPError as error:
            if error.code != 429:
                return error.code
            time.sleep(1)  # outside load test mode the gateway limit applies
    return 429


def price(listing_id: str, token: str, rng: random.Random) -> None:
    path = f"/api/v1/host/listings/{listing_id}/pricing"
    nightly = rng.randrange(6_000, 25_000, 500)
    pricing = {
        "currency": "EUR",
        "nightly_price": nightly,
        "weekend_price": nightly * 6 // 5,
        "cleaning_fee": rng.randrange(2_000, 6_000, 500),
        "min_nights": rng.choice((1, 2, 2, 3)),
        "weekly_discount_percent": rng.choice((0, 5, 10)),
    }
    for _ in range(60):  # the listing reaches Booking through the outbox within seconds
        status = request("PUT", path, token, pricing)
        if status == 200:
            return
        if status != 404:
            sys.exit(f"Pricing {listing_id} failed with {status}")
        time.sleep(0.5)
    sys.exit(f"Listing {listing_id} never arrived in Booking")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    output = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "catalog-api",
            "python",
            "manage.py",
            "seed_listings",
            "--count",
            str(args.count),
            "--seed",
            str(args.seed),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    seeded = json.loads(output.strip().splitlines()[-1])
    rng = random.Random(args.seed)
    for n, listing_id in enumerate(seeded["listing_ids"], start=1):
        price(listing_id, seeded["host_token"], rng)
        if n % 50 == 0:
            print(f"priced {n}/{len(seeded['listing_ids'])}")
    print(f"Seeded {len(seeded['listing_ids'])} bookable listings.")
    subprocess.run(
        ["docker", "compose", "exec", "-T", "booking-api", "python", "-m", "app.demo_stays"],
        check=True,
    )


if __name__ == "__main__":
    main()

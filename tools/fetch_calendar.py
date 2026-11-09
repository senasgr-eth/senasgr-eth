"""Fetch the GitHub contribution calendar into cache/calendar.json.

The GitHub Action runs this once a day; tools/build_board.py turns the cache
into the two SVGs. Works locally too -- if GITHUB_TOKEN is unset it borrows the
token from the GitHub CLI (`gh auth token`).

A token is required because the GraphQL API does not serve anonymous queries.
The default Actions token is enough: the calendar of a public profile is
public data.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "calendar.json"
LOGIN = os.environ.get("PROFILE_LOGIN", "senasgr-eth")

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(privacy: PUBLIC, ownerAffiliations: [OWNER], first: 1) {
      totalCount
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            weekday
            contributionCount
          }
        }
      }
    }
  }
}
"""


def token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        return subprocess.check_output(
            ["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("Set GITHUB_TOKEN or log in with `gh auth login`.")


def main() -> None:
    response = requests.post(
        "https://api.github.com/graphql",
        json={"query": QUERY, "variables": {"login": LOGIN}},
        headers={"Authorization": f"bearer {token()}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    if "errors" in payload:
        sys.exit(f"GraphQL error: {payload['errors']}")

    calendar = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    repos = payload["data"]["user"]["repositories"]["totalCount"]
    weeks = [
        [
            {
                "date": day["date"],
                "weekday": day["weekday"],
                "contributionCount": day["contributionCount"],
            }
            for day in week["contributionDays"]
        ]
        for week in calendar["weeks"]
    ]

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps({"login": LOGIN, "repos": repos, "weeks": weeks}, separators=(",", ":"))
        + "\n"
    )
    print(
        f"wrote {CACHE.relative_to(ROOT)}: "
        f"{len(weeks)} weeks, {calendar['totalContributions']} contributions"
    )


if __name__ == "__main__":
    main()

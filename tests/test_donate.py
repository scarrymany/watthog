"""Проверка реквизитов для поддержки проекта.

Опечатка в криптоадресе означает безвозвратно потерянный перевод, поэтому
каждая копия адреса в документации сверяется с единственным источником правды -
модулем :mod:`watthog.donate`.
"""

from pathlib import Path

import pytest

from watthog.donate import DONATION_ADDRESSES, DONATION_NOTE

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_WITH_ADDRESSES = ("DONATE.md",)

# Длина адреса зависит от сети и является простейшей защитой от обрезанной копии.
EXPECTED_LENGTHS = {
    "TRC20": 34,
    "BEP20": 42,
    "TON": 48,
    "Litecoin": 43,
    "Bitcoin": 42,
}


def test_every_network_is_listed_once():
    networks = [donation.network for donation in DONATION_ADDRESSES]
    assert len(networks) == len(set(networks))
    assert set(networks) == set(EXPECTED_LENGTHS)


@pytest.mark.parametrize("donation", DONATION_ADDRESSES, ids=lambda d: d.network)
def test_address_has_the_expected_shape(donation):
    assert len(donation.address) == EXPECTED_LENGTHS[donation.network]
    assert donation.address == donation.address.strip()
    assert " " not in donation.address
    assert donation.address.isascii()


def test_address_prefixes_match_their_networks():
    prefixes = {
        "TRC20": "T",
        "BEP20": "0x",
        "TON": "UQ",
        "Litecoin": "ltc1",
        "Bitcoin": "bc1",
    }
    for donation in DONATION_ADDRESSES:
        assert donation.address.startswith(prefixes[donation.network])


@pytest.mark.parametrize("document", DOCUMENTS_WITH_ADDRESSES)
def test_documentation_repeats_every_address_exactly(document):
    text = (ROOT / document).read_text(encoding="utf-8")
    for donation in DONATION_ADDRESSES:
        assert donation.address in text, f"{document}: нет адреса сети {donation.network}"


def test_readme_links_to_the_donation_page():
    for readme in ("README.md", "README.en.md"):
        assert "DONATE.md" in (ROOT / readme).read_text(encoding="utf-8")


def test_funding_file_points_at_the_donation_page():
    funding = (ROOT / ".github" / "FUNDING.yml").read_text(encoding="utf-8")
    assert "DONATE.md" in funding


def test_note_is_present_for_the_interfaces():
    assert DONATION_NOTE.strip()

"""Реквизиты для поддержки проекта.

Адреса хранятся в одном месте и оттуда попадают и в интерфейсы, и в
документацию. Ошибка в криптоадресе означает безвозвратно потерянный перевод,
поэтому совпадение всех копий проверяется тестом.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DonationAddress:
    """Один способ поддержать проект."""

    network: str
    asset: str
    address: str


DONATION_ADDRESSES: tuple[DonationAddress, ...] = (
    DonationAddress("TRC20", "USDT, TRX", "TLEzifd4zGRtHt4JbMhXKrzM2bMfNj6YTM"),
    DonationAddress("BEP20", "USDT, BNB", "0x5DC287eeae44d140AcF80Ea20D695A6A1De9Ba8d"),
    DonationAddress("TON", "Toncoin", "UQB2w5UGye1nw0yQGQrPPkeIdwWZ1_2iwRX6fLgh5iMn1vDk"),
    DonationAddress("Litecoin", "LTC", "ltc1q9384p272katyss6s7ugeez8vdkm49jtxktyheu"),
    DonationAddress("Bitcoin", "BTC", "bc1q5w8ynurd6urjkxzhy9z6av65cauc3culy60get"),
)

DONATION_NOTE = "Проект бесплатный и без рекламы. Поддержка ускоряет развитие, но ни на что не влияет."

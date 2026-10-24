import random
import string
import re
import json
from pathlib import Path
from faker import Faker

# ─── Country list ─────────────────────────────────
COUNTRIES = {
    "1": {"code": "BD", "locale": "bn_BD", "phone": "+880", "name": "Bangladesh"},
    "2": {"code": "US", "locale": "en_US", "phone": "+1",   "name": "United States"},
    "3": {"code": "IN", "locale": "en_IN", "phone": "+91",  "name": "India"},
    "4": {"code": "PK", "locale": "en_US", "phone": "+92",  "name": "Pakistan"},
    "5": {"code": "GB", "locale": "en_GB", "phone": "+44",  "name": "United Kingdom"},
    "6": {"code": "PH", "locale": "en_US", "phone": "+63",  "name": "Philippines"},
    "7": {"code": "NG", "locale": "en_US", "phone": "+234", "name": "Nigeria"},
    "8": {"code": "ID", "locale": "id_ID", "phone": "+62",  "name": "Indonesia"},
}

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def is_email(s: str) -> bool:
    return bool(EMAIL_REGEX.match(s.strip()))


def is_phone(s: str) -> bool:
    cleaned = "".join(c for c in s if c.isdigit())
    return len(cleaned) >= 8


# ─── Identity generator ───────────────────────────
def generate_identity(country_code="BD"):
    locale = "en_US"
    for c in COUNTRIES.values():
        if c["code"] == country_code:
            locale = c["locale"]
            break

    fake = Faker(locale)

    first = (fake.first_name().split()[0] or "User")[:20]
    last = (fake.last_name().split()[0] or "Test")[:20]

    return {
        "first_name": first,
        "last_name": last,
        "password": _gen_password(),
        "birthday": {
            "day": random.randint(1, 28),
            "month": random.randint(1, 12),
            "year": random.randint(1988, 2004),
        },
        "gender": random.choice(["1", "2"]),  # 1=female, 2=male
    }


def _gen_password(length=12):
    chars = string.ascii_letters + string.digits + "@#$%&*"
    return "".join(random.choices(chars, k=length))


# ─── Proxy handler ────────────────────────────────
class ProxyHandler:
    def __init__(self, proxy_file="proxies.txt"):
        self.proxy_file = Path(proxy_file)
        self.proxies = []
        self.blocked = set()
        self.load()

    def load(self):
        self.proxies = []
        if not self.proxy_file.exists():
            self.proxy_file.touch()
            return
        for line in self.proxy_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                self.proxies.append(line)

    def get(self):
        available = [p for p in self.proxies if p not in self.blocked]
        if not available:
            return None
        return random.choice(available)

    def block(self, proxy):
        self.blocked.add(proxy)

    def stats(self):
        return {
            "total": len(self.proxies),
            "blocked": len(self.blocked),
            "available": len(self.proxies) - len(self.blocked),
        }


# ─── Account storage ──────────────────────────────
ACCOUNTS_FILE = Path("accounts.txt")


def save_account(account: dict):
    line = json.dumps(account, ensure_ascii=False)
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_accounts() -> list:
    if not ACCOUNTS_FILE.exists():
        return []
    accounts = []
    for line in ACCOUNTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                accounts.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return accounts
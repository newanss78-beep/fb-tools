import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent


class FBCreator:
    BASE = "https://mbasic.facebook.com"

    def __init__(self, proxy=None):
        self.session = requests.Session()

        try:
            ua = UserAgent().random
        except Exception:
            ua = ("Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

        if proxy:
            parts = proxy.split(":")
            if len(parts) >= 4:
                proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            elif len(parts) >= 2:
                proxy_url = f"http://{parts[0]}:{parts[1]}"
            else:
                proxy_url = f"http://{proxy}"
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

    # ── Registration ─────────────────────────────
    def register(self, contact, identity):
        """Return: (success: bool, message: str, extra: dict)"""
        try:
            r = self.session.get(f"{self.BASE}/reg/", timeout=30)
            if r.status_code != 200:
                return False, f"GET failed ({r.status_code})", {}

            soup = BeautifulSoup(r.text, "lxml")
            form = soup.find("form")
            if not form:
                return False, "Registration form not found", {}

            hidden = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if name and inp.get("type") in ("hidden", None):
                    hidden[name] = inp.get("value", "")

            data = {
                **hidden,
                "firstname": identity["first_name"],
                "lastname": identity["last_name"],
                "reg_email__": contact,
                "reg_passwd__": identity["password"],
                "birthday_day": str(identity["birthday"]["day"]),
                "birthday_month": str(identity["birthday"]["month"]),
                "birthday_year": str(identity["birthday"]["year"]),
                "sex": identity["gender"],
            }
            if "@" in contact:
                data["reg_email_confirmation__"] = contact

            r = self.session.post(
                f"{self.BASE}/reg/", data=data, timeout=30, allow_redirects=True
            )

            text = r.text.lower()

            if any(k in text for k in
                   ["confirm your email", "enter the code", "we sent",
                    "confirmation code", "enter code"]):
                return True, "OTP_REQUIRED", {"url": r.url}

            if any(k in text for k in ["disabled", "suspended", "blocked"]):
                return False, "Account blocked by Facebook", {}

            if any(k in text for k in ["captcha", "checkpoint", "security check"]):
                return False, "CAPTCHA / Security checkpoint", {}

            if any(k in text for k in ["home", "news feed", "welcome"]):
                return True, "SUCCESS", {}

            if "/home" in r.url or "/login" in r.url:
                return True, "SUCCESS (likely)", {"url": r.url}

            return False, "Unknown response", {"url": r.url}

        except requests.exceptions.ProxyError:
            return False, "Proxy connection failed", {}
        except requests.exceptions.Timeout:
            return False, "Request timeout", {}
        except requests.exceptions.ConnectionError:
            return False, "Connection error", {}
        except Exception as e:
            return False, f"Error: {str(e)[:100]}", {}

    # ── OTP submission ───────────────────────────
    def submit_otp(self, otp):
        try:
            for endpoint in ["/confirmemail.php", "/checkpoint/", "/two_step_verification/"]:
                try:
                    r = self.session.post(
                        f"{self.BASE}{endpoint}",
                        data={"code": otp, "approvals_code": otp},
                        timeout=30,
                        allow_redirects=True,
                    )
                    t = r.text.lower()
                    if any(k in t for k in ["success", "welcome", "home", "news feed"]):
                        return True, "OTP accepted — account verified"
                except Exception:
                    continue

            r = self.session.get(f"{self.BASE}/", timeout=30)
            if any(k in r.text.lower() for k in ["home", "news feed", "welcome"]):
                return True, "Account active"
            return False, "OTP submission uncertain — check manually"
        except Exception as e:
            return False, f"OTP error: {str(e)[:80]}"
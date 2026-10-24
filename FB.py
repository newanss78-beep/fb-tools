import os
import time
import random
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box
from faker import Faker
from playwright.sync_api import sync_playwright

console = Console()
fake = Faker()
ACCOUNTS_FILE = Path("accounts.txt")

def get_chromium_path():
    path = "/data/data/com.termux/files/usr/bin/chromium"
    if os.path.exists(path):
        return path
    return None

def generate_identity():
    first = fake.first_name()
    last = fake.last_name()
    pwd = fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True)
    return {
        "first_name": first,
        "last_name": last,
        "password": pwd,
        "day": str(random.randint(1, 28)),
        "month": str(random.randint(1, 12)),
        "year": str(random.randint(1990, 2004)),
        "gender": random.choice(["1", "2"])
    }

def save_account(data):
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"Email/Phone: {data['contact']} | Pass: {data['password']} | Name: {data['first_name']} {data['last_name']} | Status: {data['status']}\n")

def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]FACEBOOK AUTO REGISTRATION[/]\n[dim]Playwright + Termux Version[/]", border_style="cyan"))

    contact = Prompt.ask("\n[bold yellow]Enter Email or Phone Number[/]")
    proxy = Prompt.ask("[bold yellow]Enter Proxy (host:port:user:pass) or leave blank[/]", default="")

    console.print("\n[dim]Generating Identity...[/]")
    identity = generate_identity()
    
    t = Table(box=box.ROUNDED)
    t.add_column("Field", style="cyan")
    t.add_column("Value", style="green")
    t.add_row("Name", f"{identity['first_name']} {identity['last_name']}")
    t.add_row("Password", identity['password'])
    console.print(t)

    console.print("\n[bold yellow]▶ Launching Browser...[/]")
    
    with sync_playwright() as p:
        launch_args = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        }
        
        chromium_path = get_chromium_path()
        if chromium_path:
            launch_args["executable_path"] = chromium_path
            console.print(f"[dim]Using Termux Chromium: {chromium_path}[/]")

        if proxy:
            parts = proxy.split(":")
            if len(parts) == 4:
                launch_args["proxy"] = {
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3]
                }
            elif len(parts) == 2:
                launch_args["proxy"] = {"server": f"http://{parts[0]}:{parts[1]}"}

        browser = p.chromium.launch(**launch_args)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            viewport={"width": 412, "height": 915}
        )
        page = context.new_page()

        try:
            console.print("[dim]Loading Facebook...[/]")
            page.goto("https://www.facebook.com/reg/", timeout=60000)
            time.sleep(3)

            console.print("[dim]Filling form...[/]")
            page.fill('input[name="firstname"]', identity["first_name"])
            page.fill('input[name="lastname"]', identity["last_name"])
            
            if "@" in contact:
                page.fill('input[name="reg_email__"]', contact)
            else:
                page.fill('input[name="reg_email__"]', contact)

            page.fill('input[name="reg_passwd__"]', identity["password"])
            
            page.select_option("#day", identity["day"])
            page.select_option("#month", identity["month"])
            page.select_option("#year", identity["year"])
            
            page.click(f'input[name="sex"][value="{identity["gender"]}"]')
            time.sleep(1)
            
            console.print("[dim]Submitting form...[/]")
            page.click('button[name="websubmit"]')
            time.sleep(6)

            content = page.content().lower()
            
            if "checkpoint" in page.url or "code" in content or "confirm" in content:
                console.print("\n[bold cyan]⚠ Facebook OTP চাচ্ছে![/]")
                otp = Prompt.ask("[bold yellow]আপনার Email/SMS থেকে OTP দিন[/]")
                
                if otp:
                    try:
                        console.print("[dim]Submitting OTP...[/]")
                        page.fill('input[name="code"]', otp)
                        page.click('button[type="submit"]')
                        time.sleep(5)
                        
                        if "home" in page.url or "checkpoint" not in page.url:
                            console.print("[bold green]✅ Account Created Successfully![/]")
                            identity["contact"] = contact
                            identity["status"] = "Success"
                            save_account(identity)
                        else:
                            console.print("[bold red]❌ OTP ভুল অথবা ব্লকড।[/]")
                    except Exception as e:
                        console.print(f"[red]OTP ফিল্ডে সমস্যা: {e}[/]")
            elif "disabled" in content or "blocked" in content:
                console.print("[bold red]❌ Facebook এই IP বা ডিভাইস ব্লক করেছে। Proxy ব্যবহার করুন।[/]")
            else:
                console.print("[bold yellow]⚠ ফেসবুক রেসপন্স দিচ্ছে না ঠিকমতো। ম্যানুয়ালি চেক করুন।[/]")

        except Exception as e:
            console.print(f"\n[bold red]Error: {e}[/]")
        finally:
            browser.close()

    Prompt.ask("\n[dim]Press Enter to exit...[/]", default="")

if __name__ == "__main__":
    main()

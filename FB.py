"""
Facebook Account Creator — Educational Tool
সম্পূর্ণ শিক্ষামূলক উদ্দেশ্যে। Meta-র ToS মানুন।
"""
import sys
import time
import random
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
from rich import box

from helpers import (
    COUNTRIES, generate_identity, ProxyHandler,
    is_email, save_account, load_accounts,
)
from creator import FBCreator

console = Console()
proxy_handler = ProxyHandler()


def banner():
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]FACEBOOK ACCOUNT CREATOR[/]\n"
        "[dim]Educational tool — respect Meta ToS[/]",
        border_style="cyan", box=box.DOUBLE,
    ))


def show_stats():
    s = proxy_handler.stats()
    console.print(f"\n[dim]Proxies:[/] [yellow]{s['available']}[/]/{s['total']} available")
    console.print(f"[dim]Accounts created:[/] [green]{len(load_accounts())}[/]\n")


def select_country():
    t = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
    t.add_column("#", style="cyan", width=3)
    t.add_column("Country", style="white")
    t.add_column("Code", style="dim")
    for k, v in COUNTRIES.items():
        t.add_row(k, v["name"], v["phone"])
    console.print(t)
    choice = Prompt.ask("[bold]Select country[/]", choices=list(COUNTRIES.keys()), default="1")
    return COUNTRIES[choice]


def show_identity(identity):
    t = Table(title="Generated Identity", box=box.ROUNDED, title_style="bold green")
    t.add_column("Field", style="cyan")
    t.add_column("Value", style="white")
    t.add_row("First Name", identity["first_name"])
    t.add_row("Last Name", identity["last_name"])
    t.add_row("Password", identity["password"])
    b = identity["birthday"]
    t.add_row("Birthday", f"{b['day']:02d}/{b['month']:02d}/{b['year']}")
    t.add_row("Gender", "Male" if identity["gender"] == "2" else "Female")
    console.print(t)


def create_single_account(contact_type="email"):
    banner()
    console.print(f"\n[bold yellow]▶ Create account via {contact_type.upper()}[/]\n")

    # 1) Contact input
    if contact_type == "email":
        while True:
            contact = Prompt.ask("[bold]Enter Email[/]")
            if is_email(contact):
                break
            console.print("[red]✗ Invalid email[/]")
        country = "BD"
    else:
        c = select_country()
        country = c["code"]
        while True:
            phone = Prompt.ask(f"[bold]Enter phone number (e.g., 17XXXXXXXX)[/]")
            digits = "".join(x for x in phone if x.isdigit())
            if len(digits) >= 8:
                contact = f"{c['phone']}{digits}"
                break
            console.print("[red]✗ Invalid phone[/]")

    console.print(f"\n[dim]Contact:[/] [cyan]{contact}[/]")

    # 2) Identity
    identity = generate_identity(country)
    show_identity(identity)

    # 3) Proxy
    use_proxy = Confirm.ask("Use proxy?", default=False)
    proxy = proxy_handler.get() if use_proxy else None
    if use_proxy and not proxy:
        console.print("[red]✗ No proxies in proxies.txt[/]")
        Prompt.ask("\n[dim]Press Enter[/]", default="")
        return
    if proxy:
        console.print(f"[dim]Proxy:[/] [cyan]{proxy}[/]")

    # 4) Submit
    console.print()
    creator = FBCreator(proxy=proxy)
    with console.status("[bold yellow]Submitting registration...[/]", spinner="dots"):
        success, message, extra = creator.register(contact, identity)

    # 5) Result
    if success and message == "OTP_REQUIRED":
        console.print("\n[yellow]⚠ Facebook OTP চাচ্ছে[/]")
        console.print("[dim]আপনার email বা SMS-এ কোড দেখুন[/]")
        otp = Prompt.ask("\n[bold]Enter OTP[/]", default="")
        if otp:
            with console.status("[yellow]Submitting OTP...[/]", spinner="dots"):
                ok, msg = creator.submit_otp(otp)
            console.print(f"[{'green' if ok else 'red'}]✓ {msg}[/]")

        save_account({**identity, "contact": contact,
                      "proxy": proxy or "", "status": "otp-pending",
                      "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        console.print("\n[green]✓ Saved to accounts.txt[/]")

    elif success:
        console.print(f"\n[bold green]✓ {message}[/]")
        save_account({**identity, "contact": contact,
                      "proxy": proxy or "", "status": "created",
                      "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        console.print("[green]✓ Saved to accounts.txt[/]")

    else:
        console.print(f"\n[bold red]✗ Failed: {message}[/]")
        if proxy and "proxy" in message.lower():
            proxy_handler.block(proxy)
            console.print(f"[yellow]Proxy blocked: {proxy}[/]")

    Prompt.ask("\n[dim]Press Enter[/]", default="")


def bulk_create():
    banner()
    console.print("\n[bold yellow]▶ Bulk Creation[/]\n")

    contact_type = Prompt.ask("Type", choices=["email", "phone"], default="email")
    count = IntPrompt.ask("How many?", default=3)

    contacts = []
    console.print(f"\n[dim]Enter {count} {contact_type}(s):[/]")
    for i in range(count):
        while True:
            c = Prompt.ask(f"  {i+1}/{count}")
            if (contact_type == "email" and is_email(c)) or \
               (contact_type == "phone" and len("".join(x for x in c if x.isdigit())) >= 8):
                contacts.append(c)
                break
            console.print("[red]✗ Invalid[/]")

    if not Confirm.ask(f"\nCreate {count} accounts?", default=False):
        return

    c_info = select_country() if contact_type == "phone" else {"code": "BD", "phone": ""}

    for i, raw in enumerate(contacts, 1):
        contact = f"{c_info['phone']}{''.join(x for x in raw if x.isdigit())}" \
                  if contact_type == "phone" else raw
        console.print(f"\n[bold cyan]━━━ [{i}/{count}] {contact} ━━━[/]")

        identity = generate_identity(c_info["code"])
        proxy = proxy_handler.get()
        console.print(f"Name: {identity['first_name']} {identity['last_name']}")
        console.print(f"Pass: {identity['password']}")
        console.print(f"Proxy: {proxy or 'none'}")

        with console.status("Submitting...", spinner="dots"):
            success, message, _ = FBCreator(proxy=proxy).register(contact, identity)

        if success and message == "OTP_REQUIRED":
            console.print("[yellow]⚠ OTP needed — skipped for bulk[/]")
            save_account({**identity, "contact": contact, "proxy": proxy or "",
                          "status": "otp-pending",
                          "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        elif success:
            console.print("[green]✓ Created[/]")
            save_account({**identity, "contact": contact, "proxy": proxy or "",
                          "status": "created",
                          "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
        else:
            console.print(f"[red]✗ {message}[/]")
            if proxy:
                proxy_handler.block(proxy)

        if i < count:
            delay = random.randint(20, 40)
            console.print(f"[dim]Waiting {delay}s...[/]")
            time.sleep(delay)

    Prompt.ask("\n[dim]Press Enter[/]", default="")


def manage_proxies():
    banner()
    console.print("\n[bold yellow]▶ Proxy Manager[/]\n")
    s = proxy_handler.stats()
    t = Table(box=box.ROUNDED)
    t.add_column("Status", style="cyan")
    t.add_column("Count")
    t.add_row("Total", str(s["total"]))
    t.add_row("Available", f"[green]{s['available']}[/]")
    t.add_row("Blocked", f"[red]{s['blocked']}[/]")
    console.print(t)

    console.print(f"\n[dim]File:[/] {proxy_handler.proxy_file}")
    console.print("[dim]Format: host:port:user:pass  OR  host:port[/]")

    if Confirm.ask("\nReload from file?", default=False):
        proxy_handler.load()
        console.print(f"[green]✓ Loaded {len(proxy_handler.proxies)} proxies[/]")

    Prompt.ask("\n[dim]Press Enter[/]", default="")


def view_accounts():
    banner()
    console.print("\n[bold yellow]▶ Saved Accounts[/]\n")
    accounts = load_accounts()
    if not accounts:
        console.print("[dim]No accounts yet[/]")
        Prompt.ask("\n[dim]Press Enter[/]", default="")
        return

    t = Table(box=box.ROUNDED, header_style="bold magenta")
    t.add_column("#", style="cyan", width=3)
    t.add_column("Contact")
    t.add_column("Password")
    t.add_column("Name")
    t.add_column("Status")
    for i, a in enumerate(accounts, 1):
        t.add_row(str(i), a["contact"], a["password"],
                  f"{a['first_name']} {a['last_name']}", a["status"])
    console.print(t)
    console.print("\n[dim]Full details → accounts.txt[/]")
    Prompt.ask("\n[dim]Press Enter[/]", default="")


def main():
    while True:
        banner()
        show_stats()
        console.print("[bold]Choose:[/]")
        console.print("  [cyan]1[/] → Create (Email)")
        console.print("  [cyan]2[/] → Create (Phone)")
        console.print("  [cyan]3[/] → Bulk Create")
        console.print("  [cyan]4[/] → Proxies")
        console.print("  [cyan]5[/] → View Accounts")
        console.print("  [cyan]0[/] → Exit")

        choice = Prompt.ask("\n[bold]Select[/]", choices=["0","1","2","3","4","5"])

        if choice == "0":
            console.print("\n[dim]Goodbye![/]")
            sys.exit(0)
        elif choice == "1": create_single_account("email")
        elif choice == "2": create_single_account("phone")
        elif choice == "3": bulk_create()
        elif choice == "4": manage_proxies()
        elif choice == "5": view_accounts()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Interrupted[/]")
        sys.exit(0)
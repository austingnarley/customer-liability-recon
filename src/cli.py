from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from dateutil.parser import isoparse
from rich.console import Console
from rich.table import Table

from src.ledger import generate_ledger
from src.reconcile import ReconciliationRow, reconcile
from src.report import render_html, render_xlsx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "data" / "customer_ledger.csv"
DEFAULT_WALLETS = ROOT / "config" / "wallets.yaml"
DEFAULT_PRICES = ROOT / "data" / "price_snapshots.csv"
DEFAULT_OUTPUT = ROOT / "output"
console = Console()


def main(argv: list[str] | None = None) -> int:
    _load_env_file(ROOT / ".env")
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Customer liability reserve coverage reconciliation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate-ledger", help="Generate the synthetic customer ledger")
    gen.add_argument("--customers", type=int, default=100)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--as-of", type=_parse_date, default=date.today())
    gen.set_defaults(func=_generate_ledger_command)

    recon = subparsers.add_parser("reconcile", help="Run reconciliation and print the summary")
    recon.add_argument("--as-of", type=_parse_date, default=date.today())
    recon.set_defaults(func=_reconcile_command)

    report = subparsers.add_parser("report", help="Render HTML and/or Excel reports")
    report.add_argument("--as-of", type=_parse_date, default=date.today())
    report.add_argument("--format", choices=["html", "xlsx", "both"], default="both")
    report.set_defaults(func=_report_command)

    demo = subparsers.add_parser(
        "demo",
        help="Generate ledger, run reconciliation, and render reports",
    )
    demo.add_argument("--as-of", type=_parse_date, default=date.today())
    demo.set_defaults(func=_demo_command)
    return parser


def _generate_ledger_command(args: argparse.Namespace) -> None:
    generate_ledger(
        customers=args.customers,
        seed=args.seed,
        as_of=args.as_of,
        out_path=DEFAULT_LEDGER,
    )
    console.print(f"[green]Generated synthetic ledger:[/] {DEFAULT_LEDGER}")


def _reconcile_command(args: argparse.Namespace) -> list[ReconciliationRow]:
    with console.status("Fetching reserve balances and reconciling...", spinner="dots"):
        rows = reconcile(DEFAULT_LEDGER, DEFAULT_WALLETS, DEFAULT_PRICES)
    _print_summary(rows)
    return rows


def _report_command(args: argparse.Namespace) -> None:
    rows = _reconcile_command(args)
    _render_requested_reports(rows, args.as_of, args.format)


def _demo_command(args: argparse.Namespace) -> None:
    generate_ledger(customers=100, seed=42, as_of=args.as_of, out_path=DEFAULT_LEDGER)
    console.print(f"[green]Generated synthetic ledger:[/] {DEFAULT_LEDGER}")
    rows = _reconcile_command(args)
    _render_requested_reports(rows, args.as_of, "both")


def _render_requested_reports(
    rows: list[ReconciliationRow],
    as_of: date,
    report_format: str,
) -> None:
    stem = DEFAULT_OUTPUT / f"recon_{as_of.isoformat()}"
    if report_format in {"html", "both"}:
        html_path = stem.with_suffix(".html")
        render_html(rows, as_of, html_path, ledger_path=DEFAULT_LEDGER, prices_path=DEFAULT_PRICES)
        console.print(f"[green]Rendered HTML report:[/] {html_path}")
    if report_format in {"xlsx", "both"}:
        xlsx_path = stem.with_suffix(".xlsx")
        render_xlsx(rows, as_of, xlsx_path, ledger_path=DEFAULT_LEDGER, prices_path=DEFAULT_PRICES)
        console.print(f"[green]Rendered Excel report:[/] {xlsx_path}")


def _print_summary(rows: list[ReconciliationRow]) -> None:
    table = Table(title="Coverage Summary")
    table.add_column("Asset")
    table.add_column("Liabilities", justify="right")
    table.add_column("Reserves", justify="right")
    table.add_column("Coverage", justify="right")
    table.add_column("Status", justify="center")
    for row in rows:
        coverage = "n/a" if row.coverage_ratio is None else f"{row.coverage_ratio * 100:.3f}%"
        liability = _format_asset_balance(row.customer_liabilities, row.asset)
        reserves = _format_asset_balance(row.on_chain_reserves, row.asset)
        table.add_row(
            row.asset,
            liability,
            reserves,
            coverage,
            row.status,
        )
    console.print(table)


def _format_asset_balance(value: Decimal, asset: str) -> str:
    return f"{value:,.8f}" if asset in {"BTC", "ETH"} else f"{value:,.2f}"


def _parse_date(value: str) -> date:
    return isoparse(value).date()


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    sys.exit(main())

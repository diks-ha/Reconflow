"""Seed roles and optionally create a user from command-line arguments."""
import argparse
from datetime import date, timedelta
from decimal import Decimal
from getpass import getpass
from hashlib import sha256

from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.role import Role
from app.models.user import User, UserRole
from app.models.finance import CodRemittance, FreightInvoice, Order, RateCard, RateCardHistory, ReturnRecord, Settlement
from app.models.import_record import ImportRecord
from app.models.partner import Partner
from app.reconciliation.imports import load_reconciliation_inputs
from app.reconciliation.service import execute_and_persist

ROLES = {
    "FINANCE_EXECUTIVE": "Finance Executive",
    "FINANCE_COFOUNDER": "Finance Co-founder",
}


def seed(email: str | None = None, password: str | None = None, full_name: str | None = None, role_name: str | None = None) -> None:
    if email and (password is None or len(password) < 12 or len(password.encode("utf-8")) > 72):
        raise ValueError("Seeded account passwords must be 12+ characters and at most 72 UTF-8 bytes")
    with SessionLocal.begin() as db:
        role_rows: dict[str, Role] = {}
        for name, description in ROLES.items():
            role = db.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, description=description)
                db.add(role)
                db.flush()
            role_rows[name] = role
        if email:
            normalized = email.strip().lower()
            user = db.scalar(select(User).where(User.email == normalized))
            if user is None:
                user = User(email=normalized, full_name=full_name or normalized.split("@")[0], password_hash=hash_password(password or ""))
                db.add(user)
                db.flush()
            selected_role = role_rows[role_name or "FINANCE_EXECUTIVE"]
            exists = db.scalar(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == selected_role.id))
            if exists is None:
                db.add(UserRole(user_id=user.id, role_id=selected_role.id))


def seed_demo_finance(email: str) -> None:
    """Load fictional, labeled sample records and run the actual reconciliation pipeline."""
    run_import_ids = []
    user_id = None
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            raise ValueError("Create the demo account first")
        if db.scalar(select(Order.id).where(Order.order_id == "ORD-W-204118")):
            print("Illustrative finance data already exists; skipping")
            return
        user_id = user.id

        website = Partner(name="ReconFlow Demo Website", partner_type="WEBSITE")
        marketplace = Partner(name="ReconFlow Demo Marketplace 1", partner_type="MARKETPLACE")
        courier = Partner(name="ReconFlow Demo Courier A", partner_type="COURIER")
        db.add_all([website, marketplace, courier])
        db.flush()

        def imported(name: str, partner: Partner, report_type: str, row_count: int) -> ImportRecord:
            return ImportRecord(
                uploaded_by=user.id, partner_id=partner.id, report_type=report_type,
                original_filename=name, storage_key=f"illustrative://reconflow/{name}",
                file_hash=sha256(name.encode()).hexdigest(), file_size=0, file_format="csv",
                status="PROCESSED", headers=[], preview_rows=[], row_count=row_count,
            )

        orders_web = imported("illustrative_demo_website_orders.csv", website, "orders", 2)
        orders_market = imported("illustrative_demo_marketplace_orders.csv", marketplace, "orders", 1)
        cod_file = imported("illustrative_demo_cod_remittances.csv", website, "cod_remittance", 1)
        settlement_file = imported("illustrative_demo_marketplace_settlements.csv", marketplace, "marketplace_settlement", 2)
        freight_file = imported("illustrative_demo_courier_freight.csv", courier, "courier_freight_invoice", 1)
        db.add_all([orders_web, orders_market, cod_file, settlement_file, freight_file])
        db.flush()

        demo_rate_card = RateCard(channel="Marketplace 1", courier_partner=courier.name, min_weight=Decimal("0"),
                     max_weight=Decimal("1"), forward_fee=Decimal("55.00"), return_fee=Decimal("60.00"),
                     cod_fee=Decimal("15.00"), fixed_charge=Decimal("2.00"), percentage_charge=Decimal("0.0000"),
                     effective_from=date.today() - timedelta(days=365), is_active=True,
                     source_note="Illustrative sample rate; not a client courier tariff", created_by=user.id,
                     version_number=1)
        db.add_all([
            Order(order_id="ORD-W-204118", partner_id=website.id, channel="Website", payment_method="COD",
                  delivery_status="Delivered", order_value=Decimal("1499.00"), expected_amount=Decimal("1409.00"),
                  payment_eligible=True, raw_source={"sample": True, "label": "Illustrative client example"},
                  source_import_id=orders_web.id, source_row_number=2),
            Order(order_id="ORD-W-204377", partner_id=website.id, channel="Website", payment_method="Prepaid",
                  delivery_status="Returned to warehouse", order_value=Decimal("2398.00"), expected_amount=Decimal("-96.00"),
                  return_status="Returned to warehouse", return_id="RET-DEMO-204377", return_deadline=date.today() - timedelta(days=12),
                  raw_source={"sample": True, "label": "Illustrative client example"},
                  source_import_id=orders_web.id, source_row_number=3),
            Order(order_id="ORD-M-88120", partner_id=marketplace.id, channel="Marketplace 1", payment_method="Prepaid",
                  delivery_status="Delivered", order_value=Decimal("1199.00"), expected_amount=Decimal("899.00"),
                  payment_eligible=True, raw_source={"sample": True, "label": "Illustrative client example"},
                  source_import_id=orders_market.id, source_row_number=2),
        ])
        db.add(ReturnRecord(partner_id=website.id, order_id="ORD-W-204377", return_id="RET-DEMO-204377",
                            return_status="Returned to warehouse", deadline=date.today() - timedelta(days=12),
                            source_import_id=orders_web.id, source_row_number=3,
                            raw_source={"sample": True, "label": "Illustrative return without warehouse scan"}))
        db.add_all([
            CodRemittance(partner_id=website.id, order_id="ORD-W-204118", transaction_id="COD-DEMO-204118",
                          amount=Decimal("0.00"), source_import_id=cod_file.id, source_row_number=2,
                          raw_source={"sample": True, "received_amount": "0.00"}),
            Settlement(partner_id=marketplace.id, order_id="ORD-M-88120", transaction_id="SET-DEMO-88120",
                       amount=Decimal("862.00"), gst_tcs=Decimal("2.40"), income_tax_tds=Decimal("1.20"),
                       source_import_id=settlement_file.id, source_row_number=2,
                       raw_source={"sample": True, "received_amount": "862.00"}),
            Settlement(partner_id=website.id, order_id="ORD-W-204377", transaction_id="REF-DEMO-204377",
                       amount=Decimal("-142.00"), source_import_id=settlement_file.id, source_row_number=3,
                       raw_source={"sample": True, "received_amount": "-142.00"}),
            FreightInvoice(partner_id=courier.id, order_id="ORD-M-88120", transaction_id="FRT-DEMO-88120",
                           tracking_id="AWB-DEMO-88120", courier_partner=courier.name,
                           billed_charge=Decimal("78.00"), weight=Decimal("0.500"),
                           source_import_id=freight_file.id, source_row_number=2,
                           raw_source={"sample": True, "freight_charge": "78.00"}),
            demo_rate_card,
        ])
        db.flush()
        db.add(RateCardHistory(
            rate_card_id=demo_rate_card.id, version_number=1, changed_by=user.id,
            snapshot={"channel": demo_rate_card.channel, "courier_partner": demo_rate_card.courier_partner,
                      "min_weight": str(demo_rate_card.min_weight), "max_weight": str(demo_rate_card.max_weight),
                      "forward_fee": str(demo_rate_card.forward_fee), "return_fee": str(demo_rate_card.return_fee),
                      "cod_fee": str(demo_rate_card.cod_fee), "fixed_charge": str(demo_rate_card.fixed_charge),
                      "percentage_charge": str(demo_rate_card.percentage_charge),
                      "effective_from": demo_rate_card.effective_from.isoformat(), "effective_to": None,
                      "is_active": True, "source_note": demo_rate_card.source_note},
        ))
        db.flush()
        run_import_ids = [orders_web.id, orders_market.id, cod_file.id, settlement_file.id, freight_file.id]
    with SessionLocal() as db:
        user = db.get(User, user_id)
        run_inputs = load_reconciliation_inputs(db, run_import_ids, date.today(), Decimal("10.00"))
        execute_and_persist(db, user, run_inputs)
    print("Illustrative ReconFlow finance data and reconciliation results created")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email")
    parser.add_argument("--full-name")
    parser.add_argument("--role", choices=ROLES, default="FINANCE_EXECUTIVE")
    parser.add_argument("--demo-data", action="store_true", help="Seed fictional orders, transactions, rate cards and run reconciliation")
    args = parser.parse_args()
    password = None
    if args.email:
        password = getpass("New account password (minimum 12 characters): ")
        if len(password) < 12 or len(password.encode("utf-8")) > 72:
            parser.error("seeded passwords must be 12 or more characters and no more than 72 UTF-8 bytes")
    seed(args.email, password, args.full_name, args.role)
    if args.demo_data:
        if not args.email:
            parser.error("--demo-data requires --email for the account that owns the seed data")
        seed_demo_finance(args.email)
    else:
        print("Roles seeded" + (f"; user {args.email.strip().lower()} ensured" if args.email else ""))


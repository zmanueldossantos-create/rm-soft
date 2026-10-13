"""Point 10 (Histórico do custo): each entry that moves a product's average cost - a priced reception, a production
with a complete cost - keeps its unit cost and the cost before and after; an entry without a price is not part of
the history. The history shows the supplier of a reception, and the cheapest and dearest unit costs."""
import pytest

from app.models.movement_type import MovementDirection, MovementType
from app.models.product import Product, ProductType
from app.models.supplier import Supplier
from app.services.cost_history_service import get_cost_history
from app.services.movement_document_service import create_stock_movement_document
from app.services.recipe_service import set_recipe
from app.services.stock_service import produce_stock


@pytest.mark.asyncio
async def test_priced_receptions_and_a_production_make_the_history(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, warehouse_id = ctx["company"].id, ctx["activity_warehouse"].id
    flour = Product(company_id=company_id, code="MP-FAR", name="Farinha", vat_id=None, price=0, min_stock_threshold=0,
                    product_type=ProductType.BEM, is_raw_material=True, unit_of_measure_id=ctx["unit_un"].id)
    bread = Product(company_id=company_id, code="PAO", name="Pão", vat_id=ctx["vat_nor"].id, price=1000,
                    min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    supplier = Supplier(company_id=company_id, name="Moagem do Kikolo")
    entrada = MovementType(code="ENH", name="Receção", direction=MovementDirection.ENTRADA, is_auto=False)
    db.add_all([flour, bread, supplier, entrada])
    await db.commit()

    async def receive(quantity, price):
        await create_stock_movement_document(
            db, company_id, entrada.id, warehouse_id, supplier_id=supplier.id,
            lines_input=[{"product_id": flour.id, "quantity": quantity, "purchase_price": price, "sale_price": 0}],
        )
    await receive(50, 700)   # first cost: 700
    await receive(50, 800)   # (50 x 700 + 50 x 800) / 100 = 750
    await receive(10, 0)     # no price: the quantity enters, the cost and the history stay

    history = await get_cost_history(db, company_id, flour.id)
    assert [(e["kind"], e["quantity"], e["unit_cost"], e["cost_before"], e["cost_after"], e["change_pct"])
            for e in history["entries"]] == [
        ("RECEPCAO", 50.0, 800.0, 700.0, 750.0, 7.14),
        ("RECEPCAO", 50.0, 700.0, None, 700.0, None),
    ]
    first = history["entries"][-1]
    assert (first["supplier"], first["reference"]) == ("Moagem do Kikolo", f"ENH{first['date'].year}/1")
    assert (history["current_cost"], history["last_purchase_price"], history["min_unit_cost"], history["max_unit_cost"]) == \
        (750.0, 800.0, 700.0, 800.0)

    # bread made from 20 units of flour at 750: 15 000 / 60 = 250 per bread
    await set_recipe(db, company_id, bread.id, 60, [{"ingredient_product_id": flour.id, "quantity_per_batch": 20}])
    await produce_stock(db, company_id, warehouse_id, bread.id, 60)
    produced = (await get_cost_history(db, company_id, bread.id))["entries"]
    assert [(e["kind"], e["unit_cost"], e["cost_before"], e["cost_after"]) for e in produced] == [("PRODUCAO", 250.0, None, 250.0)]

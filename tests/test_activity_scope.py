"""An article offered in some activities only: a service or a product category keeps the activities whose tills offer
it (a Hotel service at the Receção only) - empty means every activity, as before; an activity of another company is
refused."""
import uuid

import pytest

from app.models.activity import Activity
from app.services.ownership import NotOwnedError
from app.services.product_category_service import create_product_category, update_product_category
from app.services.service_service import create_service, update_service


@pytest.mark.asyncio
async def test_services_and_categories_keep_their_activities(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity = ctx["company"].id, ctx["activity"]
    hotel = Activity(company_id=company_id, module_id=activity.module_id, name="Hotel teste")
    db.add(hotel)
    await db.commit()
    await db.refresh(hotel)

    service = await create_service(db, company_id, code="HOT-X", name="Serviço só do hotel", vat_id=ctx["vat_nor"].id,
                                   unit_of_measure_id=ctx["unit_un"].id, price=1000, activity_ids=[hotel.id, hotel.id])
    assert service.activity_ids == [hotel.id]  # no repeats
    service = await update_service(db, company_id, service.id, code="HOT-X", name="Serviço só do hotel",
                                   vat_id=ctx["vat_nor"].id, unit_of_measure_id=ctx["unit_un"].id, price=1000, activity_ids=[])
    assert service.activity_ids is None  # every activity again

    category = await create_product_category(db, company_id, "Pão teste", activity_ids=[activity.id])
    assert category.activity_ids == [activity.id]
    category = await update_product_category(db, company_id, category.id, "Pão teste", activity_ids=None)
    assert category.activity_ids is None

    with pytest.raises(NotOwnedError):  # an activity that is not the company's
        await create_product_category(db, company_id, "Outra", activity_ids=[uuid.uuid4()])

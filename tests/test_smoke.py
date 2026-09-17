"""
Smoke test - verifies the test infrastructure itself (DB connection, table
creation, the company_with_essentials fixture) works before writing real
feature tests on top of it.
"""


async def test_company_with_essentials_fixture_builds_correctly(db, company_with_essentials):
    setup = company_with_essentials
    assert setup["company"].id is not None
    assert setup["central_warehouse"].company_id == setup["company"].id
    assert setup["activity"].company_id == setup["company"].id
    assert setup["activity"].warehouse_id == setup["activity_warehouse"].id
    assert setup["vat_nor"].rate == 14
    assert setup["vat_red"].rate == 5
    assert setup["vat_ise"].rate == 0
    assert setup["gestor"].role.value == "GESTOR"

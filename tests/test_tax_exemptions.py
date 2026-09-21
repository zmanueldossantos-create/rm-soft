"""The official exemption table respects the SAF-T XSD limits (code M + 2 digits, reason 6 to 60 characters)."""
import re

from app.core.tax_exemptions import TAX_EXEMPTION_REASONS, is_official_exemption_code


def test_official_table_respects_the_xsd_limits():
    assert len(TAX_EXEMPTION_REASONS) == 39
    for code, reason in TAX_EXEMPTION_REASONS.items():
        assert re.fullmatch(r"M[0-9]{2}", code), code
        assert 6 <= len(reason) <= 60, (code, len(reason))


def test_known_official_texts_and_the_invalid_na_code():
    assert TAX_EXEMPTION_REASONS["M04"] == "IVA \u2013 Regime de Exclus\u00e3o"
    assert TAX_EXEMPTION_REASONS["M02"] == "Transmiss\u00e3o de bens e servi\u00e7os n\u00e3o sujeita"
    assert is_official_exemption_code("M11") and not is_official_exemption_code("NA") and not is_official_exemption_code(None)
"""The SAF-T rule of an exemption motive (XSD: code M + 2 digits, reason of 6 to 60 characters) guards the catalog,
the only source of the motives copied on exempt lines."""
import pytest

from app.services.catalog_service import ExemptionMotiveInvalidError, check_exemption_motive


def test_a_valid_official_motive_passes():
    check_exemption_motive("M11", "Isento nos termos da al\u00ednea b) do n\u00ba1 do artigo 12.\u00ba do CIVA")


@pytest.mark.parametrize("code", ["NA", "11", "M1", "M111", "", None])
def test_a_code_out_of_the_format_is_refused(code):
    with pytest.raises(ExemptionMotiveInvalidError, match="formato"):
        check_exemption_motive(code, "Isento nos termos da lei")


@pytest.mark.parametrize("name", ["Isen", "x" * 61])
def test_a_reason_out_of_the_xsd_length_is_refused(name):
    with pytest.raises(ExemptionMotiveInvalidError, match="entre 6 e 60"):
        check_exemption_motive("M11", name)

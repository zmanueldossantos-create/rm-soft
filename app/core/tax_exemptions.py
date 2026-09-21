"""
Official SAF-T (AO) tax exemption codes with their official reasons.

Source: the list the SAF-T(AO) XSD points to ("Consultar: github.com/assoft-portugal/SAF-T-AO/wiki/Tax-Exemption-Codes"),
cross-checked with the AGT-validated Kiami exports (M04 = "IVA - Regime de Exclusao"). The XSD requires the code to
match M + 2 digits and the reason to be 6 to 60 characters; both are mandatory on every 0% line. The AGT e-invoicing
API only takes the 3-character code. Texts are kept verbatim - the official list itself mixes "alinea" and "alinea"
with an accent - and written with unicode escapes so this file stays ASCII.
"""

TAX_EXEMPTION_REASONS: dict[str, str] = {
    "M00": "IVA \u2013 Regime Simplificado",
    "M02": "Transmiss\u00e3o de bens e servi\u00e7os n\u00e3o sujeita",
    "M04": "IVA \u2013 Regime de Exclus\u00e3o",
    "M10": "Isento nos termos da al\u00ednea a) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M11": "Isento nos termos da al\u00ednea b) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M12": "Isento nos termos da al\u00ednea c) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M13": "Isento nos termos da al\u00ednea d) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M14": "Isento nos termos da al\u00ednea e) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M15": "Isento nos termos da al\u00ednea f) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M16": "Isento nos termos da al\u00ednea g) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M17": "Isento nos termos da al\u00ednea h) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M18": "Isento nos termos da al\u00ednea i) do n\u00ba1 artigo 12.\u00ba do CIVA",
    "M19": "Isento nos termos da al\u00ednea j) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M20": "Isento nos termos da al\u00ednea k) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M21": "Isento nos termos da al\u00ednea l) do n\u00ba1 do artigo 12.\u00ba do CIVA",
    "M22": "Isento nos termos da al\u00ednea m) do artigo 12.\u00ba do CIVA",
    "M23": "Isento nos termos da al\u00ednea n) do artigo 12.\u00ba do CIVA",
    "M24": "Isento nos termos da al\u00ednea o) do artigo 12.\u00ba do CIVA",
    "M30": "Isento nos termos da al\u00ednea a) do artigo 15.\u00ba do CIVA",
    "M31": "Isento nos termos da al\u00ednea b) do artigo 15.\u00ba do CIVA",
    "M32": "Isento nos termos da al\u00ednea c) do artigo 15.\u00ba do CIVA",
    "M33": "Isento nos termos da al\u00ednea d) do artigo 15.\u00ba do CIVA",
    "M34": "Isento nos termos da al\u00ednea e) do artigo 15.\u00ba do CIVA",
    "M35": "Isento nos termos da al\u00ednea f) do artigo 15.\u00ba do CIVA",
    "M36": "Isento nos termos da al\u00ednea g) do artigo 15.\u00ba do CIVA",
    "M37": "Isento nos termos da al\u00ednea h) do artigo 15.\u00ba do CIVA",
    "M38": "Isento nos termos da al\u00ednea i) do artigo 15.\u00ba do CIVA",
    "M80": "Isento nos termos da alinea a) do n\u00ba1 do artigo 14.\u00ba",
    "M81": "Isento nos termos da alinea b) do n\u00ba1 do artigo 14.\u00ba",
    "M82": "Isento nos termos da alinea c) do n\u00ba1 do artigo 14.\u00ba",
    "M83": "Isento nos termos da alinea d) do n\u00ba1 do artigo 14.\u00ba",
    "M84": "Isento nos termos da al\u00ednea e) do n\u00ba1 do artigo 14.\u00ba",
    "M85": "Isento nos termos da alinea a) do n\u00ba2 do artigo 14.\u00ba",
    "M86": "Isento nos termos da alinea b) do n\u00ba2 do artigo 14.\u00ba",
    "M90": "Isento nos termos da alinea a) do n\u00ba1 do artigo 16.\u00ba",
    "M91": "Isento nos termos da alinea b) do n\u00ba1 do artigo 16.\u00ba",
    "M92": "Isento nos termos da alinea c) do n\u00ba1 do artigo 16.\u00ba",
    "M93": "Isento nos termos da alinea d) do n\u00ba1 do artigo 16.\u00ba",
    "M94": "Isento nos termos da alinea e) do n\u00ba1 do artigo 16.\u00ba",
}


def is_official_exemption_code(code: str | None) -> bool:
    """True for a code of the official list - the only ones the SAF-T (and the AGT API) accept."""
    return code in TAX_EXEMPTION_REASONS
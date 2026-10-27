"""
The RM SOFT public key that checks the licences (app/core/license.py) - written once by
`python -m app.tools.license_keys`, then committed. Public: it only checks; the private key that signs stays in the
platform's .env (LICENSE_PRIVATE_KEY). Changing it makes every licence already issued invalid.
"""
PUBLIC_KEY = "_HxpFmH4wyoUkoPGxGJojve1htleqUCMWO2Vq8VTHqs"

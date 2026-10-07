# ERP Multisecteurs — Angola

ERP modulaire pour PME angolaises (Hotel, Boulangerie, Bar, Restauration, Alimentation),
conforme au regime fiscal RGIFT 2.0 (AGT).

Architecture hybride v7 : une seule base de code backend, deployable en Mode A (local,
Docker installe par notre equipe ou .exe autonome) ou Mode B (SaaS, VPS, multi-tenant).

## Prerequis
- Python 3.11.9
- PostgreSQL 16
- Redis
- Docker + Docker Compose (mode recommande)

## Installation locale (developpement, Windows)

1. Installer Python 3.11.9 (installeur officiel, cocher Add to PATH + for all users)
2. Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
3. python -m venv venv
4. venv\Scripts\activate
5. pip install -r requirements.txt

### Note environnements avec antivirus a inspection SSL (ex. Kaspersky)

Si pip echoue avec une erreur SSLCertVerificationError / self-signed certificate,
l antivirus intercepte le trafic HTTPS. Deux options :
- Desactiver temporairement l inspection des connexions chiffrees de l antivirus
- Ou exporter le certificat racine de l antivirus et l ajouter a la fin de :
  venv\Lib\site-packages\certifi\cacert.pem
  venv\Lib\site-packages\pip\_vendor\certifi\cacert.pem

A confirmer definitivement laquelle des deux methodes est necessaire sur ce poste.

## Authentification
Connexion par numero de telephone (format +244...), pas par email.

## Structure du projet
Voir cahier des charges v7, section 2.9.

Confidentiel - Usage interne - Conforme RGIFT 2.0 / AGT

# RM SOFT — Installation du service hébergé (SaaS)

Ce document est destiné à l'équipe RM SOFT. Le client ne touche jamais au serveur.

Une seule machine (VPS) fait tourner tout le service :

| Conteneur | Rôle |
|---|---|
| `web` | Caddy : sert les écrans, donne à chaque adresse son certificat HTTPS, passe `/api` et `/uploads` au backend. **Le seul ouvert sur Internet (ports 80 et 443).** |
| `backend` | L'API FastAPI. Met la base à jour (`alembic upgrade head`) à chaque démarrage. |
| `worker` | Celery : envoi des factures à l'AGT. |
| `postgres` | La base de données (jamais accessible depuis Internet). |
| `redis` | La file d'envoi AGT. |
| `backup` | Une copie de la base et des fichiers par jour, gardée 14 jours. |

## 1. Ce qu'il faut avant

- Un VPS Linux (Ubuntu 22.04 ou 24.04), au minimum 2 processeurs, 4 Go de mémoire et 40 Go de disque.
- Docker et Docker Compose installés : `curl -fsSL https://get.docker.com | sh`.
- Le domaine (ex. `rmsystem.co.ao`). Chez son gestionnaire, **deux lignes DNS**, une seule fois :
  - `*.rmsystem.co.ao` → type A → l'adresse IP du VPS ;
  - `rmsystem.co.ao` → type A → l'adresse IP du VPS (pour le futur site).
- Les ports 80 et 443 ouverts dans le pare-feu du VPS, et tous les autres fermés, sauf SSH.

Il n'y a rien à créer chez l'hébergeur pour chaque entreprise : une entreprise créée dans Empresas est en ligne tout de suite.

## 2. Installer

```bash
git clone https://github.com/zmanueldossantos-create/rm-soft.git /opt/rmsoft
cd /opt/rmsoft
cp docker/saas/.env.saas.example docker/saas/.env.saas
nano docker/saas/.env.saas
```

Dans `.env.saas` :
- `POSTGRES_PASSWORD` : un long mot de passe.
- `JWT_SECRET_KEY` : générer **une seule fois** avec `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
  **Ne jamais le changer ensuite** : les sessions seraient fermées, et les secrets gardés dans la base (clé IA, mots de passe d'email, token du bot) deviendraient illisibles.
- `ACME_EMAIL` : l'email qui reçoit les avertissements des certificats.
- `BACKUP_DIR` : le dossier des sauvegardes sur le VPS (ex. `/srv/rmsoft-backups`).

Démarrer :
```bash
docker compose -f docker/saas/docker-compose.saas.yml --env-file docker/saas/.env.saas up -d --build
docker compose -f docker/saas/docker-compose.saas.yml --env-file docker/saas/.env.saas ps
```
Tous les conteneurs doivent être `running`, et le backend `healthy`.

## 3. Premier accès

1. Créer le compte SUPER_ADMIN, une seule fois :
   ```bash
   docker compose -f docker/saas/docker-compose.saas.yml --env-file docker/saas/.env.saas exec backend python -m app.cli create-superadmin
   ```
   Le script demande le nom, le téléphone (`+244…`) et le mot de passe.
2. Ouvrir `https://admin.rmsystem.co.ao`. La première visite prend quelques secondes, le temps d'obtenir le certificat.
3. Configurações : renseigner l'identification du logiciel (n.º de validação AGT…), l'assistant IA et le bot Telegram. En SaaS, le bot est relié automatiquement : Telegram appelle `https://admin.rmsystem.co.ao/api/v1/channels/telegram/webhook`.
4. Empresas → Nova empresa. L'adresse de l'entreprise (ex. `farmacia-da-luz.rmsystem.co.ao`) fonctionne tout de suite.

## 4. Mettre à jour

```bash
cd /opt/rmsoft
git pull
docker compose -f docker/saas/docker-compose.saas.yml --env-file docker/saas/.env.saas up -d --build
```
Le backend applique lui-même les migrations au démarrage. Faire une sauvegarde manuelle avant une grosse mise à jour (voir 5).

## 5. Sauvegardes

- Une fois par jour, dans `BACKUP_DIR` : `rmsoft_db_<date>.dump` (la base) et `rmsoft_uploads_<date>.tar.gz` (les logos et les images).
- Dans `BACKUP_DIR/empresas/<id de l'entreprise>/` : les **copies de chaque entreprise** (automatiques aux heures choisies par son gestor, ou manuelles), gardées 7 jours puis une par semaine pendant 4 semaines. Elles se voient dans Empresas → « Cópias de segurança » ; une copie se restaure avec « Restaurar empresa ».
- **Copier ce dossier ailleurs** (un autre serveur, un stockage externe). Une sauvegarde qui reste sur le même VPS ne protège pas d'une panne du VPS.
- Sauvegarde immédiate : `docker compose ... restart backup` (il en fait une au démarrage).

Restaurer la base, par exemple sur un VPS neuf :
```bash
docker compose ... up -d postgres
docker compose ... exec -T postgres pg_restore -U rmsoft -d rmsoft --clean --if-exists < /srv/rmsoft-backups/rmsoft_db_<date>.dump
```
Restaurer les fichiers :
```bash
docker run --rm -v rmsoft_uploads:/uploads -v /srv/rmsoft-backups:/b alpine tar -xzf /b/rmsoft_uploads_<date>.tar.gz -C /uploads
```
Puis `docker compose ... up -d`.

## 6. Au quotidien

- Journaux : `docker compose ... logs -f backend` (ou `worker`, `web`).
- Suspendre une entreprise : Empresas, désactiver. Personne ne peut plus s'y connecter, et ses sessions ouvertes se terminent en moins de 30 minutes.
- Une adresse inventée (ex. `nimporte-quoi.rmsystem.co.ao`) n'obtient jamais de certificat : Caddy demande d'abord au backend si elle existe.

## 7. Sécurité, à vérifier à l'installation

- [ ] `.env.saas` lisible seulement par root (`chmod 600`), jamais commité dans git.
- [ ] Pare-feu : seulement 22, 80 et 443.
- [ ] Connexion SSH par clé, mot de passe désactivé.
- [ ] Sauvegardes copiées hors du VPS.
- [ ] `JWT_SECRET_KEY` noté dans un coffre (gestionnaire de mots de passe) : sans lui, une restauration ne peut pas relire les secrets.

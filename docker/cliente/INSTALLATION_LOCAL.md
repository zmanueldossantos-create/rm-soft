# RM SOFT — Installation chez un client (serveur local)

Ce document est destiné au **technicien RM SOFT**. Le client ne touche jamais au serveur.

RM SOFT est installé **sur une seule machine : le serveur**. Les postes du magasin (caisse, bureau…) n'installent
rien : ils ouvrent RM SOFT dans Chrome. Internet n'est nécessaire que pour l'envoi des factures à l'AGT ; sans
internet tout fonctionne et les factures partent au retour de la connexion.

```
              Internet (AGT)
                    │
              [ Routeur ]
                    │
        ┌───────────┼───────────┐
   [ SERVEUR ]   [ Poste 1 ]  [ Poste 2 ]
   RM SOFT        Chrome       Chrome
   base, copies   (Caixa)      (Gestor)
   licence .lic
```

| Conteneur | Rôle |
|---|---|
| `web` | Les écrans, sur le réseau du magasin (`http://rmsoft.local`, port 80). |
| `backend` | L'API. Met la base à jour à chaque démarrage. Lit la **licence**. |
| `worker` | L'envoi des factures à l'AGT (file d'attente). |
| `postgres` | La base de données (jamais visible depuis le réseau). |
| `redis` | La file d'envoi AGT. |
| `backup` | Une copie de toute la base par jour (gardée 14 jours). |

Les **copies de chaque entreprise** (Definições da Empresa → Cópias de segurança) vont aussi dans le dossier des copies.

---

## 1. Matériel

- **Serveur** : mini-PC ou PC de bureau, 8 Go de mémoire, disque SSD 256 Go, branché sur un **onduleur**.
- **Disque externe** (ou dossier réseau / NAS) pour les copies — jamais seulement le disque du serveur.
- Dans le routeur : une **adresse IP fixe** pour le serveur (réservation DHCP), ex. `192.168.1.10`.
- Câble réseau pour le serveur (pas le Wi-Fi).

Trois façons d'installer le serveur :

| | **Windows : RMSOFT-Setup.exe** (le plus simple) | **Ubuntu Server** | **Windows + Docker Desktop** |
|---|---|---|---|
| Coût | licence Windows | gratuit | licence Windows |
| Démarrage après coupure | RM SOFT redémarre seul (services Windows) | RM SOFT redémarre seul | il faut l'ouverture de session automatique de Windows |
| Code source sur le serveur | non | oui | oui |
| Installation | double-clic | `sudo ./instalar.sh` | `.\instalar.ps1` (administrateur) |

---

## 2. Installation — serveur Windows avec RMSOFT-Setup.exe

Le fichier `RMSOFT-Setup-<version>.exe` (fabriqué par RM SOFT, voir section 8) sur une clé USB.

1. Sur le serveur (Windows 10/11 ou Windows Server, 64 bits), double-cliquer `RMSOFT-Setup-<version>.exe`.
   Si Windows affiche « Windows a protégé votre ordinateur » : **Informations complémentaires → Exécuter quand même**.
   Répondre **Oui** à la demande d'administrateur.
2. Les questions : le **port** (laisser 80), le **dossier des copies** (le disque externe, ex. `E:\RMSOFT\copias`),
   le **compte SUPER_ADMIN** (nom, téléphone `+244…`, mot de passe).
3. **Instalar** → l'installation configure la base de données et les services (quelques minutes).
4. Le dernier écran affiche les **adresses des postes** et le **code d'installation** (aussi dans
   `C:\ProgramData\RMSOFT\codigo_instalacao.txt`). Une icône **RM SOFT** est sur le bureau du serveur.

Ce qui est installé :

| | |
|---|---|
| `C:\Program Files\RMSOFT` | le programme (sans code source) |
| `C:\ProgramData\RMSOFT` | les données : base, `.env`, logos, journaux (`logs\`) — gardées à la désinstallation |
| Service **RMSOFT-BaseDados** | la base de données (PostgreSQL, accessible depuis ce PC seulement) |
| Service **RMSOFT-Servidor** | les écrans, l'API, l'envoi AGT, les copies automatiques |
| Tâche **RMSOFT-CopiaBase** | une copie de toute la base chaque jour à 23:30 dans `<dossier des copies>\base` (14 jours) |

**Mise à jour** : lancer le nouveau `RMSOFT-Setup-<version>.exe` sur le serveur. Aucune question : il copie d'abord
toute la base (`<dossier des copies>\base\antes_atualizacao_….dump`), remplace le programme, met la base à jour et
redémarre. Sur les postes : Ctrl+F5.

## 2 bis. Installation — serveur Ubuntu

1. Installer **Ubuntu Server 24.04** (option « OpenSSH server » cochée), brancher le disque des copies.
2. Copier RM SOFT sur le serveur :
   ```bash
   sudo git clone https://github.com/zmanueldossantos-create/rm-soft.git /opt/rmsoft
   ```
   (sans internet : copier le dossier depuis une clé USB vers `/opt/rmsoft`)
3. Lancer l'installation :
   ```bash
   cd /opt/rmsoft/docker/cliente
   sudo ./instalar.sh
   ```
   Le script demande : le nom du client, le dossier des copies (ex. `/media/copias` pour le disque externe), le
   port (laisser 80), puis le **téléphone et le mot de passe du SUPER_ADMIN RM SOFT** de ce serveur.
4. À la fin il affiche les adresses des postes et le **code d'installation** (ex. `3F2A-91C0-7B4E-D218`).

## 2 ter. Installation — serveur Windows avec Docker Desktop

1. Installer **Docker Desktop** (https://www.docker.com/products/docker-desktop), l'ouvrir une fois, attendre
   « Engine running ». Dans Settings → General : cocher **Start Docker Desktop when you sign in**.
2. Configurer l'**ouverture de session automatique** de Windows (sinon, après une coupure de courant, RM SOFT ne
   redémarre qu'à la connexion d'un utilisateur).
3. Copier RM SOFT dans `C:\RMSOFT\rm-soft` (git clone ou clé USB).
4. Ouvrir **PowerShell en administrateur** :
   ```powershell
   cd C:\RMSOFT\rm-soft\docker\cliente
   Set-ExecutionPolicy -Scope Process Bypass
   .\instalar.ps1
   ```
   Mêmes questions que sous Ubuntu (dossier des copies, ex. `D:/RMSOFT/copias`). Le script ouvre le port dans le
   pare-feu Windows et affiche le **code d'installation**.

---

## 3. Licence

1. Sur **la plateforme RM SOFT** : Empresas → l'entreprise du client → **Contrato** → contrat avec
   *Instalação : Local* → coller le code d'installation → **Gerar licença** → le fichier `.lic` se télécharge.
2. Sur **le serveur du client** (depuis un poste) : se connecter en SUPER_ADMIN → Empresas → créer l'entreprise
   (ou **Restaurar empresa** avec sa copie) → onglet **Licença** → importer le `.lic`.
   Le gestor peut aussi l'importer lui-même : Definições da Empresa → Licença (renouvellements).

Sans licence valide : tout fonctionne 7 jours, puis lecture seule (consulter, SAF-T et copies restent possibles).

---

## 4. Les postes (caisse, bureau)

Rien à installer. Dans **Chrome** :
1. Ouvrir `http://rmsoft.local` (Ubuntu) ou `http://NOMDUSERVEUR` (Windows) — sinon l'adresse IP affichée par le
   script, ex. `http://192.168.1.10`.
2. Menu ⋮ → **Caster, enregistrer et partager → Créer un raccourci…** → cocher **Ouvrir dans une fenêtre** → Créer.
   Une icône RM SOFT apparaît sur le bureau ; l'application s'ouvre dans sa propre fenêtre.
3. Chaque utilisateur se connecte avec son téléphone et son mot de passe.
4. Imprimantes : branchées sur le poste comme d'habitude ; faire une vente test (ticket et A4).

---

## 5. Vérifier avant de partir

- [ ] Une vente test, imprimée.
- [ ] La facture est **ENVIADA** à l'AGT (ou en file si pas d'internet).
- [ ] Definições da Empresa → Cópias de segurança : **Fazer cópia agora**, et la copie est bien dans le dossier des
      copies (sous `empresas/`). Mettre les copies automatiques (ex. 13:00 et 23:00).
- [ ] Redémarrer le serveur : RM SOFT revient seul (Windows : après l'ouverture de session automatique).
- [ ] Noter dans la fiche client : l'adresse IP, le code d'installation, l'emplacement des copies.

---

## 6. Mises à jour (dont les changements AGT)

RMSOFT-Setup.exe : lancer le nouveau setup sur le serveur (voir section 2).
Ubuntu : `cd /opt/rmsoft/docker/cliente && sudo ./atualizar.sh`
Windows : `.\atualizar.ps1` (PowerShell administrateur)

Le script fait d'abord une copie de la base (`antes_atualizacao_….dump`), prend la version nouvelle, reconstruit et
redémarre. Les données restent ; la base se met à jour seule. Sur les postes : Ctrl+F5.

---

## 7. En cas de problème

| Situation | Que faire |
|---|---|
| RMSOFT-Setup.exe : voir l'état | `services.msc` → RMSOFT-BaseDados et RMSOFT-Servidor « En cours d'exécution » |
| RMSOFT-Setup.exe : messages d'erreur | `C:\ProgramData\RMSOFT\logs\` : `instalacao.log` (installation), `rmsoft-servico.out.log` / `.err.log` (serveur) |
| RMSOFT-Setup.exe : le port 80 est occupé | ouvrir `C:\ProgramData\RMSOFT\.env` (Bloc-notes en administrateur), `RMSOFT_PORT=8080`, relancer le setup |
| Docker : voir l'état | `docker compose -f docker-compose.yml ps` (dans `docker/cliente`) |
| Voir les messages d'erreur | `docker compose -f docker-compose.yml logs --tail 100 backend` |
| Tout redémarrer | `docker compose -f docker-compose.yml restart` |
| Le serveur est remplacé | nouvelle installation, **nouvelle licence** (le code change), puis **Restaurar empresa** avec la dernière copie (`empresas/`) |
| Un poste n'ouvre pas `rmsoft.local` | utiliser l'adresse IP ; vérifier que le poste est sur le même réseau |

(Sous Ubuntu, ajouter `-f docker-compose.linux.yml` après `-f docker-compose.yml`, et `sudo` devant.)

Ne jamais modifier `JWT_SECRET_KEY` dans `.env` : les secrets enregistrés deviendraient illisibles.
Ne jamais envoyer le fichier `.env` : il contient les mots de passe.

---

## 8. Fabriquer RMSOFT-Setup.exe (PC de développement RM SOFT)

Une fois : **Inno Setup 6** (https://jrsoftware.org/isdl.php) et Node.js. Puis, dans `C:\Projects\rm-system` :

```powershell
powershell -ExecutionPolicy Bypass -File instalador\fabricar_setup.ps1 -Versao 1.0.0
```

Résultat : `instalador\saida\RMSOFT-Setup-1.0.0.exe`. La 1re fois, le script télécharge PostgreSQL 16, WinSW et
Visual C++ dans `instalador\cache\` (gardés pour les fois suivantes). Changer `-Versao` à chaque livraison.

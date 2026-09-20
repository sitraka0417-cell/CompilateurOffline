# Compilateur Hors Ligne

Un logiciel Windows (interface graphique) qui compile un projet Python
(comme VoteMGR, ou n'importe quel autre script `.py`) en un exécutable
Windows `.exe`, **sans connexion Internet**.

Il s'agit d'une interface autour de [PyInstaller](https://pyinstaller.org/),
mais avec PyInstaller **intégré à l'intérieur** de l'exécutable produit,
pour ne dépendre d'aucune installation externe une fois construit.

## Ce que ça fait

1. **Importez un projet entier** en `.zip` (ex : votre projet VoteMGR
   zippé), ou ouvrez un dossier existant, ou partez d'un projet vide.
   L'arborescence complète s'affiche à gauche.
2. **Parcourez, ajoutez, supprimez, renommez ou modifiez** n'importe quel
   fichier directement dans l'appli (un double-clic ouvre le fichier
   dans l'éditeur intégré à droite ; Ctrl+S pour enregistrer).
3. **Désignez le script principal** (celui qui sera lancé au démarrage
   de l'exe) : sélectionnez-le puis cliquez « ⭐ Définir... ».
4. Réglez les options : nom de l'application, icône, fenêtrée/console,
   fichier unique ou dossier, dossiers de données à inclure (les
   dossiers de premier niveau comme `assets` sont détectés
   automatiquement à l'import).
5. Cliquez **Compiler** : le journal s'affiche en direct, et un `.exe`
   Windows est généré.
6. **Exportez le projet modifié en `.zip`** si vous voulez le garder ou
   le repartager, à tout moment.

Tout cela se passe en local, sur la machine, sans requête réseau.

## Construire le logiciel (à faire une fois, sur un PC avec Internet)

**Option A — localement :**

```bat
installer\preparer_hors_ligne.bat   REM télécharge PyInstaller dans vendor\
installer\build.bat                 REM compile CompilateurOffline.exe
```

Résultat : `dist\CompilateurOffline\` — copiez ce dossier entier (pas
seulement le `.exe`, PyInstaller a besoin des fichiers qui l'accompagnent)
sur une clé USB, un disque, ou n'importe quel autre PC Windows.

**Option B — via GitHub Actions (rien à installer chez vous) :**

1. Poussez ce dossier `compilateur_offline/` sur un dépôt GitHub.
2. Onglet **Actions** → le workflow « Build CompilateurOffline (Windows) »
   se lance automatiquement (ou lancez-le manuellement via
   *Run workflow*). Un serveur GitHub (qui a Internet) compile à votre
   place.
3. Une fois le run terminé (icône verte), ouvrez-le → section
   **Artifacts** en bas → téléchargez `CompilateurOffline-windows.zip`.
4. Dézippez : c'est l'équivalent exact de `dist\CompilateurOffline\`
   ci-dessus.

**Important à bien comprendre : Internet n'est nécessaire qu'à cette
étape de construction (A ou B), une seule fois. Une fois le dossier
`CompilateurOffline\` obtenu, son utilisation — y compris le tout
premier lancement — ne demande plus jamais de connexion.**

## Utiliser le logiciel (ensuite, sans Internet, sur n'importe quel PC)

1. Copiez le dossier `CompilateurOffline\` sur le PC cible.
2. Double-cliquez sur `CompilateurOffline.exe`.
3. Cliquez **📦 Importer un projet (.zip)** et choisissez votre archive
   (ex : `votemgr.zip`) — l'arborescence apparaît à gauche.
4. Sélectionnez `main.py` dans l'arbre, cliquez « ⭐ Définir la
   sélection comme script principal ».
5. (Optionnel) Modifiez des fichiers via l'éditeur, ajoutez-en, vérifiez
   que les dossiers de données détectés automatiquement (ex : `assets`)
   sont corrects dans la liste en bas.
6. Cliquez **▶ Compiler**. Le résultat apparaît dans le dossier de
   sortie indiqué ; **📂 Ouvrir le résultat** l'ouvre directement.

Aucun Python, aucun `pip`, aucune connexion réseau n'est nécessaire à
cette étape : tout ce qu'il fallait a été embarqué à la construction.

Les projets importés sont conservés dans
`%USERPROFILE%\CompilateurOffline\projets\` (chaque import crée un
nouveau sous-dossier horodaté, pour ne jamais écraser un import
précédent par erreur).

## Limites à connaître (important)

- **Ce compilateur cible les projets Python.** Il ne compile pas du
  C++/C#/etc. — c'est un compilateur "Python → .exe Windows", ce qui
  correspond à votre projet VoteMGR.
- **La technique consistant à embarquer PyInstaller dans un exécutable
  qu'il a lui-même produit** (`--collect-all PyInstaller`) fonctionne
  dans la plupart des cas mais reste plus fragile qu'une installation
  Python classique. **Testez-le avant de compter dessus** : compilez
  d'abord un petit script `.py` de test, sur une machine hors-ligne,
  pour vérifier que tout se passe bien sur ce PC précis.
- Si jamais cette méthode pose problème sur votre machine, la solution
  de repli fiable à 100% reste celle donnée pour VoteMGR : le dossier
  `vendor\` + `installer\build.bat` classique, qui nécessite Python
  installé sur la machine (une seule fois, avec l'installateur officiel
  téléchargé une fois pour toutes) mais ne demande plus jamais Internet
  ensuite.
- Le script à compiler doit être un projet Python "normal" (bibliothèque
  standard + paquets déjà installés sur le PC où vous lancez
  `installer\build.bat`, ou déclarés proprement). Un script qui a besoin
  d'un paquet non présent au moment de la compilation ne pourra pas être
  compilé.

## Structure

```
compilateur_offline/
  main.py                  interface graphique (Tkinter) + appel de PyInstaller en mémoire
  requirements.txt
  installer/
    preparer_hors_ligne.bat  télécharge PyInstaller une fois (avec Internet)
    build.bat                compile CompilateurOffline.exe (avec PyInstaller intégré)
```

# -*- coding: utf-8 -*-
"""
main.py — Compilateur Hors Ligne (avec explorateur de projet intégré)

Logiciel Windows : on importe un projet Python entier (fichier .zip),
son arborescence s'affiche, on peut ajouter/supprimer/modifier chaque
fichier directement dans l'appli, désigner le script principal, puis
compiler en .exe — le tout sans connexion Internet une fois PyInstaller
disponible (voir installer/build.bat).
"""

import os
import sys
import shutil
import zipfile
import datetime
import queue
import logging
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

TITRE = "Compilateur Hors Ligne — pour projets Python"

DOSSIER_PROJETS = os.path.join(os.path.expanduser("~"), "CompilateurOffline", "projets")

DOSSIERS_EXCLUS_ARBRE = {"__pycache__", "dist", "build", "vendor", "dist_compilations",
                          "_travail_temporaire", ".git", "Output"}
# En plus de ce qui précède, ces dossiers restent visibles/éditables dans
# l'arbre mais ne sont pas proposés automatiquement comme "données" à
# inclure dans l'exécutable (ce ne sont pas des fichiers utiles à l'exécution) :
DOSSIERS_EXCLUS_DONNEES = DOSSIERS_EXCLUS_ARBRE | {"installer", ".github", "app"}

EXTENSIONS_TEXTE = {
    ".py", ".txt", ".md", ".json", ".csv", ".ini", ".cfg", ".iss", ".bat",
    ".html", ".htm", ".css", ".js", ".yml", ".yaml", ".xml", ".sh", ".gitignore",
    ".vmgr",
}
EXTENSIONS_IMAGE = {".png", ".gif"}


class FluxVersFile:
    """Objet 'fichier' minimal : tout ce qu'on lui écrit part dans une
    queue.Queue, lue ensuite par l'interface graphique (thread-safe)."""

    def __init__(self, file_attente):
        self.file_attente = file_attente

    def write(self, texte):
        if texte:
            self.file_attente.put(texte)

    def flush(self):
        pass


class CompilateurApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITRE)
        self.geometry("1180x800")
        self.minsize(980, 680)

        # ---- état du projet ----
        self.dossier_projet = None       # dossier de travail (extrait du zip, ou choisi)
        self.chemin_relatif_principal = None   # ex: "main.py"
        self.chemin_fichier_edite = None       # chemin relatif du fichier actuellement ouvert

        # ---- état de la compilation ----
        self.var_nom = tk.StringVar()
        self.var_icone = tk.StringVar()
        self.var_mode = tk.StringVar(value="fenetre")
        self.var_un_seul_fichier = tk.BooleanVar(value=False)
        self.var_dossier_sortie = tk.StringVar(value=os.path.join(
            os.path.expanduser("~"), "Desktop", "dist_compilations"))
        self.var_script_principal = tk.StringVar(value="(aucun projet chargé)")

        self.donnees_supplementaires = []   # liste de (chemin_absolu, nom_destination)

        self._file_log = queue.Queue()
        self._compilation_en_cours = False

        self._construire_ui()
        self.after(100, self._lire_file_log)
        self.bind_all("<Control-s>", lambda e: self._enregistrer_fichier_edite())

    # ================= construction UI =================
    def _construire_ui(self):
        cadre = ttk.Frame(self, padding=12)
        cadre.pack(fill="both", expand=True)

        ttk.Label(cadre, text=TITRE, font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(cadre,
                  text="Importez un projet Python (.zip), modifiez ses fichiers si besoin, "
                       "puis compilez-le en .exe Windows — sans Internet.",
                  foreground="#555").pack(anchor="w", pady=(0, 10))

        # ---- barre projet ----
        barre_projet = ttk.Frame(cadre)
        barre_projet.pack(fill="x", pady=(0, 8))
        ttk.Button(barre_projet, text="📦 Importer un projet (.zip)",
                   command=self._importer_projet_zip).pack(side="left", padx=(0, 6))
        ttk.Button(barre_projet, text="🗂 Ouvrir un dossier de projet",
                   command=self._ouvrir_dossier_projet).pack(side="left", padx=(0, 6))
        ttk.Button(barre_projet, text="🆕 Nouveau projet vide",
                   command=self._nouveau_projet_vide).pack(side="left", padx=(0, 6))
        ttk.Button(barre_projet, text="💾 Exporter en .zip",
                   command=self._exporter_projet_zip).pack(side="left", padx=(0, 6))
        ttk.Button(barre_projet, text="📂 Ouvrir le dossier du projet",
                   command=self._ouvrir_dossier_dans_explorateur).pack(side="left")

        self.var_projet_actuel = tk.StringVar(value="Aucun projet chargé.")
        ttk.Label(cadre, textvariable=self.var_projet_actuel,
                  foreground="#1a3c6e", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))

        # ---- zone arbre + éditeur ----
        zone_principale = ttk.Panedwindow(cadre, orient="horizontal")
        zone_principale.pack(fill="both", expand=True, pady=(0, 10))

        # -- arbre --
        cadre_arbre = ttk.Frame(zone_principale)
        zone_principale.add(cadre_arbre, weight=1)

        boutons_arbre = ttk.Frame(cadre_arbre)
        boutons_arbre.pack(fill="x", pady=(0, 4))
        ttk.Button(boutons_arbre, text="📄 +Fichier", width=10,
                   command=self._nouveau_fichier).pack(side="left", padx=1)
        ttk.Button(boutons_arbre, text="📁 +Dossier", width=10,
                   command=self._nouveau_dossier).pack(side="left", padx=1)
        ttk.Button(boutons_arbre, text="📤 Importer", width=10,
                   command=self._importer_fichier_externe).pack(side="left", padx=1)
        ttk.Button(boutons_arbre, text="🗑 Supprimer", width=10,
                   command=self._supprimer_selection).pack(side="left", padx=1)
        ttk.Button(boutons_arbre, text="✏ Renommer", width=10,
                   command=self._renommer_selection).pack(side="left", padx=1)

        self.arbre = ttk.Treeview(cadre_arbre, show="tree")
        self.arbre.pack(fill="both", expand=True)
        self.arbre.bind("<<TreeviewSelect>>", self._on_selection_arbre)
        self.arbre.bind("<Double-1>", lambda e: self._definir_script_principal())

        ttk.Button(cadre_arbre, text="⭐ Définir la sélection comme script principal",
                   command=self._definir_script_principal).pack(fill="x", pady=(4, 0))

        # -- éditeur --
        cadre_editeur = ttk.Frame(zone_principale)
        zone_principale.add(cadre_editeur, weight=2)

        entete_editeur = ttk.Frame(cadre_editeur)
        entete_editeur.pack(fill="x")
        self.var_fichier_ouvert = tk.StringVar(value="Aucun fichier ouvert.")
        ttk.Label(entete_editeur, textvariable=self.var_fichier_ouvert,
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Button(entete_editeur, text="💾 Enregistrer (Ctrl+S)",
                   command=self._enregistrer_fichier_edite).pack(side="right")

        self.zone_editeur = tk.Text(cadre_editeur, wrap="none", undo=True,
                                     font=("Consolas", 10))
        self.zone_editeur.pack(fill="both", expand=True, pady=(4, 0))
        self.zone_editeur.configure(state="disabled")

        self.label_apercu_image = None  # créé à la volée pour les images

        # ---- options de compilation ----
        cadre_options = ttk.LabelFrame(cadre, text="Compilation")
        cadre_options.pack(fill="x", pady=(0, 8))

        ligne = ttk.Frame(cadre_options)
        ligne.pack(fill="x", pady=4, padx=6)
        ttk.Label(ligne, text="Script principal :", width=16).pack(side="left")
        ttk.Label(ligne, textvariable=self.var_script_principal,
                  foreground="#1a3c6e").pack(side="left", fill="x", expand=True)

        ligne = ttk.Frame(cadre_options)
        ligne.pack(fill="x", pady=4, padx=6)
        ttk.Label(ligne, text="Nom de l'application :", width=16).pack(side="left")
        ttk.Entry(ligne, textvariable=self.var_nom).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(ligne, text="Icône (.ico) :").pack(side="left", padx=(12, 4))
        ttk.Entry(ligne, textvariable=self.var_icone, width=30).pack(side="left")
        ttk.Button(ligne, text="...", width=3, command=self._choisir_icone).pack(side="left")

        ligne = ttk.Frame(cadre_options)
        ligne.pack(fill="x", pady=4, padx=6)
        ttk.Radiobutton(ligne, text="Fenêtrée (sans console)",
                        variable=self.var_mode, value="fenetre").pack(side="left", padx=(0, 16))
        ttk.Radiobutton(ligne, text="Console (fenêtre noire, pour déboguer)",
                        variable=self.var_mode, value="console").pack(side="left", padx=(0, 16))
        ttk.Checkbutton(ligne, text="Un seul fichier .exe",
                        variable=self.var_un_seul_fichier).pack(side="left")

        ligne = ttk.Frame(cadre_options)
        ligne.pack(fill="x", pady=4, padx=6)
        ttk.Label(ligne, text="Dossiers inclus (assets, etc.) :", width=26).pack(side="left")
        self.liste_donnees = tk.Listbox(ligne, height=3)
        self.liste_donnees.pack(side="left", fill="x", expand=True, padx=6)
        cadre_boutons_donnees = ttk.Frame(ligne)
        cadre_boutons_donnees.pack(side="left")
        ttk.Button(cadre_boutons_donnees, text="+", width=3,
                   command=self._ajouter_dossier_donnees_manuel).pack(pady=1)
        ttk.Button(cadre_boutons_donnees, text="－", width=3,
                   command=self._retirer_donnees).pack(pady=1)

        ligne = ttk.Frame(cadre_options)
        ligne.pack(fill="x", pady=4, padx=6)
        ttk.Label(ligne, text="Dossier de sortie :", width=16).pack(side="left")
        ttk.Entry(ligne, textvariable=self.var_dossier_sortie).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(ligne, text="Parcourir...", command=self._choisir_dossier_sortie).pack(side="left")

        ligne = ttk.Frame(cadre_options)
        ligne.pack(fill="x", pady=(6, 6), padx=6)
        self.bouton_compiler = ttk.Button(ligne, text="▶ Compiler", command=self._lancer_compilation)
        self.bouton_compiler.pack(side="left")
        self.bouton_ouvrir_resultat = ttk.Button(ligne, text="📂 Ouvrir le résultat",
                                                   command=self._ouvrir_dossier_resultat, state="disabled")
        self.bouton_ouvrir_resultat.pack(side="left", padx=8)
        self.var_statut = tk.StringVar(value="Prêt.")
        ttk.Label(ligne, textvariable=self.var_statut, foreground="#1a3c6e").pack(side="left", padx=12)

        # ---- journal ----
        ttk.Label(cadre, text="Journal de compilation :").pack(anchor="w")
        cadre_log = ttk.Frame(cadre)
        cadre_log.pack(fill="both", expand=False)
        self.zone_log = tk.Text(cadre_log, height=10, bg="#0b1220", fg="#d7e2f5",
                                 insertbackground="#d7e2f5", font=("Consolas", 9))
        self.zone_log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(cadre_log, command=self.zone_log.yview)
        scroll.pack(side="right", fill="y")
        self.zone_log.configure(yscrollcommand=scroll.set)

    # ================= gestion du projet (zip / dossier) =================
    def _charger_projet(self, dossier, nom_affiche):
        self.dossier_projet = dossier
        self.chemin_relatif_principal = None
        self.var_script_principal.set("(aucun script principal choisi — double-cliquez sur un .py)")
        self.var_projet_actuel.set("Projet actuel : %s  (%s)" % (nom_affiche, dossier))
        self._fermer_editeur()
        self._rafraichir_arbre()
        self._detecter_dossiers_donnees()
        if not self.var_nom.get():
            self.var_nom.set(nom_affiche)

    def _importer_projet_zip(self):
        chemin_zip = filedialog.askopenfilename(
            title="Importer un projet (.zip)", filetypes=[("Archive ZIP", "*.zip")])
        if not chemin_zip:
            return
        nom_base = os.path.splitext(os.path.basename(chemin_zip))[0]
        horodatage = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dossier_dest = os.path.join(DOSSIER_PROJETS, "%s_%s" % (nom_base, horodatage))
        try:
            os.makedirs(dossier_dest, exist_ok=True)
            with zipfile.ZipFile(chemin_zip) as z:
                z.extractall(dossier_dest)
        except Exception as e:
            messagebox.showerror("Importer un projet", "Impossible d'extraire ce zip :\n%s" % e)
            return

        contenu = os.listdir(dossier_dest)
        if len(contenu) == 1 and os.path.isdir(os.path.join(dossier_dest, contenu[0])):
            dossier_dest = os.path.join(dossier_dest, contenu[0])

        self._charger_projet(dossier_dest, nom_base)
        self._statut("Projet « %s » importé." % nom_base)

    def _ouvrir_dossier_projet(self):
        dossier = filedialog.askdirectory(title="Choisir le dossier du projet")
        if not dossier:
            return
        self._charger_projet(dossier, os.path.basename(dossier.rstrip("/\\")))

    def _nouveau_projet_vide(self):
        nom = simpledialog.askstring("Nouveau projet", "Nom du nouveau projet :", parent=self)
        if not nom:
            return
        horodatage = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dossier = os.path.join(DOSSIER_PROJETS, "%s_%s" % (nom, horodatage))
        os.makedirs(dossier, exist_ok=True)
        chemin_main = os.path.join(dossier, "main.py")
        with open(chemin_main, "w", encoding="utf-8") as f:
            f.write('# -*- coding: utf-8 -*-\nprint("Bonjour depuis %s")\n' % nom)
        self._charger_projet(dossier, nom)
        self.chemin_relatif_principal = "main.py"
        self.var_script_principal.set("main.py")
        self._statut("Nouveau projet « %s » créé avec un main.py de départ." % nom)

    def _exporter_projet_zip(self):
        if not self.dossier_projet:
            messagebox.showinfo("Exporter", "Aucun projet chargé.")
            return
        chemin = filedialog.asksaveasfilename(
            title="Exporter le projet en .zip", defaultextension=".zip",
            filetypes=[("Archive ZIP", "*.zip")])
        if not chemin:
            return
        base_sans_ext = chemin[:-4] if chemin.lower().endswith(".zip") else chemin
        try:
            shutil.make_archive(base_sans_ext, "zip", self.dossier_projet)
            self._statut("Projet exporté : %s" % chemin)
        except Exception as e:
            messagebox.showerror("Exporter", "Erreur pendant l'export :\n%s" % e)

    def _ouvrir_dossier_dans_explorateur(self):
        if self.dossier_projet and os.path.isdir(self.dossier_projet):
            try:
                os.startfile(self.dossier_projet)
            except Exception:
                messagebox.showinfo("Dossier du projet", self.dossier_projet)
        else:
            messagebox.showinfo("Dossier du projet", "Aucun projet chargé.")

    def _detecter_dossiers_donnees(self):
        """Après import, propose automatiquement les dossiers de premier
        niveau (hors code/exclus) comme données à inclure dans l'exe."""
        self.donnees_supplementaires = []
        self.liste_donnees.delete(0, "end")
        if not self.dossier_projet:
            return
        try:
            for nom in sorted(os.listdir(self.dossier_projet)):
                chemin = os.path.join(self.dossier_projet, nom)
                if not os.path.isdir(chemin):
                    continue
                if nom in DOSSIERS_EXCLUS_DONNEES:
                    continue
                self.donnees_supplementaires.append((chemin, nom))
                self.liste_donnees.insert("end", "%s\\" % nom)
        except Exception:
            pass

    # ================= arbre de fichiers =================
    def _rafraichir_arbre(self):
        self.arbre.delete(*self.arbre.get_children())
        if not self.dossier_projet:
            return
        self._inserer_dossier("", self.dossier_projet)

    def _inserer_dossier(self, parent_iid, chemin_dossier):
        try:
            entrees = sorted(os.listdir(chemin_dossier),
                              key=lambda n: (not os.path.isdir(os.path.join(chemin_dossier, n)), n.lower()))
        except Exception:
            return
        for nom in entrees:
            if nom in DOSSIERS_EXCLUS_ARBRE:
                continue
            chemin_complet = os.path.join(chemin_dossier, nom)
            relatif = os.path.relpath(chemin_complet, self.dossier_projet).replace("\\", "/")
            if os.path.isdir(chemin_complet):
                iid = self.arbre.insert(parent_iid, "end", iid=relatif, text="📁 " + nom, open=False)
                self._inserer_dossier(iid, chemin_complet)
            else:
                etoile = "⭐ " if relatif == self.chemin_relatif_principal else ""
                self.arbre.insert(parent_iid, "end", iid=relatif, text=etoile + "📄 " + nom)

    def _chemin_absolu_selection(self):
        sel = self.arbre.selection()
        if not sel or not self.dossier_projet:
            return None
        return os.path.join(self.dossier_projet, sel[0].replace("/", os.sep))

    def _relatif_selection(self):
        sel = self.arbre.selection()
        return sel[0] if sel else None

    def _dossier_cible_pour_ajout(self):
        """Renvoie le dossier (absolu) où ajouter un nouvel élément : le
        dossier sélectionné, ou le dossier parent du fichier sélectionné,
        ou la racine du projet si rien n'est sélectionné."""
        chemin = self._chemin_absolu_selection()
        if chemin is None:
            return self.dossier_projet
        if os.path.isdir(chemin):
            return chemin
        return os.path.dirname(chemin)

    # ---- actions sur l'arbre ----
    def _nouveau_fichier(self):
        if not self._verifier_projet_charge():
            return
        nom = simpledialog.askstring("Nouveau fichier", "Nom du fichier (ex: outils.py) :", parent=self)
        if not nom:
            return
        chemin = os.path.join(self._dossier_cible_pour_ajout(), nom)
        if os.path.exists(chemin):
            messagebox.showwarning("Nouveau fichier", "Ce fichier existe déjà.")
            return
        try:
            with open(chemin, "w", encoding="utf-8") as f:
                f.write("")
        except Exception as e:
            messagebox.showerror("Nouveau fichier", str(e))
            return
        self._rafraichir_arbre()
        relatif = os.path.relpath(chemin, self.dossier_projet).replace("\\", "/")
        self.arbre.selection_set(relatif)
        self._ouvrir_fichier_dans_editeur(relatif)

    def _nouveau_dossier(self):
        if not self._verifier_projet_charge():
            return
        nom = simpledialog.askstring("Nouveau dossier", "Nom du dossier :", parent=self)
        if not nom:
            return
        chemin = os.path.join(self._dossier_cible_pour_ajout(), nom)
        try:
            os.makedirs(chemin, exist_ok=False)
        except FileExistsError:
            messagebox.showwarning("Nouveau dossier", "Ce dossier existe déjà.")
            return
        except Exception as e:
            messagebox.showerror("Nouveau dossier", str(e))
            return
        self._rafraichir_arbre()

    def _importer_fichier_externe(self):
        if not self._verifier_projet_charge():
            return
        chemins = filedialog.askopenfilenames(title="Choisir un ou plusieurs fichiers à importer")
        if not chemins:
            return
        dossier_cible = self._dossier_cible_pour_ajout()
        for chemin in chemins:
            try:
                shutil.copy2(chemin, os.path.join(dossier_cible, os.path.basename(chemin)))
            except Exception as e:
                messagebox.showerror("Importer", "Erreur pour %s :\n%s" % (chemin, e))
        self._rafraichir_arbre()
        self._statut("%d fichier(s) importé(s)." % len(chemins))

    def _supprimer_selection(self):
        chemin = self._chemin_absolu_selection()
        relatif = self._relatif_selection()
        if chemin is None:
            return
        if not messagebox.askyesno("Supprimer", "Supprimer « %s » définitivement ?" % relatif):
            return
        try:
            if os.path.isdir(chemin):
                shutil.rmtree(chemin)
            else:
                os.remove(chemin)
        except Exception as e:
            messagebox.showerror("Supprimer", str(e))
            return
        if relatif == self.chemin_relatif_principal:
            self.chemin_relatif_principal = None
            self.var_script_principal.set("(aucun script principal choisi)")
        if relatif == self.chemin_fichier_edite:
            self._fermer_editeur()
        self._rafraichir_arbre()

    def _renommer_selection(self):
        chemin = self._chemin_absolu_selection()
        relatif = self._relatif_selection()
        if chemin is None:
            return
        ancien_nom = os.path.basename(chemin)
        nouveau_nom = simpledialog.askstring("Renommer", "Nouveau nom :",
                                              initialvalue=ancien_nom, parent=self)
        if not nouveau_nom or nouveau_nom == ancien_nom:
            return
        nouveau_chemin = os.path.join(os.path.dirname(chemin), nouveau_nom)
        try:
            os.rename(chemin, nouveau_chemin)
        except Exception as e:
            messagebox.showerror("Renommer", str(e))
            return
        if relatif == self.chemin_relatif_principal:
            self.chemin_relatif_principal = os.path.relpath(
                nouveau_chemin, self.dossier_projet).replace("\\", "/")
            self.var_script_principal.set(self.chemin_relatif_principal)
        self._rafraichir_arbre()

    def _definir_script_principal(self):
        relatif = self._relatif_selection()
        if not relatif or not relatif.lower().endswith(".py"):
            messagebox.showinfo("Script principal", "Sélectionnez un fichier .py dans l'arbre.")
            return
        self.chemin_relatif_principal = relatif
        self.var_script_principal.set(relatif)
        if not self.var_nom.get() or self.var_nom.get() == "main":
            self.var_nom.set(os.path.splitext(os.path.basename(relatif))[0])
        self._rafraichir_arbre()
        self._statut("Script principal défini : %s" % relatif)

    def _verifier_projet_charge(self):
        if not self.dossier_projet:
            messagebox.showinfo("Projet", "Importez d'abord un projet (.zip) ou créez-en un nouveau.")
            return False
        return True

    # ================= éditeur de fichier =================
    def _on_selection_arbre(self, event=None):
        relatif = self._relatif_selection()
        chemin = self._chemin_absolu_selection()
        if relatif is None or chemin is None or os.path.isdir(chemin):
            return
        self._ouvrir_fichier_dans_editeur(relatif)

    def _ouvrir_fichier_dans_editeur(self, relatif):
        # sauvegarde silencieuse du fichier précédent si modifié
        self._enregistrer_fichier_edite(silencieux=True)

        chemin = os.path.join(self.dossier_projet, relatif.replace("/", os.sep))
        extension = os.path.splitext(chemin)[1].lower()

        if self.label_apercu_image is not None:
            self.label_apercu_image.destroy()
            self.label_apercu_image = None

        if extension in EXTENSIONS_IMAGE:
            self.zone_editeur.pack_forget()
            try:
                image = tk.PhotoImage(file=chemin)
                self.label_apercu_image = ttk.Label(
                    self.zone_editeur.master, image=image, text="(aperçu image, lecture seule)",
                    compound="top")
                self.label_apercu_image.image = image
                self.label_apercu_image.pack(fill="both", expand=True, pady=(4, 0))
            except Exception:
                self.label_apercu_image = ttk.Label(
                    self.zone_editeur.master, text="Aperçu impossible pour ce fichier image.")
                self.label_apercu_image.pack(fill="both", expand=True, pady=(4, 0))
            self.chemin_fichier_edite = None
            self.var_fichier_ouvert.set(relatif + "  (image, lecture seule)")
            return

        self.zone_editeur.pack(fill="both", expand=True, pady=(4, 0))

        try:
            with open(chemin, "r", encoding="utf-8") as f:
                contenu = f.read()
        except UnicodeDecodeError:
            self.zone_editeur.configure(state="normal")
            self.zone_editeur.delete("1.0", "end")
            self.zone_editeur.insert("1.0",
                "(Fichier binaire — non éditable comme texte.\n"
                "Utilisez 🗑 Supprimer puis 📤 Importer pour le remplacer.)")
            self.zone_editeur.configure(state="disabled")
            self.chemin_fichier_edite = None
            self.var_fichier_ouvert.set(relatif + "  (binaire, lecture seule)")
            return
        except Exception as e:
            messagebox.showerror("Ouvrir le fichier", str(e))
            return

        self.zone_editeur.configure(state="normal")
        self.zone_editeur.delete("1.0", "end")
        self.zone_editeur.insert("1.0", contenu)
        self.chemin_fichier_edite = relatif
        self.var_fichier_ouvert.set(relatif)

    def _enregistrer_fichier_edite(self, silencieux=False):
        if not self.chemin_fichier_edite or not self.dossier_projet:
            return
        chemin = os.path.join(self.dossier_projet, self.chemin_fichier_edite.replace("/", os.sep))
        try:
            contenu = self.zone_editeur.get("1.0", "end-1c")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(contenu)
            if not silencieux:
                self._statut("Fichier enregistré : %s" % self.chemin_fichier_edite)
        except Exception as e:
            if not silencieux:
                messagebox.showerror("Enregistrer", str(e))

    def _fermer_editeur(self):
        self.chemin_fichier_edite = None
        if self.label_apercu_image is not None:
            self.label_apercu_image.destroy()
            self.label_apercu_image = None
        self.zone_editeur.pack(fill="both", expand=True, pady=(4, 0))
        self.zone_editeur.configure(state="normal")
        self.zone_editeur.delete("1.0", "end")
        self.zone_editeur.configure(state="disabled")
        self.var_fichier_ouvert.set("Aucun fichier ouvert.")

    # ================= options diverses =================
    def _choisir_icone(self):
        chemin = filedialog.askopenfilename(title="Choisir une icône", filetypes=[("Icône Windows", "*.ico")])
        if chemin:
            self.var_icone.set(chemin)

    def _choisir_dossier_sortie(self):
        chemin = filedialog.askdirectory(title="Choisir le dossier de sortie")
        if chemin:
            self.var_dossier_sortie.set(chemin)

    def _ajouter_dossier_donnees_manuel(self):
        chemin = filedialog.askdirectory(title="Choisir un dossier à inclure")
        if not chemin:
            return
        nom_dest = os.path.basename(chemin.rstrip("/\\"))
        self.donnees_supplementaires.append((chemin, nom_dest))
        self.liste_donnees.insert("end", "%s\\" % nom_dest)

    def _retirer_donnees(self):
        sel = list(self.liste_donnees.curselection())
        sel.reverse()
        for i in sel:
            self.liste_donnees.delete(i)
            del self.donnees_supplementaires[i]

    def _ouvrir_dossier_resultat(self):
        chemin = getattr(self, "_dernier_dossier_resultat", None)
        if chemin and os.path.exists(chemin):
            try:
                os.startfile(chemin)
            except Exception:
                messagebox.showinfo("Dossier résultat", chemin)

    # ================= compilation =================
    def _lancer_compilation(self):
        if self._compilation_en_cours:
            return
        if not self.dossier_projet:
            messagebox.showwarning("Compiler", "Importez ou créez d'abord un projet.")
            return
        if not self.chemin_relatif_principal:
            messagebox.showwarning("Compiler", "Désignez d'abord le script principal "
                                                "(sélectionnez un .py puis « ⭐ Définir... »).")
            return

        self._enregistrer_fichier_edite(silencieux=True)

        try:
            import PyInstaller.__main__  # noqa: F401
        except Exception:
            messagebox.showerror(
                "PyInstaller manquant",
                "Le module PyInstaller n'est pas disponible sur ce poste.\n"
                "Voir installer\\build.bat de ce projet pour l'intégrer correctement.")
            return

        nom = self.var_nom.get().strip() or os.path.splitext(
            os.path.basename(self.chemin_relatif_principal))[0]

        self.zone_log.delete("1.0", "end")
        self.var_statut.set("Compilation en cours...")
        self.bouton_compiler.config(state="disabled")
        self.bouton_ouvrir_resultat.config(state="disabled")
        self._compilation_en_cours = True

        dossier_sortie = self.var_dossier_sortie.get().strip() or "dist_compilations"
        os.makedirs(dossier_sortie, exist_ok=True)
        self._dernier_dossier_resultat = os.path.join(dossier_sortie, nom)

        script_absolu = os.path.join(self.dossier_projet, self.chemin_relatif_principal.replace("/", os.sep))
        args = self._construire_args_pyinstaller(script_absolu, nom, dossier_sortie)

        fil = threading.Thread(target=self._executer_pyinstaller,
                               args=(args, self.dossier_projet), daemon=True)
        fil.start()

    def _construire_args_pyinstaller(self, script, nom, dossier_sortie):
        args = ["--noconfirm", "--name", nom]
        args.append("--windowed" if self.var_mode.get() == "fenetre" else "--console")
        args.append("--onefile" if self.var_un_seul_fichier.get() else "--onedir")
        args += ["--paths", self.dossier_projet]

        icone = self.var_icone.get().strip()
        if icone:
            args += ["--icon", icone]

        for source, destination in self.donnees_supplementaires:
            args += ["--add-data", "%s%s%s" % (source, os.pathsep, destination)]

        args += ["--distpath", dossier_sortie]
        args += ["--workpath", os.path.join(dossier_sortie, "_travail_temporaire")]
        args += ["--specpath", os.path.join(dossier_sortie, "_travail_temporaire")]
        args.append(script)
        return args

    def _executer_pyinstaller(self, args, dossier_travail):
        import PyInstaller.__main__ as pyi

        ancien_stdout, ancien_stderr = sys.stdout, sys.stderr
        ancien_cwd = os.getcwd()
        flux = FluxVersFile(self._file_log)
        sys.stdout = flux
        sys.stderr = flux

        gestionnaire = logging.StreamHandler(flux)
        gestionnaire.setLevel(logging.INFO)
        logger_racine = logging.getLogger()
        niveau_avant = logger_racine.level
        logger_racine.addHandler(gestionnaire)
        logger_racine.setLevel(logging.INFO)

        succes = True
        try:
            os.chdir(dossier_travail)  # pour que les imports locaux (ex: "app") soient trouvés
            self._file_log.put("Commande PyInstaller : %s\n\n" % " ".join(args))
            pyi.run(args)
        except SystemExit as e:
            if e.code not in (0, None):
                succes = False
                self._file_log.put("\n[Compilation terminée avec le code %s]\n" % e.code)
        except Exception:
            succes = False
            self._file_log.put("\n[ERREUR]\n" + traceback.format_exc())
        finally:
            os.chdir(ancien_cwd)
            sys.stdout, sys.stderr = ancien_stdout, ancien_stderr
            logger_racine.removeHandler(gestionnaire)
            logger_racine.setLevel(niveau_avant)

        self._file_log.put(("__FIN_OK__" if succes else "__FIN_ERREUR__"))

    def _lire_file_log(self):
        try:
            while True:
                item = self._file_log.get_nowait()
                if item == "__FIN_OK__":
                    self._compilation_en_cours = False
                    self.bouton_compiler.config(state="normal")
                    self.bouton_ouvrir_resultat.config(state="normal")
                    self.var_statut.set("Compilation terminée avec succès.")
                elif item == "__FIN_ERREUR__":
                    self._compilation_en_cours = False
                    self.bouton_compiler.config(state="normal")
                    self.var_statut.set("Échec de la compilation (voir le journal).")
                else:
                    self.zone_log.insert("end", item)
                    self.zone_log.see("end")
        except queue.Empty:
            pass
        self.after(100, self._lire_file_log)

    def _statut(self, texte):
        self.var_statut.set(texte)


def main():
    os.makedirs(DOSSIER_PROJETS, exist_ok=True)
    app = CompilateurApp()
    try:
        style = ttk.Style(app)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app.mainloop()


if __name__ == "__main__":
    main()

"use client";

// Page « Campagne » : liste, import Markdown, état canonique (phases, crochets,
// PNJ, lieux, blocs, indices, récompenses) et mutations déclaratives.

import { useCallback, useEffect, useState } from "react";
import { jdr, ErreurJdr } from "@/lib/jdr";
import CreationCampagne from "@/components/CreationCampagne";

type PNJ = { nom: string; objectif: string; faille: string; attitude: string; rencontre: boolean };
type Lieu = { nom: string; description: string; decouvert: boolean };
type Crochet = { id: string; titre: string; lie_a_pj: string; statut: string };
type Bloc = { id: string; titre: string; position: string; deplace: boolean };
type Advisory = {
  ok: boolean;
  type: string;
  groupe?: { effectif: number; niveaux: number[] };
  xp_monstres?: number;
  seuils?: Record<string, number>;
  degre?: string;
  conseil?: string;
  erreur?: string;
};
type Etat = {
  id: string;
  titre: string;
  synopsis: string;
  pj: string[];
  phase: string;
  danger: string;
  active: boolean;
  structure_valide: boolean;
  avertissements_structure: string[];
  accroche: string;
  enjeux: string;
  motivations: string;
  lieux: Lieu[];
  pnj: PNJ[];
  crochets: Crochet[];
  blocs: Bloc[];
  indices: string[];
  recompenses: string[];
  chronologie: string[];
  mode?: string;
  age_joueur?: number;
  duree?: string;
  nb_joueurs?: number;
  niveaux?: number[];
  piliers?: string[];
  ton?: string;
  theme?: string;
  conseil_cadrage?: { ton?: string; violence?: string; duree?: string; scenes_conseillees?: string };
};
type Resume = { id: string; titre: string; phase: string; active: boolean };

export default function PageCampagne() {
  const [liste, setListe] = useState<Resume[]>([]);
  const [id, setId] = useState("");
  const [etat, setEtat] = useState<Etat | null>(null);
  const [erreur, setErreur] = useState("");
  const [advisory, setAdvisory] = useState<Advisory | null>(null);
  const [wizard, setWizard] = useState(false);

  const chargerListe = useCallback(async () => {
    try {
      const j = await jdr.get<{ campagnes: Resume[] }>("/campagne");
      setListe(j.campagnes);
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur liste.");
    }
  }, []);

  const chargerEtat = useCallback(async (cid: string) => {
    try {
      setEtat(await jdr.get<Etat>(`/campagne/${encodeURIComponent(cid)}`));
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur état.");
    }
  }, []);

  useEffect(() => {
    chargerListe();
  }, [chargerListe]);
  useEffect(() => {
    if (id) chargerEtat(id);
    else setEtat(null);
  }, [id, chargerEtat]);

  const muter = useCallback(
    async (corps: Record<string, unknown>) => {
      setErreur("");
      try {
        // `jdr.patch` lève ErreurJdr dès que `ok:false` (mutation refusée par
        // le moteur) : le catch ci-dessous affiche déjà l'erreur du moteur.
        await jdr.patch(`/campagne/${encodeURIComponent(id)}`, corps);
        await chargerEtat(id);
      } catch (e) {
        setErreur(e instanceof ErreurJdr ? e.message : "Erreur mutation.");
      }
    },
    [id, chargerEtat],
  );

  const demander = (q: string) => {
    const v = window.prompt(q);
    return v == null ? null : v.trim();
  };

  const supprimer = useCallback(
    async (cid: string, titre: string) => {
      if (!window.confirm(`Supprimer définitivement la campagne « ${titre || cid} » ?`))
        return;
      setErreur("");
      try {
        await jdr.del(`/campagne/${encodeURIComponent(cid)}`);
        if (cid === id) setId("");
        await chargerListe();
      } catch (e) {
        setErreur(e instanceof ErreurJdr ? e.message : "Erreur de suppression.");
      }
    },
    [id, chargerListe],
  );

  const rejouer = useCallback(
    async (cid: string, titre: string) => {
      if (
        !window.confirm(
          `Rejouer « ${titre || cid} » depuis le début ? La trame et le personnage sont conservés, la progression (phase, indices, crochets, lieux) est remise à zéro.`,
        )
      )
        return;
      setErreur("");
      try {
        // Le backend réinitialise la partie ET renvoie l'amorce d'ouverture
        // canonique (identique à celle envoyée à la création). On ne la construit
        // plus ici : une campagne recommencée s'ouvre avec le même prompt qu'une
        // campagne neuve.
        const j = await jdr.post<{ message?: string }>(
          `/campagne/${encodeURIComponent(cid)}/rejouer`,
        );
        await chargerEtat(cid);
        await chargerListe();
        const message =
          j.message ??
          "Ouvre la campagne : raconte l'accroche en expliquant pourquoi le " +
            "personnage est là et donne-lui une raison personnelle et concrète " +
            "d'avancer dans la quête (un objectif immédiat, ce qu'il risque ou " +
            "gagne, lié à son crochet personnel). Puis lance la partie.";
        window.location.href = `/chat?campagne=${encodeURIComponent(
          cid,
        )}&nouveau=1&message=${encodeURIComponent(message)}`;
      } catch (e) {
        setErreur(
          e instanceof ErreurJdr ? e.message : "Erreur de réinitialisation.",
        );
      }
    },
    [chargerEtat, chargerListe],
  );

  return (
    <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
      <section className="w-full md:w-80 shrink-0 overflow-y-auto border-b md:border-b-0 md:border-r border-white/10 bg-black/10">
        <div className="p-3 border-b border-white/10 font-bold text-or flex items-center justify-between">
          <span>Campagnes</span>
          <button
            onClick={() => setWizard((w) => !w)}
            className="rounded bg-or/80 hover:bg-or text-encre text-xs font-semibold px-2 py-1"
          >
            {wizard ? "Fermer" : "+ Nouvelle"}
          </button>
        </div>
        <div className="p-2 space-y-1">
          {liste.length === 0 && (
            <p className="text-parchemin/40 italic text-sm p-2">
              Aucune campagne. Importe un scénario Markdown ci-dessous.
            </p>
          )}
          {liste.map((c) => (
            <div
              key={c.id}
              onClick={() => setId(c.id)}
              className={`group flex items-center gap-2 w-full text-left rounded-lg px-3 py-2 text-sm cursor-pointer ${
                c.id === id ? "bg-or/20 text-or" : "hover:bg-white/5"
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="truncate">{c.titre || c.id}</div>
                <div className="text-[11px] text-parchemin/50">
                  {c.active ? c.phase : "clôturée"}
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  supprimer(c.id, c.titre);
                }}
                title="Supprimer la campagne"
                className="shrink-0 opacity-0 group-hover:opacity-100 text-parchemin/50 hover:text-red-400"
              >
                🗑
              </button>
            </div>
          ))}
        </div>
        <FormulaireImport
          onImporte={(nouvelId) => {
            chargerListe();
            setId(nouvelId);
          }}
        />
      </section>

      <section className="flex-1 overflow-y-auto p-4">
        {erreur && <div className="text-red-400 text-sm mb-2">{erreur}</div>}
        {wizard && (
          <div className="mb-4 rounded-lg border border-or/30 bg-black/20">
            <CreationCampagne onAnnuler={() => setWizard(false)} />
          </div>
        )}
        {!etat ? (
          <p className="text-parchemin/40 italic">Sélectionne ou importe une campagne.</p>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="text-xl font-bold text-or">{etat.titre || etat.id}</h2>
              <span className="text-sm text-parchemin/60">
                phase : <b className="text-or">{etat.phase}</b> · danger {etat.danger}
              </span>
              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={() => rejouer(id, etat.titre)}
                  title="Rejouer la même aventure depuis le début (trame et PJ conservés)"
                  className="rounded bg-or/80 hover:bg-or text-encre px-3 py-1 text-xs font-semibold"
                >
                  ↺ Rejouer
                </button>
              </div>
            </div>

            <Cadrage etat={etat} />

            {!etat.structure_valide && (
              <div className="rounded border border-sang/40 bg-sang/10 p-2 text-xs text-parchemin/80">
                <div className="font-semibold text-sang mb-1">
                  Structure à compléter :
                </div>
                <ul className="list-disc ml-4 space-y-0.5">
                  {etat.avertissements_structure.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Barre de mutations globales */}
            <div className="flex flex-wrap gap-1.5 text-xs">
              {etat.active && etat.phase !== "conclusion" && (
                <Bouton onClick={() => muter({ action: "avancer_phase" })}>
                  ▶ Phase suivante
                </Bouton>
              )}
              <Bouton
                onClick={() => {
                  const v = demander("Indice à consigner ?");
                  if (v) muter({ action: "ajouter_indice", indice: v });
                }}
              >
                + Indice
              </Bouton>
              <Bouton
                onClick={() => {
                  const v = demander("Récompense accordée ?");
                  if (v) muter({ action: "accorder_recompense", recompense: v });
                }}
              >
                + Récompense
              </Bouton>
              <Bouton onClick={() => setAdvisory(null)}>✕ Advisory</Bouton>
            </div>

            <AdvisoryForm id={id} onResultat={setAdvisory} />
            {advisory && (
              <div className="rounded border border-or/40 bg-or/10 p-3 text-sm">
                {advisory.ok ? (
                  <>
                    <div className="font-semibold text-or capitalize">
                      Difficulté : {advisory.degre}
                    </div>
                    <div className="text-parchemin/70 text-xs mt-1">
                      XP monstres {advisory.xp_monstres} · seuils{" "}
                      {advisory.seuils
                        ? Object.entries(advisory.seuils)
                            .map(([k, v]) => `${k} ${v}`)
                            .join(" / ")
                        : "—"}
                    </div>
                    <div className="text-parchemin/80 mt-1">{advisory.conseil}</div>
                  </>
                ) : (
                  <div className="text-red-400">{advisory.erreur}</div>
                )}
              </div>
            )}

            {etat.synopsis && (
              <p className="text-sm text-parchemin/70 italic">{etat.synopsis}</p>
            )}

            <Section titre={`Crochets (${etat.crochets.length})`}>
              {etat.crochets.map((c) => (
                <Ligne key={c.id}>
                  <span className="flex-1">
                    {c.titre || c.id}
                    {c.lie_a_pj && (
                      <span className="text-parchemin/50"> · {c.lie_a_pj}</span>
                    )}
                  </span>
                  <span className="text-xs text-parchemin/50">{c.statut}</span>
                  {etat.active && c.statut !== "resolvee" && (
                    <Bouton
                      onClick={() =>
                        muter({ action: "resoudre_crochet", id: c.id })
                      }
                    >
                      Résoudre
                    </Bouton>
                  )}
                </Ligne>
              ))}
            </Section>

            <Section titre={`PNJ (${etat.pnj.length})`}>
              {etat.pnj.map((p) => (
                <Ligne key={p.nom}>
                  <span className="flex-1">
                    {p.nom}
                    <span className="text-parchemin/50">
                      {" "}
                      · {p.attitude}
                      {p.rencontre ? " · rencontré" : ""}
                    </span>
                  </span>
                  {etat.active && (
                    <>
                      {!p.rencontre && (
                        <Bouton
                          onClick={() =>
                            muter({ action: "rencontrer_pnj", nom: p.nom })
                          }
                        >
                          Rencontrer
                        </Bouton>
                      )}
                      <Bouton
                        onClick={() => {
                          const v = demander(`Nouvelle attitude de ${p.nom} ?`);
                          if (v)
                            muter({
                              action: "changer_attitude",
                              nom: p.nom,
                              attitude: v,
                            });
                        }}
                      >
                        Attitude
                      </Bouton>
                    </>
                  )}
                </Ligne>
              ))}
            </Section>

            <Section titre={`Lieux (${etat.lieux.length})`}>
              {etat.lieux.map((l) => (
                <Ligne key={l.nom}>
                  <span className="flex-1">
                    {l.nom}
                    {l.decouvert && (
                      <span className="text-emerald-400 text-xs"> · découvert</span>
                    )}
                  </span>
                  {etat.active && !l.decouvert && (
                    <Bouton
                      onClick={() =>
                        muter({ action: "decouvrir_lieu", nom: l.nom })
                      }
                    >
                      Découvrir
                    </Bouton>
                  )}
                </Ligne>
              ))}
            </Section>

            <Section titre={`Blocs (${etat.blocs.length})`}>
              {etat.blocs.map((b) => (
                <Ligne key={b.id}>
                  <span className="flex-1">
                    {b.titre || b.id}
                    <span className="text-parchemin/50"> · {b.position}</span>
                  </span>
                  {etat.active && (
                    <Bouton
                      onClick={() =>
                        muter({
                          action: "deplacer_bloc",
                          id: b.id,
                          position: b.position === "actif" ? "reserve" : "actif",
                        })
                      }
                    >
                      {b.position === "actif" ? "Réserver" : "Activer"}
                    </Bouton>
                  )}
                </Ligne>
              ))}
            </Section>

            {etat.indices.length > 0 && (
              <Section titre={`Indices (${etat.indices.length})`}>
                {etat.indices.map((i, k) => (
                  <Ligne key={k}>
                    <span className="flex-1 text-parchemin/80">{i}</span>
                  </Ligne>
                ))}
              </Section>
            )}

            {etat.recompenses.length > 0 && (
              <Section titre={`Récompenses (${etat.recompenses.length})`}>
                {etat.recompenses.map((r, k) => (
                  <Ligne key={k}>
                    <span className="flex-1 text-parchemin/80">{r}</span>
                  </Ligne>
                ))}
              </Section>
            )}

            {etat.chronologie.length > 0 && (
              <Section titre="Chronologie">
                <div className="text-xs text-parchemin/50 space-y-0.5">
                  {etat.chronologie.slice(-15).map((c, k) => (
                    <div key={k}>{c}</div>
                  ))}
                </div>
              </Section>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function Section({ titre, children }: { titre: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="font-semibold text-or/90 text-sm mb-1">{titre}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function Ligne({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded bg-white/5 px-3 py-1.5 text-sm">
      {children}
    </div>
  );
}

function Cadrage({ etat }: { etat: Etat }) {
  const cc = etat.conseil_cadrage;
  const chips: string[] = [];
  if (etat.mode) chips.push(etat.mode === "surprise" ? "🎭 Surprise" : "🧭 Guidé");
  if (etat.age_joueur) chips.push(`Âge ${etat.age_joueur} ans`);
  if (etat.duree) chips.push(`Durée : ${etat.duree}`);
  if (etat.nb_joueurs) chips.push(`${etat.nb_joueurs} joueur(s)`);
  if (etat.niveaux?.length) chips.push(`Niveaux ${etat.niveaux.join(",")}`);
  if (etat.piliers?.length) chips.push(`Piliers : ${etat.piliers.join(", ")}`);
  if (etat.ton) chips.push(`Ton : ${etat.ton}`);
  if (chips.length === 0) return null;
  return (
    <div className="rounded border border-white/10 bg-black/20 p-2 text-xs space-y-1">
      <div className="flex flex-wrap gap-1.5">
        {chips.map((c, i) => (
          <span key={i} className="rounded bg-white/5 px-2 py-0.5 text-parchemin/80">
            {c}
          </span>
        ))}
      </div>
      {etat.theme && <div className="text-parchemin/60 italic">{etat.theme}</div>}
      {cc?.ton && (
        <div className="text-parchemin/50">
          Conseil MJ : ton {cc.ton}, violence {cc.violence}
          {cc.scenes_conseillees ? ` · ${cc.scenes_conseillees} scènes` : ""}.
        </div>
      )}
    </div>
  );
}

function Bouton({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 text-xs shrink-0"
    >
      {children}
    </button>
  );
}

function AdvisoryForm({
  id,
  onResultat,
}: {
  id: string;
  onResultat: (a: Advisory) => void;
}) {
  const [monstres, setMonstres] = useState("");
  const [niveaux, setNiveaux] = useState("");
  const [erreur, setErreur] = useState("");

  const lancer = useCallback(async () => {
    setErreur("");
    let specs: unknown[];
    try {
      specs = monstres.trim() ? JSON.parse(monstres) : [];
    } catch {
      setErreur("Monstres : JSON invalide.");
      return;
    }
    if (specs.length === 0) {
      setErreur("Indique au moins un monstre.");
      return;
    }
    const corps: Record<string, unknown> = { monstres: specs };
    if (niveaux.trim()) {
      corps.niveaux_pj = niveaux
        .split(",")
        .map((n) => Number(n.trim()))
        .filter((n) => !Number.isNaN(n));
    }
    try {
      const r = await jdr.post<Advisory>(
        `/campagne/${encodeURIComponent(id)}/advisory`,
        corps,
      );
      onResultat(r);
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur advisory.");
    }
  }, [id, monstres, niveaux, onResultat]);

  return (
    <div className="rounded border border-white/10 bg-black/20 p-2 space-y-1">
      <div className="text-xs font-semibold text-or/80">
        Advisory d&apos;équilibrage
      </div>
      <textarea
        value={monstres}
        onChange={(e) => setMonstres(e.target.value)}
        rows={2}
        placeholder='Monstres : [{"nom":"Orc","cr":0.5,"nb":3}]'
        className="w-full bg-white/5 rounded px-2 py-1 text-xs outline-none font-mono"
      />
      <input
        value={niveaux}
        onChange={(e) => setNiveaux(e.target.value)}
        placeholder="Niveaux PJ (option) : 3,3,4"
        className="w-full bg-white/5 rounded px-2 py-1 text-xs outline-none"
      />
      {erreur && <div className="text-red-400 text-xs">{erreur}</div>}
      <button
        onClick={lancer}
        className="rounded bg-or/70 hover:bg-or text-encre text-xs font-semibold px-3 py-1"
      >
        Calculer
      </button>
    </div>
  );
}

function FormulaireImport({ onImporte }: { onImporte: (id: string) => void }) {
  const [markdown, setMarkdown] = useState("");
  const [idManuel, setIdManuel] = useState("");
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);

  const importer = useCallback(async () => {
    setErreur("");
    if (!markdown.trim()) {
      setErreur("Colle le Markdown du scénario.");
      return;
    }
    setEnCours(true);
    try {
      const corps: Record<string, unknown> = { markdown };
      if (idManuel.trim()) corps.id = idManuel.trim();
      const j = await jdr.post<{ id: string }>("/campagne/importer", corps);
      setMarkdown("");
      setIdManuel("");
      onImporte(j.id);
    } catch (e) {
      setErreur(e instanceof ErreurJdr ? e.message : "Erreur import.");
    } finally {
      setEnCours(false);
    }
  }, [markdown, idManuel, onImporte]);

  return (
    <div className="border-t border-white/10 p-3 space-y-2">
      <div className="font-semibold text-or text-sm">
        Importer un scénario (Markdown)
      </div>
      <textarea
        value={markdown}
        onChange={(e) => setMarkdown(e.target.value)}
        rows={5}
        placeholder="---&#10;titre: ...&#10;---&#10;# Scénario ..."
        className="w-full bg-white/5 rounded px-2 py-1 text-xs outline-none font-mono"
      />
      <input
        value={idManuel}
        onChange={(e) => setIdManuel(e.target.value)}
        placeholder="id (optionnel)"
        className="w-full bg-white/5 rounded px-2 py-1 text-xs outline-none"
      />
      {erreur && <div className="text-red-400 text-xs">{erreur}</div>}
      <button
        onClick={importer}
        disabled={enCours}
        className="rounded-lg bg-or/80 hover:bg-or text-encre text-xs font-semibold px-3 py-1.5 disabled:opacity-40"
      >
        Importer
      </button>
    </div>
  );
}

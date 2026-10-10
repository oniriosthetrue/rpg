"use client";

// Contexte « personnage actif » partagé entre les pages (chat, persos, combat).
// Persisté en localStorage pour survivre aux rechargements et navigations.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

type Perso = { nom: string; espece: string; classe: string; niveau: number };

type Valeur = {
  personnages: Perso[];
  nom: string;
  setNom: (nom: string) => void;
  rafraichir: number;
  onChangementFiche: () => void;
  rechargerListe: () => Promise<void>;
};

const Ctx = createContext<Valeur | null>(null);
const CLE = "mj-perso-actif";

export function PersoProvider({ children }: { children: React.ReactNode }) {
  const [personnages, setPersonnages] = useState<Perso[]>([]);
  const [nom, setNomState] = useState("");
  const [rafraichir, setRafraichir] = useState(0);

  const rechargerListe = useCallback(async () => {
    try {
      const r = await fetch("/api/jdr/personnages", { cache: "no-store" });
      const j = await r.json();
      if (j.ok && Array.isArray(j.personnages)) {
        setPersonnages(j.personnages);
        setNomState((n) => {
          if (n && j.personnages.some((p: Perso) => p.nom === n)) return n;
          const stocke =
            typeof localStorage !== "undefined"
              ? localStorage.getItem(CLE) || ""
              : "";
          if (stocke && j.personnages.some((p: Perso) => p.nom === stocke))
            return stocke;
          return j.personnages[0]?.nom || "";
        });
      }
    } catch {
      /* backend indisponible : liste vide */
    }
  }, []);

  useEffect(() => {
    rechargerListe();
  }, [rechargerListe]);

  const setNom = useCallback((n: string) => {
    setNomState(n);
    if (typeof localStorage !== "undefined") localStorage.setItem(CLE, n);
  }, []);

  const onChangementFiche = useCallback(
    () => setRafraichir((x) => x + 1),
    [],
  );

  const valeur = useMemo(
    () => ({
      personnages,
      nom,
      setNom,
      rafraichir,
      onChangementFiche,
      rechargerListe,
    }),
    [personnages, nom, setNom, rafraichir, onChangementFiche, rechargerListe],
  );

  return <Ctx.Provider value={valeur}>{children}</Ctx.Provider>;
}

export function usePerso(): Valeur {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePerso doit être utilisé dans <PersoProvider>.");
  return v;
}

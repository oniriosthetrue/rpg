"use client";

// Page d'écran de création. Récupère le payload écrit par l'assistant de
// création (sessionStorage) puis lance l'écran de progression. Si le payload a
// disparu (rechargement direct, navigation passée), on renvoie à la campagne.

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import CreationProgress from "@/components/CreationProgress";

const CLE_CREATION = "mj-creation-en-cours";

type Payload = {
  campagneId: string;
  consigne: string;
  message: string;
  titre: string;
  mode: string;
};

function Ecran() {
  const router = useRouter();
  const [payload, setPayload] = useState<Payload | null>(null);
  const [lus, setLus] = useState(false);

  useEffect(() => {
    try {
      const brut = sessionStorage.getItem(CLE_CREATION);
      if (brut) {
        sessionStorage.removeItem(CLE_CREATION); // à consommer une seule fois
        setPayload(JSON.parse(brut) as Payload);
      }
    } catch {
      /* payload illisible → redirection ci-dessous */
    }
    setLus(true);
  }, []);

  if (!lus) return <div className="flex-1" />;

  if (!payload) {
    // Rien à créer : retour propre vers la page Campagne.
    router.replace("/campagne");
    return <div className="flex-1" />;
  }

  return (
    <CreationProgress
      campagneId={payload.campagneId}
      consigne={payload.consigne}
      message={payload.message}
      titre={payload.titre}
      mode={payload.mode}
    />
  );
}

export default function PageCreation() {
  return (
    <Suspense fallback={<div className="flex-1" />}>
      <Ecran />
    </Suspense>
  );
}

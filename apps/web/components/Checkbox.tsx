"use client";

// Case à cocher réutilisable : carré avec coche ✓ visible quand elle est activée.
// Purement présentationnelle — la gestion du clic appartient au parent (ex. une
// ligne entière cliquable). Utiliser `CheckboxLigne` pour un élément de liste
// « toute la ligne est cliquable + libellé + case à cocher ».

import type { ReactNode } from "react";

export function Checkbox({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[11px] font-bold leading-none transition-colors ${
        checked
          ? "border-or bg-or text-encre"
          : "border-parchemin/40 bg-transparent text-transparent"
      }`}
    >
      {"\u2713"}
    </span>
  );
}

export function CheckboxLigne({
  checked,
  onToggle,
  children,
  disabled,
}: {
  checked: boolean;
  onToggle: () => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={onToggle}
      disabled={disabled}
      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm disabled:opacity-40 ${
        checked
          ? "bg-or/20 text-or ring-1 ring-or/50"
          : "bg-white/5 hover:bg-white/10"
      }`}
    >
      <Checkbox checked={checked} />
      {children}
    </button>
  );
}

import Sidebar from "@/components/Sidebar";
import { PersoProvider } from "@/components/PersoContext";

// Layout applicatif : sidebar + contenu, pour toutes les pages du groupe (app).
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <PersoProvider>
      <div className="h-screen flex flex-col md:flex-row overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">{children}</div>
      </div>
    </PersoProvider>
  );
}

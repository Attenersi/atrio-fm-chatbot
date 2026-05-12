import { LanguageToggle } from "../../components/LanguageToggle";
import { Sidebar } from "../../components/Sidebar";
import { ThemeToggle } from "../../components/ThemeToggle";

export default function MainGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <div className="chrome-toggles-fixed">
        <LanguageToggle />
        <ThemeToggle />
      </div>
      <div className="app-shell">
        <Sidebar />
        <main className="main-content">{children}</main>
      </div>
    </>
  );
}

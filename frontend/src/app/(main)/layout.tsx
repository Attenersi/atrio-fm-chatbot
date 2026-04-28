import { Sidebar } from "../../components/Sidebar";
import { ThemeToggle } from "../../components/ThemeToggle";

export default function MainGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ThemeToggle />
      <div className="app-shell">
        <Sidebar />
        <main className="main-content">{children}</main>
      </div>
    </>
  );
}

import { ThemeToggle } from "../../components/ThemeToggle";

export default function AuthGroupLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth-shell">
      <ThemeToggle />
      {children}
    </div>
  );
}

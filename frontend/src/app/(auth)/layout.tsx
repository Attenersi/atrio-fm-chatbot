import Image from "next/image";
import Link from "next/link";
import { ThemeToggle } from "../../components/ThemeToggle";

export default function AuthGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="auth-shell">
      <ThemeToggle />
      <Link href="/" className="auth-strip-brand" aria-label="Atrio home">
        <Image
          className="brand-logo brand-logo-dark"
          src="/atrio-brand-assets/atrio-logo-dark.png?v=4"
          alt="Atrio"
          width={170}
          height={50}
          priority
        />
        <Image
          className="brand-logo brand-logo-light"
          src="/atrio-brand-assets/atrio-logo-light.png?v=4"
          alt="Atrio"
          width={170}
          height={50}
          priority
        />
      </Link>
      {children}
    </div>
  );
}

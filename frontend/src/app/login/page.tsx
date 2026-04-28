"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSession } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();

  useEffect(() => {
    getSession()
      .then((res) => router.replace(res.user.role === "admin" ? "/admin" : "/chat"))
      .catch(() => router.replace("/"));
  }, [router]);

  return (
    <section className="page-shell">
      <p>Redirecting...</p>
    </section>
  );
}

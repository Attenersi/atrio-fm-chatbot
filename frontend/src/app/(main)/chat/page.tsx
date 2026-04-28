"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChatWindow } from "../../../components/ChatWindow";
import { getSession } from "../../../lib/api";

export default function ChatPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    getSession()
      .then(() => setReady(true))
      .catch(() => router.replace("/"));
  }, [router]);

  if (!ready) {
    return <section className="page-shell"><p>Checking session...</p></section>;
  }

  return <ChatWindow />;
}

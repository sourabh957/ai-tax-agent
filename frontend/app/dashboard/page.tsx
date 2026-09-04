"use client";

import { AppShell } from "@/components/layout/app-shell";
import { ChatWindow } from "@/components/chat/chat-window";
import { useAuth } from "@/hooks/use-auth";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function DashboardPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/auth");
    }
  }, [user, isLoading, router]);

  if (isLoading || !user) return null;

  return (
    <AppShell>
      <ChatWindow />
    </AppShell>
  );
}


"use client";

import { AppShell } from "@/components/layout/app-shell";
import { ChatWindow } from "@/components/chat/chat-window";

export default function DashboardPage() {
  return (
    <AppShell>
      <ChatWindow />
    </AppShell>
  );
}

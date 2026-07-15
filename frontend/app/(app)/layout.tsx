import { Sidebar, MobileNav } from "@/components/shell/sidebar";
import { AppGuard } from "@/components/shell/app-guard";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppGuard>
      <div className="flex min-h-screen bg-paper">
        <Sidebar />
        <div className="relative flex-1">
          <main className="mx-auto max-w-5xl px-5 py-9 pb-28 lg:px-12 lg:pb-12">{children}</main>
        </div>
        <MobileNav />
      </div>
    </AppGuard>
  );
}

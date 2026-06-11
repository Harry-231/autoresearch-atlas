import Link from "next/link";

export function Nav() {
  return (
    <header className="border-b bg-card">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-primary text-sm text-primary-foreground">
            C
          </span>
          Crucible
          <span className="text-xs font-normal text-muted-foreground">research OS</span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <Link href="/" className="rounded-md px-3 py-1.5 hover:bg-accent">
            Programs
          </Link>
          <Link href="/tools" className="rounded-md px-3 py-1.5 hover:bg-accent">
            Tools
          </Link>
        </nav>
      </div>
    </header>
  );
}

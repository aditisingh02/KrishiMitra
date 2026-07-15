import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4 py-16">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="display text-3xl text-ink">Create your farm</h1>
          <p className="mt-1.5 text-sm text-muted">Start your digital twin in two minutes.</p>
        </div>
        <SignUp
          appearance={{
            elements: {
              rootBox: "mx-auto",
              card: "shadow-none border border-line",
              headerTitle: "hidden",
              headerSubtitle: "hidden",
            },
          }}
          signInUrl="/sign-in"
          forceRedirectUrl="/onboarding"
        />
      </div>
    </div>
  );
}
